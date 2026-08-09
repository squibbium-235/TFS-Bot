from __future__ import annotations

import asyncio
import random
import re
import time
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from src.services.custom_commands.store import (
    ADD_REACTION,
    ADD_ROLE,
    DELETE_MESSAGE,
    REMOVE_ROLE,
    SEND_EMBED,
    SEND_MESSAGE,
    CustomCommand,
    CustomCommandStore,
)
from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
)
from src.utils.permissions import (
    get_member_level_name,
    member_meets_level,
)


LEVEL_CHOICES = [
    app_commands.Choice(
        name="Public",
        value=LEVEL_PUBLIC,
    ),
    app_commands.Choice(
        name="Staff",
        value=LEVEL_STAFF,
    ),
    app_commands.Choice(
        name="Admin",
        value=LEVEL_ADMIN,
    ),
    app_commands.Choice(
        name="Owner",
        value=LEVEL_OWNER,
    ),
]

MESSAGE_TARGET_CHOICES = [
    app_commands.Choice(
        name="Trigger message",
        value="trigger",
    ),
    app_commands.Choice(
        name="Latest bot response",
        value="response",
    ),
]

MEMBER_TARGET_CHOICES = [
    app_commands.Choice(
        name="Command user",
        value="invoker",
    ),
    app_commands.Choice(
        name="Mentioned user",
        value="target",
    ),
]

RANDOM_PLACEHOLDER_RE = re.compile(
    r"\{random:([^{}]+)\}"
)

ARGUMENT_PLACEHOLDER_RE = re.compile(
    r"\{arg(\d+)\}"
)


def parse_colour(
    value: str | None,
) -> int | None:
    if not value:
        return None

    value = (
        value.strip()
        .lower()
        .removeprefix("#")
        .removeprefix("0x")
    )

    if not re.fullmatch(
        r"[0-9a-f]{6}",
        value,
    ):
        raise ValueError(
            "Colour must be six hex digits, "
            "for example `5865F2`."
        )

    return int(
        value,
        16,
    )


async def command_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    store = getattr(
        interaction.client,
        "custom_command_store",
        None,
    )

    if store is None:
        return []

    current = current.lower().strip()

    choices: list[
        app_commands.Choice[str]
    ] = []

    custom_commands = await store.list(
        interaction.guild.id
    )

    for custom_command in custom_commands:
        label = (
            f"{custom_command.name} - "
            f"{custom_command.description}"
        ).strip(" -")

        if (
            current
            and current not in label.lower()
        ):
            continue

        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=custom_command.name,
            )
        )

    return choices[:25]


class CustomCommandCog(commands.Cog):
    custom_command_group = app_commands.Group(
        name="custom-command",
        description=(
            "Create and manage custom "
            "prefix commands."
        ),
    )

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

        self.store: CustomCommandStore = (
            bot.custom_command_store
        )

        self.cooldowns: dict[
            tuple[int, str, int],
            float,
        ] = {}

    @commands.Cog.listener(
        "on_message"
    )
    async def run_custom_command(
        self,
        message: discord.Message,
    ) -> None:
        if message.guild is None:
            return

        if message.author.bot:
            return

        if not isinstance(
            message.author,
            discord.Member,
        ):
            return

        application_store = getattr(
            self.bot,
            "application_store",
            None,
        )

        if (
            isinstance(
                message.channel,
                discord.Thread,
            )
            and application_store is not None
        ):
            application = (
                await application_store
                .get_pending_application_by_questioning_thread(
                    message.channel.id
                )
            )

            if application is not None:
                return

        parsed = await self._parse_message(
            message
        )

        if parsed is None:
            return

        (
            command_name,
            raw_arguments,
            arguments,
            prefix,
        ) = parsed

        built_in_context = (
            await self.bot.get_context(
                message
            )
        )

        if built_in_context.valid:
            return

        custom_command = (
            await self.store.get(
                message.guild.id,
                command_name,
            )
        )

        if (
            custom_command is None
            or not custom_command.enabled
        ):
            return

        member_level = (
            await get_member_level_name(
                message.author,
                self.bot.permission_store,
            )
        )

        if not member_meets_level(
            member_level,
            custom_command.required_level,
        ):
            await self._temporary_reply(
                message,
                (
                    "You need "
                    f"`{custom_command.required_level}` "
                    "permission to use this command."
                ),
            )
            return

        cooldown_remaining = (
            self._cooldown_remaining(
                custom_command,
                message.author.id,
            )
        )

        if cooldown_remaining:
            await self._temporary_reply(
                message,
                (
                    "That command is on cooldown "
                    f"for `{cooldown_remaining}` "
                    "more second(s)."
                ),
            )
            return

        cooldown_key = (
            message.guild.id,
            custom_command.name,
            message.author.id,
        )

        self.cooldowns[cooldown_key] = (
            time.monotonic()
        )

        target = (
            message.mentions[0]
            if message.mentions
            else message.author
        )

        context: dict[str, Any] = {
            "message": message,
            "command": custom_command,
            "raw_arguments": raw_arguments,
            "arguments": arguments,
            "prefix": prefix,
            "target": target,
        }

        last_response: (
            discord.Message | None
        ) = None

        for action in custom_command.actions:
            try:
                response = (
                    await self._run_action(
                        action,
                        context,
                        last_response,
                    )
                )

                if response is not None:
                    last_response = response

            except (
                discord.Forbidden,
                discord.HTTPException,
                ValueError,
                TypeError,
            ):
                self.bot.log.exception(
                    (
                        "Custom command action "
                        "failed: %s/%s"
                    ),
                    message.guild.id,
                    custom_command.name,
                )

        if custom_command.delete_trigger:
            await self._safe_delete(
                message
            )

    async def _run_action(
        self,
        action: dict[str, Any],
        context: dict[str, Any],
        last_response: discord.Message | None,
    ) -> discord.Message | None:
        action_type = action.get(
            "type"
        )

        data = action.get(
            "data",
            {},
        )

        if not isinstance(
            data,
            dict,
        ):
            return None

        message: discord.Message = (
            context["message"]
        )

        if action_type == SEND_MESSAGE:
            content = self._render_text(
                str(
                    data.get(
                        "content",
                        "",
                    )
                ),
                context,
            )[:2000]

            if data.get("reply"):
                return await message.reply(
                    content,
                    mention_author=False,
                )

            return await message.channel.send(
                content
            )

        if action_type == SEND_EMBED:
            colour_value = data.get(
                "colour"
            )

            colour = (
                discord.Colour(
                    colour_value
                )
                if isinstance(
                    colour_value,
                    int,
                )
                else discord.Colour.blurple()
            )

            title = self._render_text(
                str(
                    data.get(
                        "title",
                        "",
                    )
                ),
                context,
            )[:256]

            description = self._render_text(
                str(
                    data.get(
                        "description",
                        "",
                    )
                ),
                context,
            )[:4096]

            embed = discord.Embed(
                title=title or None,
                description=(
                    description or None
                ),
                colour=colour,
            )

            author = self._render_text(
                str(
                    data.get(
                        "author",
                        "",
                    )
                ),
                context,
            )[:256]

            footer = self._render_text(
                str(
                    data.get(
                        "footer",
                        "",
                    )
                ),
                context,
            )[:2048]

            thumbnail = self._render_text(
                str(
                    data.get(
                        "thumbnail",
                        "",
                    )
                ),
                context,
            )

            image = self._render_text(
                str(
                    data.get(
                        "image",
                        "",
                    )
                ),
                context,
            )

            if author:
                embed.set_author(
                    name=author
                )

            if footer:
                embed.set_footer(
                    text=footer
                )

            if thumbnail:
                embed.set_thumbnail(
                    url=thumbnail
                )

            if image:
                embed.set_image(
                    url=image
                )

            fields = data.get(
                "fields",
                [],
            )

            if isinstance(fields, list):
                for field in fields[:25]:
                    if not isinstance(
                        field,
                        dict,
                    ):
                        continue

                    field_name = (
                        self._render_text(
                            str(
                                field.get(
                                    "name",
                                    "",
                                )
                            ),
                            context,
                        )[:256]
                    )

                    field_value = (
                        self._render_text(
                            str(
                                field.get(
                                    "value",
                                    "",
                                )
                            ),
                            context,
                        )[:1024]
                    )

                    if (
                        not field_name
                        or not field_value
                    ):
                        continue

                    embed.add_field(
                        name=field_name,
                        value=field_value,
                        inline=bool(
                            field.get(
                                "inline",
                                False,
                            )
                        ),
                    )

            if (
                not embed.title
                and not embed.description
                and not embed.fields
            ):
                embed.description = "\u200b"

            if data.get("reply"):
                return await message.reply(
                    embed=embed,
                    mention_author=False,
                )

            return await message.channel.send(
                embed=embed
            )

        if action_type == ADD_REACTION:
            reaction_target = (
                last_response
                if data.get("target")
                == "response"
                else message
            )

            emoji = self._render_text(
                str(
                    data.get(
                        "emoji",
                        "",
                    )
                ),
                context,
            ).strip()

            if (
                reaction_target is not None
                and emoji
            ):
                await reaction_target.add_reaction(
                    emoji
                )

        if action_type in {
            ADD_ROLE,
            REMOVE_ROLE,
        }:
            try:
                role_id = int(
                    data.get(
                        "role_id",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                return None

            role = message.guild.get_role(
                role_id
            )

            member = (
                context["target"]
                if data.get("target")
                == "target"
                else message.author
            )

            if role is None:
                return None

            if (
                role.is_default()
                or role.managed
            ):
                return None

            bot_member = message.guild.me

            if bot_member is None:
                return None

            if role >= bot_member.top_role:
                return None

            reason = (
                "Custom command: "
                f"{context['prefix']}"
                f"{context['command'].name}"
            )

            if action_type == ADD_ROLE:
                await member.add_roles(
                    role,
                    reason=reason,
                )

            else:
                await member.remove_roles(
                    role,
                    reason=reason,
                )

        if action_type == DELETE_MESSAGE:
            delete_target = (
                last_response
                if data.get("target")
                == "response"
                else message
            )

            if delete_target is None:
                return None

            try:
                delay = float(
                    data.get(
                        "delay",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                delay = 0

            delay = max(
                0,
                min(
                    delay,
                    86400,
                ),
            )

            if delay:
                asyncio.create_task(
                    self._delete_later(
                        delete_target,
                        delay,
                    )
                )

            else:
                await self._safe_delete(
                    delete_target
                )

        return None

    async def _parse_message(
        self,
        message: discord.Message,
    ) -> tuple[
        str,
        str,
        list[str],
        str,
    ] | None:
        prefixes = await self.bot.get_prefix(
            message
        )

        if isinstance(
            prefixes,
            str,
        ):
            prefix_values = [prefixes]

        else:
            prefix_values = list(
                prefixes
            )

        prefix = next(
            (
                item
                for item in sorted(
                    prefix_values,
                    key=len,
                    reverse=True,
                )
                if message.content.startswith(
                    item
                )
            ),
            None,
        )

        if prefix is None:
            return None

        content = message.content[
            len(prefix):
        ].strip()

        if not content:
            return None

        (
            command_name,
            separator,
            raw_arguments,
        ) = content.partition(" ")

        try:
            command_name = (
                self.store.normalise_name(
                    command_name
                )
            )

        except ValueError:
            return None

        raw_arguments = (
            raw_arguments.strip()
            if separator
            else ""
        )

        arguments = (
            raw_arguments.split()
            if raw_arguments
            else []
        )

        return (
            command_name,
            raw_arguments,
            arguments,
            prefix,
        )

    def _render_text(
        self,
        text: str,
        context: dict[str, Any],
    ) -> str:
        message: discord.Message = (
            context["message"]
        )

        command: CustomCommand = (
            context["command"]
        )

        target: discord.Member = (
            context["target"]
        )

        arguments: list[str] = (
            context["arguments"]
        )

        replacements = {
            "{user}": (
                message.author.name
            ),
            "{display_name}": (
                message.author.display_name
            ),
            "{mention}": (
                message.author.mention
            ),
            "{user_id}": str(
                message.author.id
            ),
            "{target}": (
                target.display_name
            ),
            "{target_mention}": (
                target.mention
            ),
            "{target_id}": str(
                target.id
            ),
            "{server}": (
                message.guild.name
            ),
            "{server_id}": str(
                message.guild.id
            ),
            "{member_count}": str(
                message.guild.member_count
                or 0
            ),
            "{channel}": getattr(
                message.channel,
                "mention",
                str(message.channel),
            ),
            "{channel_id}": str(
                message.channel.id
            ),
            "{args}": context[
                "raw_arguments"
            ],
            "{command}": (
                command.name
            ),
            "{prefix}": context[
                "prefix"
            ],
            "{newline}": "\n",
        }

        for (
            placeholder,
            value,
        ) in replacements.items():
            text = text.replace(
                placeholder,
                value,
            )

        def replace_argument(
            match: re.Match[str],
        ) -> str:
            argument_number = int(
                match.group(1)
            )

            argument_index = (
                argument_number - 1
            )

            if not (
                0
                <= argument_index
                < len(arguments)
            ):
                return ""

            return arguments[
                argument_index
            ]

        text = (
            ARGUMENT_PLACEHOLDER_RE.sub(
                replace_argument,
                text,
            )
        )

        def replace_random(
            match: re.Match[str],
        ) -> str:
            choices = [
                choice
                for choice
                in match.group(1).split("|")
                if choice
            ]

            if not choices:
                return ""

            return random.choice(
                choices
            )

        return (
            RANDOM_PLACEHOLDER_RE.sub(
                replace_random,
                text,
            )
        )

    def _cooldown_remaining(
        self,
        command: CustomCommand,
        user_id: int,
    ) -> int:
        if command.cooldown_seconds <= 0:
            return 0

        key = (
            command.guild_id,
            command.name,
            user_id,
        )

        last_used = self.cooldowns.get(
            key
        )

        if last_used is None:
            return 0

        remaining = (
            command.cooldown_seconds
            - (
                time.monotonic()
                - last_used
            )
        )

        return max(
            0,
            int(remaining + 0.999),
        )

    async def _temporary_reply(
        self,
        message: discord.Message,
        content: str,
    ) -> None:
        response = await message.reply(
            content,
            mention_author=False,
        )

        asyncio.create_task(
            self._delete_later(
                response,
                5,
            )
        )

    @staticmethod
    async def _safe_delete(
        message: discord.Message,
    ) -> None:
        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
            discord.HTTPException,
        ):
            pass

    @classmethod
    async def _delete_later(
        cls,
        message: discord.Message,
        delay: float,
    ) -> None:
        await asyncio.sleep(
            delay
        )

        await cls._safe_delete(
            message
        )

    @custom_command_group.command(
        name="create",
        description=(
            "Create a custom command."
        ),
    )
    @app_commands.guild_only()
    @app_commands.choices(
        permission=LEVEL_CHOICES
    )
    async def create_command(
        self,
        interaction: discord.Interaction,
        name: str,
        description: str = "",
        permission: (
            app_commands.Choice[str]
            | None
        ) = None,
        cooldown_seconds: (
            app_commands.Range[
                int,
                0,
                86400,
            ]
        ) = 0,
        delete_trigger: bool = False,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            name = (
                self.store.normalise_name(
                    name
                )
            )

            if self.bot.get_command(name):
                raise ValueError(
                    "That name conflicts with "
                    "a built-in prefix command."
                )

            await self.store.create(
                interaction.guild.id,
                name,
                description,
                interaction.user.id,
                (
                    permission.value
                    if permission
                    else LEVEL_PUBLIC
                ),
                cooldown_seconds,
                delete_trigger,
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Created "
                    f"`{self.bot.config.prefix}"
                    f"{name}`."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="delete",
        description=(
            "Delete a custom command."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def delete_command(
        self,
        interaction: discord.Interaction,
        command: str,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        deleted = await self.store.delete(
            interaction.guild.id,
            command,
        )

        response = (
            f"Deleted `{command}`."
            if deleted
            else (
                "Could not find "
                f"`{command}`."
            )
        )

        await (
            interaction.response
            .send_message(
                response,
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="list",
        description=(
            "List custom commands."
        ),
    )
    @app_commands.guild_only()
    async def list_commands(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        custom_commands = (
            await self.store.list(
                interaction.guild.id
            )
        )

        if not custom_commands:
            await (
                interaction.response
                .send_message(
                    (
                        "No custom commands "
                        "exist."
                    ),
                    ephemeral=True,
                )
            )
            return

        embed = discord.Embed(
            title="Custom Commands",
            colour=(
                discord.Colour.blurple()
            ),
        )

        for command in custom_commands[:25]:
            embed.add_field(
                name=(
                    f"{self.bot.config.prefix}"
                    f"{command.name}"
                ),
                value=(
                    f"{command.description or '*No description*'}\n"
                    f"`{command.required_level}` • "
                    f"`{command.cooldown_seconds}s` • "
                    f"`{len(command.actions)} action(s)` • "
                    f"enabled: `{command.enabled}`"
                )[:1024],
                inline=False,
            )

        await (
            interaction.response
            .send_message(
                embed=embed,
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="view",
        description=(
            "View a custom command."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def view_command(
        self,
        interaction: discord.Interaction,
        command: str,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        custom_command = (
            await self.store.get(
                interaction.guild.id,
                command,
            )
        )

        if custom_command is None:
            await (
                interaction.response
                .send_message(
                    "Command not found.",
                    ephemeral=True,
                )
            )
            return

        action_lines: list[str] = []

        for (
            index,
            action,
        ) in enumerate(
            custom_command.actions,
            start=1,
        ):
            data = action.get(
                "data",
                {},
            )

            if not isinstance(
                data,
                dict,
            ):
                data = {}

            summary = str(
                data.get("content")
                or data.get("title")
                or data.get("emoji")
                or data
            )

            action_lines.append(
                (
                    f"**{index}. "
                    f"`{action.get('type')}`**\n"
                    f"{summary[:300]}"
                )
            )

        embed = discord.Embed(
            title=(
                f"{self.bot.config.prefix}"
                f"{custom_command.name}"
            ),
            description=(
                custom_command.description
                or "No description."
            ),
            colour=(
                discord.Colour.blurple()
            ),
        )

        embed.add_field(
            name="Settings",
            value=(
                "Permission: "
                f"`{custom_command.required_level}`\n"
                "Cooldown: "
                f"`{custom_command.cooldown_seconds}s`\n"
                "Enabled: "
                f"`{custom_command.enabled}`\n"
                "Delete trigger: "
                f"`{custom_command.delete_trigger}`"
            ),
            inline=False,
        )

        embed.add_field(
            name="Actions",
            value=(
                "\n\n".join(
                    action_lines
                )[:1024]
                if action_lines
                else "No actions."
            ),
            inline=False,
        )

        await (
            interaction.response
            .send_message(
                embed=embed,
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="settings",
        description=(
            "Change command settings."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    @app_commands.choices(
        permission=LEVEL_CHOICES
    )
    async def command_settings(
        self,
        interaction: discord.Interaction,
        command: str,
        description: str | None = None,
        enabled: bool | None = None,
        permission: (
            app_commands.Choice[str]
            | None
        ) = None,
        cooldown_seconds: (
            app_commands.Range[
                int,
                0,
                86400,
            ]
            | None
        ) = None,
        delete_trigger: bool | None = None,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        changed = await self.store.update(
            interaction.guild.id,
            command,
            description=description,
            enabled=enabled,
            required_level=(
                permission.value
                if permission
                else None
            ),
            cooldown_seconds=(
                cooldown_seconds
            ),
            delete_trigger=(
                delete_trigger
            ),
        )

        await (
            interaction.response
            .send_message(
                (
                    "Command updated."
                    if changed
                    else "Nothing changed."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-message",
        description=(
            "Add a message action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def add_message(
        self,
        interaction: discord.Interaction,
        command: str,
        content: str,
        reply: bool = False,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    SEND_MESSAGE,
                    {
                        "content": content,
                        "reply": reply,
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-embed",
        description=(
            "Add an embed action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def add_embed(
        self,
        interaction: discord.Interaction,
        command: str,
        title: str = "",
        description: str = "",
        colour: str | None = None,
        reply: bool = False,
        author: str = "",
        footer: str = "",
        thumbnail_url: str = "",
        image_url: str = "",
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    SEND_EMBED,
                    {
                        "title": title,
                        "description": description,
                        "colour": parse_colour(
                            colour
                        ),
                        "reply": reply,
                        "author": author,
                        "footer": footer,
                        "thumbnail": (
                            thumbnail_url
                        ),
                        "image": image_url,
                        "fields": [],
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-embed-field",
        description=(
            "Add a field to an "
            "embed action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def add_embed_field(
        self,
        interaction: discord.Interaction,
        command: str,
        action_number: (
            app_commands.Range[
                int,
                1,
                100,
            ]
        ),
        name: str,
        value: str,
        inline: bool = False,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            await self.store.add_embed_field(
                interaction.guild.id,
                command,
                action_number,
                {
                    "name": name,
                    "value": value,
                    "inline": inline,
                },
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                "Field added.",
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-reaction",
        description=(
            "Add a reaction action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    @app_commands.choices(
        target=MESSAGE_TARGET_CHOICES
    )
    async def add_reaction(
        self,
        interaction: discord.Interaction,
        command: str,
        emoji: str,
        target: app_commands.Choice[str],
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    ADD_REACTION,
                    {
                        "emoji": emoji,
                        "target": target.value,
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-role",
        description=(
            "Add a role action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    @app_commands.choices(
        target=MEMBER_TARGET_CHOICES
    )
    async def add_role(
        self,
        interaction: discord.Interaction,
        command: str,
        role: discord.Role,
        target: app_commands.Choice[str],
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        if (
            role.is_default()
            or role.managed
        ):
            await (
                interaction.response
                .send_message(
                    (
                        "That role cannot be "
                        "assigned by the bot."
                    ),
                    ephemeral=True,
                )
            )
            return

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    ADD_ROLE,
                    {
                        "role_id": role.id,
                        "target": target.value,
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="remove-role",
        description=(
            "Add a remove-role action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    @app_commands.choices(
        target=MEMBER_TARGET_CHOICES
    )
    async def remove_role(
        self,
        interaction: discord.Interaction,
        command: str,
        role: discord.Role,
        target: app_commands.Choice[str],
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    REMOVE_ROLE,
                    {
                        "role_id": role.id,
                        "target": target.value,
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="add-delete",
        description=(
            "Add a message deletion action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    @app_commands.choices(
        target=MESSAGE_TARGET_CHOICES
    )
    async def add_delete(
        self,
        interaction: discord.Interaction,
        command: str,
        target: app_commands.Choice[str],
        delay_seconds: (
            app_commands.Range[
                float,
                0,
                86400,
            ]
        ) = 0,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        try:
            action_number = (
                await self.store.add_action(
                    interaction.guild.id,
                    command,
                    DELETE_MESSAGE,
                    {
                        "target": target.value,
                        "delay": float(
                            delay_seconds
                        ),
                    },
                )
            )

        except ValueError as error:
            await (
                interaction.response
                .send_message(
                    str(error),
                    ephemeral=True,
                )
            )
            return

        await (
            interaction.response
            .send_message(
                (
                    "Added action "
                    f"#{action_number}."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="remove-action",
        description=(
            "Remove an action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def remove_action(
        self,
        interaction: discord.Interaction,
        command: str,
        action_number: (
            app_commands.Range[
                int,
                1,
                100,
            ]
        ),
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        removed = (
            await self.store.remove_action(
                interaction.guild.id,
                command,
                action_number,
            )
        )

        await (
            interaction.response
            .send_message(
                (
                    "Action removed."
                    if removed
                    else "Action not found."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="move-action",
        description=(
            "Move an action."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def move_action(
        self,
        interaction: discord.Interaction,
        command: str,
        action_number: (
            app_commands.Range[
                int,
                1,
                100,
            ]
        ),
        new_position: (
            app_commands.Range[
                int,
                1,
                100,
            ]
        ),
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        moved = await self.store.move_action(
            interaction.guild.id,
            command,
            action_number,
            new_position,
        )

        await (
            interaction.response
            .send_message(
                (
                    "Action moved."
                    if moved
                    else (
                        "Invalid action "
                        "position."
                    )
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="clear-actions",
        description=(
            "Remove all actions."
        ),
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(
        command=command_autocomplete
    )
    async def clear_actions(
        self,
        interaction: discord.Interaction,
        command: str,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        removed_count = (
            await self.store.clear_actions(
                interaction.guild.id,
                command,
            )
        )

        await (
            interaction.response
            .send_message(
                (
                    f"Removed {removed_count} "
                    "action(s)."
                ),
                ephemeral=True,
            )
        )

    @custom_command_group.command(
        name="placeholders",
        description=(
            "Show content placeholders."
        ),
    )
    @app_commands.guild_only()
    async def placeholders(
        self,
        interaction: discord.Interaction,
    ) -> None:
        await (
            interaction.response
            .send_message(
                (
                    "`{user}` `{display_name}` "
                    "`{mention}` `{user_id}`\n"
                    "`{target}` `{target_mention}` "
                    "`{target_id}`\n"
                    "`{server}` `{server_id}` "
                    "`{member_count}`\n"
                    "`{channel}` `{channel_id}` "
                    "`{args}`\n"
                    "`{arg1}` `{arg2}` "
                    "`{arg3}` ...\n"
                    "`{command}` `{prefix}` "
                    "`{newline}`\n"
                    "`{random:one|two|three}`"
                ),
                ephemeral=True,
            )
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        CustomCommandCog(bot)
    )