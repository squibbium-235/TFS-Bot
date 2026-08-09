from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
    PermissionStore,
    normalise_command_key,
)
from src.utils.permissions import get_member_level_name


def get_permission_store(bot: commands.Bot) -> PermissionStore:
    permission_store = getattr(bot, "permission_store", None)

    if permission_store is None:
        raise RuntimeError("Permission store is not available.")

    return permission_store


async def command_key_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []

    permission_store = getattr(interaction.client, "permission_store", None)

    if permission_store is None:
        return []

    current = current.lower().strip()

    choices: list[app_commands.Choice[str]] = []

    command_keys = await permission_store.get_known_command_keys(interaction.guild.id)

    for command_key in command_keys:
        if current and current not in command_key:
            continue

        choices.append(
            app_commands.Choice(
                name=command_key,
                value=command_key,
            )
        )

    return choices[:25]


def role_display(
    guild: discord.Guild,
    role_id: int | None,
) -> str:
    if role_id is None:
        return "`Not set`"

    role = guild.get_role(role_id)

    if role is None:
        return f"`Unknown role: {role_id}`"

    return role.mention


async def build_permissions_embed(
    guild: discord.Guild,
    permission_store: PermissionStore,
) -> discord.Embed:
    embed = discord.Embed(
        title="Permission Settings",
        description=(
            f"Permission configuration for **{discord.utils.escape_markdown(guild.name)}**."
        ),
        colour=discord.Colour.blurple(),
    )

    if guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)

    role_ids = await permission_store.get_role_ids(guild.id)

    embed.add_field(
        name="Permission Roles",
        value=(
            f"**Staff:** {role_display(guild, role_ids.get(LEVEL_STAFF))}\n"
            f"**Admin:** {role_display(guild, role_ids.get(LEVEL_ADMIN))}\n"
            f"**Owner:** {role_display(guild, role_ids.get(LEVEL_OWNER))}"
        ),
        inline=False,
    )

    command_levels = await permission_store.get_all_command_levels(guild.id)

    lines = [
        f"`{command_key}` → `{level}`"
        for command_key, level in command_levels.items()
    ]

    chunks = [
        lines[index:index + 15]
        for index in range(0, len(lines), 15)
    ]

    for index, chunk in enumerate(chunks[:4], start=1):
        embed.add_field(
            name=f"Command Levels {index}",
            value="\n".join(chunk),
            inline=False,
        )

    embed.set_footer(
        text="Bot devs and the server owner count as owner level automatically."
    )

    return embed


class PermissionsCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    permissions_group = app_commands.Group(
        name="permissions",
        description="Configure bot permission levels.",
    )

    @permissions_group.command(
        name="view",
        description="View permission roles and command levels.",
    )
    @app_commands.guild_only()
    async def view_permissions(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)

        embed = await build_permissions_embed(
            guild=interaction.guild,
            permission_store=permission_store,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @permissions_group.command(
        name="my-level",
        description="Check your current bot permission level.",
    )
    @app_commands.guild_only()
    async def my_level(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)

        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Could not read your member permissions.",
                ephemeral=True,
            )
            return

        level = await get_member_level_name(
            member=interaction.user,
            permission_store=permission_store,
        )

        await interaction.response.send_message(
            f"Your bot permission level is `{level}`.",
            ephemeral=True,
        )

    @permissions_group.command(
        name="set-role",
        description="Set the Discord role for a permission level.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        level=[
            app_commands.Choice(name="Staff", value=LEVEL_STAFF),
            app_commands.Choice(name="Admin", value=LEVEL_ADMIN),
            app_commands.Choice(name="Owner / Bot Dev", value=LEVEL_OWNER),
        ]
    )
    async def set_role(
        self,
        interaction: discord.Interaction,
        level: app_commands.Choice[str],
        role: discord.Role,
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)

        await permission_store.set_role(
            guild_id=interaction.guild.id,
            level=level.value,
            role_id=role.id,
        )

        await interaction.response.send_message(
            f"Set `{level.value}` permission role to {role.mention}.",
            ephemeral=True,
        )

    @permissions_group.command(
        name="clear-role",
        description="Clear the Discord role for a permission level.",
    )
    @app_commands.guild_only()
    @app_commands.choices(
        level=[
            app_commands.Choice(name="Staff", value=LEVEL_STAFF),
            app_commands.Choice(name="Admin", value=LEVEL_ADMIN),
            app_commands.Choice(name="Owner / Bot Dev", value=LEVEL_OWNER),
        ]
    )
    async def clear_role(
        self,
        interaction: discord.Interaction,
        level: app_commands.Choice[str],
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)

        await permission_store.clear_role(
            guild_id=interaction.guild.id,
            level=level.value,
        )

        await interaction.response.send_message(
            f"Cleared `{level.value}` permission role.",
            ephemeral=True,
        )

    @permissions_group.command(
        name="set-command",
        description="Set the minimum permission level for a command.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(command=command_key_autocomplete)
    @app_commands.choices(
        level=[
            app_commands.Choice(name="Public", value=LEVEL_PUBLIC),
            app_commands.Choice(name="Staff", value=LEVEL_STAFF),
            app_commands.Choice(name="Admin", value=LEVEL_ADMIN),
            app_commands.Choice(name="Owner / Bot Dev", value=LEVEL_OWNER),
        ]
    )
    async def set_command(
        self,
        interaction: discord.Interaction,
        command: str,
        level: app_commands.Choice[str],
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)
        command_key = normalise_command_key(command)

        await permission_store.set_command_level(
            guild_id=interaction.guild.id,
            command_key=command_key,
            level=level.value,
        )

        await interaction.response.send_message(
            f"Set `{command_key}` minimum level to `{level.value}`.",
            ephemeral=True,
        )

    @permissions_group.command(
        name="reset-command",
        description="Reset a command back to its default permission level.",
    )
    @app_commands.guild_only()
    @app_commands.autocomplete(command=command_key_autocomplete)
    async def reset_command(
        self,
        interaction: discord.Interaction,
        command: str,
    ) -> None:
        assert interaction.guild is not None

        permission_store = get_permission_store(self.bot)
        command_key = normalise_command_key(command)

        await permission_store.reset_command_level(
            guild_id=interaction.guild.id,
            command_key=command_key,
        )

        await interaction.response.send_message(
            f"Reset `{command_key}` to its default permission level.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PermissionsCommand(bot))