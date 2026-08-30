from __future__ import annotations

import re

import discord

from discord import app_commands
from discord.ext import commands


USER_ID_PATTERN = re.compile(
    r"^(?:<@!?)?(\d+)>?$"
)


async def resolve_profile_user(
    bot: commands.Bot,
    guild: discord.Guild,
    value: str,
) -> tuple[
    discord.User | discord.Member | None,
    str | None,
]:
    value = value.strip()

    id_match = USER_ID_PATTERN.fullmatch(
        value
    )

    if id_match is not None:
        user_id = int(
            id_match.group(1)
        )

        member = guild.get_member(
            user_id
        )

        if member is not None:
            return member, None

        cached_user = bot.get_user(
            user_id
        )

        if cached_user is not None:
            return cached_user, None

        try:
            user = await bot.fetch_user(
                user_id
            )

        except discord.NotFound:
            return (
                None,
                "I could not find a Discord "
                "user with that ID.",
            )

        except discord.HTTPException:
            return (
                None,
                "Discord could not resolve "
                "that user right now.",
            )

        return user, None

    search_value = value.casefold()

    matches: list[discord.Member] = []

    for member in guild.members:
        possible_names = {
            member.name.casefold(),
            member.display_name.casefold(),
        }

        if member.global_name:
            possible_names.add(
                member.global_name.casefold()
            )

        if search_value in possible_names:
            matches.append(
                member
            )

    if len(matches) == 1:
        return matches[0], None

    if len(matches) > 1:
        return (
            None,
            (
                "More than one member matches "
                f"`{value}`. Use their user ID "
                "or mention instead."
            ),
        )

    return (
        None,
        (
            f"I could not find `{value}` in "
            "this server. If they have left the "
            "server, please use their Discord user ID."
        ),
    )
    
class ModProfileCommands(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    @app_commands.command(
        name="modprofile",
        description=(
            "Open or create a user's "
            "moderation profile."
        ),
    )
    @app_commands.describe(
        user=(
            "User ID, username, "
            "display name, or mention."
        ),
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def modprofile(
        self,
        interaction: discord.Interaction,
        user: str,
    ) -> None:
        assert interaction.guild is not None

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        resolved_user, error = (
            await resolve_profile_user(
                self.bot,
                interaction.guild,
                user,
            )
        )

        if resolved_user is None:
            await interaction.followup.send(
                error
                or "That user could not be found.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            (
                "Resolved user: "
                f"{resolved_user.mention}\n"
                f"ID: `{resolved_user.id}`"
            ),
            ephemeral=True,
        )
    
async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        ModProfileCommands(
            bot
        )
    )