from __future__ import annotations

import copy
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.services.permission_store import (
    DEFAULT_COMMAND_LEVELS,
    LEVEL_OWNER,
)
from src.services.welcome_service import (
    build_welcome_embed,
    send_welcome_message,
)
from src.services.welcome_store import (
    WelcomeSettings,
    WelcomeStore,
)


DEFAULT_COMMAND_LEVELS.setdefault(
    "welcome",
    LEVEL_OWNER,
)


PLACEHOLDER_HELP = (
    "`{user}` mention • `{username}` username • "
    "`{display_name}` display name • `{server}` server • "
    "`{member_count}` member count • `{inviter}` inviter • "
    "`{avatar}` avatar URL"
)


def clean_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def parse_colour(
    raw_value: str | None,
) -> int | None:
    value = clean_optional_text(
        raw_value
    )

    if value is None:
        return None

    value = value.removeprefix(
        "#"
    ).removeprefix(
        "0x"
    )

    if len(value) != 6:
        raise ValueError(
            "Colour must be a 6-digit hex "
            "value such as `#8CC8E8`."
        )

    try:
        return int(
            value,
            16,
        )

    except ValueError as caught:
        raise ValueError(
            "Colour must be a valid hex "
            "value such as `#8CC8E8`."
        ) from caught


def colour_text(
    embed_data: dict[str, Any],
) -> str:
    raw_colour = embed_data.get(
        "color"
    )

    if not isinstance(
        raw_colour,
        int,
    ):
        return ""

    return f"#{raw_colour:06X}"


def nested_url(
    embed_data: dict[str, Any],
    key: str,
) -> str:
    value = embed_data.get(key)

    if not isinstance(value, dict):
        return ""

    raw_url = value.get("url")

    return (
        str(raw_url)
        if raw_url
        else ""
    )


def author_value(
    embed_data: dict[str, Any],
    key: str,
) -> str:
    author = embed_data.get(
        "author"
    )

    if not isinstance(author, dict):
        return ""

    value = author.get(key)

    return str(value) if value else ""


def footer_text(
    embed_data: dict[str, Any],
) -> str:
    footer = embed_data.get(
        "footer"
    )

    if not isinstance(footer, dict):
        return ""

    value = footer.get(
        "text"
    )

    return str(value) if value else ""


def settings_summary_embed(
    guild: discord.Guild,
    settings: WelcomeSettings,
) -> discord.Embed:
    status = (
        "Enabled"
        if settings.enabled
        else "Disabled"
    )

    channel_text = (
        f"<#{settings.channel_id}>"
        if settings.channel_id
        is not None
        else "`Not configured`"
    )

    fields = settings.embed_data.get(
        "fields",
        [],
    )

    field_count = (
        len(fields)
        if isinstance(fields, list)
        else 0
    )

    embed = discord.Embed(
        title="Welcome Message Settings",
        description=(
            f"Configuration for "
            f"**{discord.utils.escape_markdown(guild.name)}**."
        ),
        colour=(
            discord.Colour.green()
            if settings.enabled
            else discord.Colour.dark_grey()
        ),
    )

    embed.add_field(
        name="Status",
        value=status,
        inline=True,
    )

    embed.add_field(
        name="Channel",
        value=channel_text,
        inline=True,
    )

    embed.add_field(
        name="Embed Fields",
        value=str(field_count),
        inline=True,
    )

    embed.add_field(
        name="Template Variables",
        value=PLACEHOLDER_HELP,
        inline=False,
    )

    embed.set_footer(
        text=(
            "Welcome messages are sent after a "
            "verification application is approved."
        )
    )

    return embed


async def get_preview_member(
    interaction: discord.Interaction,
    user: discord.Member | None,
) -> discord.Member:
    if user is not None:
        return user

    if isinstance(
        interaction.user,
        discord.Member,
    ):
        return interaction.user

    raise RuntimeError(
        "Could not resolve a member for preview."
    )


class WelcomeEmbedModal(
    discord.ui.Modal
):
    def __init__(
        self,
        *,
        store: WelcomeStore,
        guild: discord.Guild,
        settings: WelcomeSettings,
        channel_id: int | None = None,
        title: str,
    ) -> None:
        super().__init__(
            title=title
        )

        self.store = store
        self.guild = guild
        self.settings = settings

        self.channel_id = (
            channel_id
            if channel_id is not None
            else settings.channel_id
        )

        data = settings.embed_data

        self.embed_title = (
            discord.ui.TextInput(
                label="Embed title",
                default=str(
                    data.get(
                        "title",
                        "",
                    )
                ),
                placeholder=(
                    "Welcome {user}!"
                ),
                required=False,
                max_length=256,
            )
        )

        self.description = (
            discord.ui.TextInput(
                label="Description",
                default=str(
                    data.get(
                        "description",
                        "",
                    )
                ),
                placeholder=(
                    "Welcome to {server}!"
                ),
                style=(
                    discord.TextStyle.paragraph
                ),
                required=False,
                max_length=4000,
            )
        )

        self.colour = (
            discord.ui.TextInput(
                label="Colour",
                default=colour_text(
                    data
                ),
                placeholder="#8CC8E8",
                required=False,
                max_length=8,
            )
        )

        self.thumbnail_url = (
            discord.ui.TextInput(
                label="Thumbnail URL",
                default=nested_url(
                    data,
                    "thumbnail",
                ),
                placeholder=(
                    "https://... or {avatar}"
                ),
                required=False,
                max_length=2000,
            )
        )

        self.image_url = (
            discord.ui.TextInput(
                label="Large image URL",
                default=nested_url(
                    data,
                    "image",
                ),
                placeholder="https://...",
                required=False,
                max_length=2000,
            )
        )

        self.add_item(
            self.embed_title
        )

        self.add_item(
            self.description
        )

        self.add_item(
            self.colour
        )

        self.add_item(
            self.thumbnail_url
        )

        self.add_item(
            self.image_url
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        try:
            data = copy.deepcopy(
                self.settings.embed_data
            )

            title = clean_optional_text(
                str(self.embed_title.value)
            )

            description = clean_optional_text(
                str(self.description.value)
            )

            thumbnail_url = clean_optional_text(
                str(self.thumbnail_url.value)
            )

            image_url = clean_optional_text(
                str(self.image_url.value)
            )

            colour = parse_colour(
                str(self.colour.value)
            )

            if title is None:
                data.pop(
                    "title",
                    None,
                )
            else:
                data["title"] = title

            if description is None:
                data.pop(
                    "description",
                    None,
                )
            else:
                data["description"] = (
                    description
                )

            if colour is None:
                data.pop(
                    "color",
                    None,
                )
            else:
                data["color"] = colour

            if thumbnail_url is None:
                data.pop(
                    "thumbnail",
                    None,
                )
            else:
                data["thumbnail"] = {
                    "url": thumbnail_url,
                }

            if image_url is None:
                data.pop(
                    "image",
                    None,
                )
            else:
                data["image"] = {
                    "url": image_url,
                }

            if not any(
                key in data
                for key in (
                    "title",
                    "description",
                    "author",
                    "fields",
                    "image",
                    "thumbnail",
                    "footer",
                )
            ):
                raise ValueError(
                    "The welcome embed cannot "
                    "be completely empty."
                )

            saved = await self.store.save_config(
                guild_id=self.guild.id,
                channel_id=self.channel_id,
                embed_data=data,
            )

            member = await get_preview_member(
                interaction,
                None,
            )

            preview = await build_welcome_embed(
                bot=interaction.client,
                guild=self.guild,
                member=member,
                embed_data=(
                    saved.embed_data
                ),
            )

            await interaction.response.send_message(
                "Welcome embed saved. Preview:",
                embed=preview,
                ephemeral=True,
            )

        except Exception as caught_error:
            await interaction.response.send_message(
                str(caught_error),
                ephemeral=True,
            )


class WelcomeExtrasModal(
    discord.ui.Modal
):
    def __init__(
        self,
        *,
        store: WelcomeStore,
        guild: discord.Guild,
        settings: WelcomeSettings,
    ) -> None:
        super().__init__(
            title="Welcome Embed Extras"
        )

        self.store = store
        self.guild = guild
        self.settings = settings

        data = settings.embed_data

        self.author_name = (
            discord.ui.TextInput(
                label="Author name",
                default=author_value(
                    data,
                    "name",
                ),
                placeholder=(
                    "Leave blank for no author"
                ),
                required=False,
                max_length=256,
            )
        )

        self.author_icon_url = (
            discord.ui.TextInput(
                label="Author icon URL",
                default=author_value(
                    data,
                    "icon_url",
                ),
                placeholder=(
                    "https://... or {avatar}"
                ),
                required=False,
                max_length=2000,
            )
        )

        self.footer = (
            discord.ui.TextInput(
                label="Footer",
                default=footer_text(
                    data
                ),
                placeholder=(
                    "Leave blank for no footer"
                ),
                required=False,
                max_length=2000,
            )
        )

        self.add_item(
            self.author_name
        )

        self.add_item(
            self.author_icon_url
        )

        self.add_item(
            self.footer
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        data = copy.deepcopy(
            self.settings.embed_data
        )

        author_name = clean_optional_text(
            str(self.author_name.value)
        )

        author_icon_url = clean_optional_text(
            str(self.author_icon_url.value)
        )

        footer = clean_optional_text(
            str(self.footer.value)
        )

        if author_name is None:
            data.pop(
                "author",
                None,
            )
        else:
            author: dict[str, str] = {
                "name": author_name,
            }

            if author_icon_url:
                author["icon_url"] = (
                    author_icon_url
                )

            data["author"] = author

        if footer is None:
            data.pop(
                "footer",
                None,
            )
        else:
            data["footer"] = {
                "text": footer,
            }

        saved = await self.store.set_embed_data(
            guild_id=self.guild.id,
            embed_data=data,
        )

        member = await get_preview_member(
            interaction,
            None,
        )

        preview = await build_welcome_embed(
            bot=interaction.client,
            guild=self.guild,
            member=member,
            embed_data=saved.embed_data,
        )

        await interaction.response.send_message(
            "Welcome embed extras saved. Preview:",
            embed=preview,
            ephemeral=True,
        )


class WelcomeFieldModal(
    discord.ui.Modal
):
    def __init__(
        self,
        *,
        store: WelcomeStore,
        guild: discord.Guild,
        settings: WelcomeSettings,
    ) -> None:
        super().__init__(
            title="Add Welcome Embed Field"
        )

        self.store = store
        self.guild = guild
        self.settings = settings

        self.field_name = (
            discord.ui.TextInput(
                label="Field name",
                required=True,
                max_length=256,
            )
        )

        self.field_value = (
            discord.ui.TextInput(
                label="Field value",
                style=(
                    discord.TextStyle.paragraph
                ),
                required=True,
                max_length=1024,
            )
        )

        self.inline = (
            discord.ui.TextInput(
                label="Inline? yes/no",
                default="no",
                required=True,
                max_length=5,
            )
        )

        self.add_item(
            self.field_name
        )

        self.add_item(
            self.field_value
        )

        self.add_item(
            self.inline
        )

    async def on_submit(
        self,
        interaction: discord.Interaction,
    ) -> None:
        data = copy.deepcopy(
            self.settings.embed_data
        )

        fields = data.get(
            "fields"
        )

        if not isinstance(fields, list):
            fields = []

        if len(fields) >= 25:
            await interaction.response.send_message(
                "Discord embeds can have at most 25 fields.",
                ephemeral=True,
            )
            return

        inline_text = str(
            self.inline.value
        ).strip().casefold()

        if inline_text not in {
            "yes",
            "y",
            "true",
            "no",
            "n",
            "false",
        }:
            await interaction.response.send_message(
                "Inline must be `yes` or `no`.",
                ephemeral=True,
            )
            return

        fields.append(
            {
                "name": str(
                    self.field_name.value
                ).strip(),
                "value": str(
                    self.field_value.value
                ).strip(),
                "inline": (
                    inline_text
                    in {
                        "yes",
                        "y",
                        "true",
                    }
                ),
            }
        )

        data["fields"] = fields

        saved = await self.store.set_embed_data(
            guild_id=self.guild.id,
            embed_data=data,
        )

        member = await get_preview_member(
            interaction,
            None,
        )

        preview = await build_welcome_embed(
            bot=interaction.client,
            guild=self.guild,
            member=member,
            embed_data=saved.embed_data,
        )

        await interaction.response.send_message(
            "Field added. Preview:",
            embed=preview,
            ephemeral=True,
        )


class WelcomeCommands(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
        store: WelcomeStore,
    ) -> None:
        self.bot = bot
        self.store = store

        self.log = logging.getLogger(
            "TFSBot.Welcome"
        )

    async def cog_load(self) -> None:
        self.approval_welcome_worker.start()

    async def cog_unload(self) -> None:
        self.approval_welcome_worker.cancel()

    welcome_group = app_commands.Group(
        name="welcome",
        description=(
            "Configure verification welcome messages."
        ),
    )

    @welcome_group.command(
        name="setup",
        description=(
            "Set the welcome channel and edit the welcome embed."
        ),
    )
    @app_commands.guild_only()
    async def setup_welcome(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        await interaction.response.send_modal(
            WelcomeEmbedModal(
                store=self.store,
                guild=interaction.guild,
                settings=settings,
                channel_id=channel.id,
                title="Set Up Welcome Message",
            )
        )

    @welcome_group.command(
        name="edit",
        description=(
            "Edit the main welcome embed content."
        ),
    )
    @app_commands.guild_only()
    async def edit_welcome(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        await interaction.response.send_modal(
            WelcomeEmbedModal(
                store=self.store,
                guild=interaction.guild,
                settings=settings,
                title="Edit Welcome Message",
            )
        )

    @welcome_group.command(
        name="extras",
        description=(
            "Edit welcome embed author and footer settings."
        ),
    )
    @app_commands.guild_only()
    async def edit_extras(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        await interaction.response.send_modal(
            WelcomeExtrasModal(
                store=self.store,
                guild=interaction.guild,
                settings=settings,
            )
        )

    @welcome_group.command(
        name="channel",
        description=(
            "Change the channel used for welcome messages."
        ),
    )
    @app_commands.guild_only()
    async def set_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild is not None

        await self.store.set_channel(
            guild_id=interaction.guild.id,
            channel_id=channel.id,
        )

        await interaction.response.send_message(
            f"Welcome channel set to {channel.mention}.",
            ephemeral=True,
        )

    @welcome_group.command(
        name="add-field",
        description=(
            "Add a field to the welcome embed."
        ),
    )
    @app_commands.guild_only()
    async def add_field(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        await interaction.response.send_modal(
            WelcomeFieldModal(
                store=self.store,
                guild=interaction.guild,
                settings=settings,
            )
        )

    @welcome_group.command(
        name="fields",
        description=(
            "View the configured welcome embed fields."
        ),
    )
    @app_commands.guild_only()
    async def view_fields(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        fields = settings.embed_data.get(
            "fields"
        )

        if (
            not isinstance(fields, list)
            or not fields
        ):
            await interaction.response.send_message(
                "No welcome embed fields are configured.",
                ephemeral=True,
            )
            return

        lines: list[str] = []

        for index, field in enumerate(
            fields,
            start=1,
        ):
            if not isinstance(field, dict):
                continue

            name = str(
                field.get(
                    "name",
                    "Unnamed field",
                )
            )

            lines.append(
                f"`{index}` • "
                f"{discord.utils.escape_markdown(name)}"
            )

        await interaction.response.send_message(
            "**Welcome embed fields**\n"
            + "\n".join(lines),
            ephemeral=True,
        )

    @welcome_group.command(
        name="remove-field",
        description=(
            "Remove a welcome embed field by its number."
        ),
    )
    @app_commands.guild_only()
    async def remove_field(
        self,
        interaction: discord.Interaction,
        number: app_commands.Range[int, 1, 25],
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        data = copy.deepcopy(
            settings.embed_data
        )

        fields = data.get(
            "fields"
        )

        if not isinstance(fields, list):
            fields = []

        index = number - 1

        if index >= len(fields):
            await interaction.response.send_message(
                "There is no field with that number.",
                ephemeral=True,
            )
            return

        removed = fields.pop(
            index
        )

        if fields:
            data["fields"] = fields
        else:
            data.pop(
                "fields",
                None,
            )

        await self.store.set_embed_data(
            guild_id=interaction.guild.id,
            embed_data=data,
        )

        removed_name = (
            str(removed.get("name"))
            if isinstance(removed, dict)
            else str(number)
        )

        await interaction.response.send_message(
            f"Removed field "
            f"`{discord.utils.escape_markdown(removed_name)}`.",
            ephemeral=True,
        )

    @welcome_group.command(
        name="clear-fields",
        description=(
            "Remove all fields from the welcome embed."
        ),
    )
    @app_commands.guild_only()
    async def clear_fields(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        data = copy.deepcopy(
            settings.embed_data
        )

        data.pop(
            "fields",
            None,
        )

        await self.store.set_embed_data(
            guild_id=interaction.guild.id,
            embed_data=data,
        )

        await interaction.response.send_message(
            "All welcome embed fields were removed.",
            ephemeral=True,
        )

    @welcome_group.command(
        name="enable",
        description=(
            "Enable welcome messages after verification approval."
        ),
    )
    @app_commands.guild_only()
    async def enable_welcome(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        if settings.channel_id is None:
            await interaction.response.send_message(
                "Set a welcome channel first with "
                "`/welcome setup` or `/welcome channel`.",
                ephemeral=True,
            )
            return

        settings = await self.store.set_enabled(
            guild_id=interaction.guild.id,
            enabled=True,
        )

        await interaction.response.send_message(
            f"Welcome messages enabled in "
            f"<#{settings.channel_id}>.",
            ephemeral=True,
        )

    @welcome_group.command(
        name="disable",
        description="Disable welcome messages.",
    )
    @app_commands.guild_only()
    async def disable_welcome(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        await self.store.set_enabled(
            guild_id=interaction.guild.id,
            enabled=False,
        )

        await interaction.response.send_message(
            "Welcome messages disabled.",
            ephemeral=True,
        )

    @welcome_group.command(
        name="status",
        description=(
            "View the current welcome message configuration."
        ),
    )
    @app_commands.guild_only()
    async def welcome_status(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        member = await get_preview_member(
            interaction,
            None,
        )

        preview = await build_welcome_embed(
            bot=self.bot,
            guild=interaction.guild,
            member=member,
            embed_data=settings.embed_data,
        )

        await interaction.response.send_message(
            embeds=[
                settings_summary_embed(
                    interaction.guild,
                    settings,
                ),
                preview,
            ],
            ephemeral=True,
        )

    @welcome_group.command(
        name="preview",
        description=(
            "Preview the welcome embed ephemerally."
        ),
    )
    @app_commands.guild_only()
    async def preview_welcome(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        member = await get_preview_member(
            interaction,
            user,
        )

        preview = await build_welcome_embed(
            bot=self.bot,
            guild=interaction.guild,
            member=member,
            embed_data=settings.embed_data,
        )

        await interaction.response.send_message(
            embed=preview,
            ephemeral=True,
        )

    @welcome_group.command(
        name="test",
        description=(
            "Send a test welcome to the configured channel."
        ),
    )
    @app_commands.guild_only()
    async def test_welcome(
        self,
        interaction: discord.Interaction,
        user: discord.Member | None = None,
    ) -> None:
        assert interaction.guild is not None

        settings = await self.store.get_settings(
            interaction.guild.id
        )

        if settings.channel_id is None:
            await interaction.response.send_message(
                "No welcome channel is configured.",
                ephemeral=True,
            )
            return

        member = await get_preview_member(
            interaction,
            user,
        )

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            message = await send_welcome_message(
                bot=self.bot,
                settings=settings,
                member=member,
            )

        except Exception as caught_error:
            await interaction.followup.send(
                f"Test failed: {caught_error}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Test welcome sent: {message.jump_url}",
            ephemeral=True,
        )

    @tasks.loop(seconds=1.0)
    async def approval_welcome_worker(
        self,
    ) -> None:
        settings_rows = (
            await self.store
            .list_enabled_settings()
        )

        for settings in settings_rows:
            if settings.enabled_since is None:
                continue

            approvals = (
                await self.store
                .list_unprocessed_approvals(
                    guild_id=settings.guild_id,
                    since=(
                        settings.enabled_since
                    ),
                )
            )

            for approval in approvals:
                guild = self.bot.get_guild(
                    approval.guild_id
                )

                if guild is None:
                    await self.store.mark_delivery(
                        application_id=(
                            approval.application_id
                        ),
                        guild_id=(
                            approval.guild_id
                        ),
                        user_id=(
                            approval.user_id
                        ),
                        result="skipped",
                        detail=(
                            "Guild is not available."
                        ),
                    )
                    continue

                member = guild.get_member(
                    approval.user_id
                )

                if member is None:
                    try:
                        member = await guild.fetch_member(
                            approval.user_id
                        )

                    except discord.HTTPException:
                        member = None

                if member is None:
                    await self.store.mark_delivery(
                        application_id=(
                            approval.application_id
                        ),
                        guild_id=(
                            approval.guild_id
                        ),
                        user_id=(
                            approval.user_id
                        ),
                        result="skipped",
                        detail=(
                            "Approved user is no longer "
                            "in the server."
                        ),
                    )
                    continue

                try:
                    message = await send_welcome_message(
                        bot=self.bot,
                        settings=settings,
                        member=member,
                    )

                except Exception as caught_error:
                    self.log.exception(
                        "Failed to send welcome for "
                        "application %s.",
                        approval.application_id,
                    )

                    await self.store.mark_delivery(
                        application_id=(
                            approval.application_id
                        ),
                        guild_id=(
                            approval.guild_id
                        ),
                        user_id=(
                            approval.user_id
                        ),
                        result="failed",
                        detail=str(
                            caught_error
                        ),
                    )
                    continue

                await self.store.mark_delivery(
                    application_id=(
                        approval.application_id
                    ),
                    guild_id=(
                        approval.guild_id
                    ),
                    user_id=(
                        approval.user_id
                    ),
                    result="sent",
                    message_id=message.id,
                )

    @approval_welcome_worker.before_loop
    async def before_welcome_worker(
        self,
    ) -> None:
        await self.bot.wait_until_ready()


async def setup(
    bot: commands.Bot,
) -> None:
    database_path = getattr(
        getattr(
            bot,
            "config",
            None,
        ),
        "application_db_path",
        "data/tfsbot.sqlite3",
    )

    store = WelcomeStore(
        database_path
    )

    await store.initialise()

    setattr(
        bot,
        "welcome_store",
        store,
    )

    await bot.add_cog(
        WelcomeCommands(
            bot,
            store,
        )
    )