from __future__ import annotations

import discord

from discord import app_commands
from discord.ext import commands

from src.services.diagnostics import (
    STATUS_BAD,
    STATUS_GOOD,
    DiagnosticReport,
    build_diagnostic_report,
)
from src.utils.embed_builder import (
    EmbedFactory,
)


def status_icon(
    status: str,
) -> str:
    if status == STATUS_GOOD:
        return "✅"

    if status == STATUS_BAD:
        return "❌"

    return "⚠️"


def build_diagnostics_embed(
    guild: discord.Guild,
    report: DiagnosticReport,
) -> discord.Embed:
    if report.error_count:
        colour = discord.Colour.red()

    elif report.warning_count:
        colour = discord.Colour.orange()

    else:
        colour = discord.Colour.green()

    embed = EmbedFactory.base(
        title="TFSBot Diagnostics",
        description=(
            f"Health check for "
            f"**{discord.utils.escape_markdown(guild.name)}**.\n\n"
            f"✅ {report.good_count} healthy"
            f"  •  "
            f"⚠️ {report.warning_count} warning"
            f"  •  "
            f"❌ {report.error_count} error"
        ),
        colour=colour,
    )

    for item in report.items:
        value = (
            f"{status_icon(item.status)} "
            f"{item.value}"
        )

        if item.detail:
            value += (
                f"\n{item.detail}"
            )

        embed.add_field(
            name=item.label,
            value=value,
            inline=False,
        )

    return embed


class DiagnosticsCommand(
    commands.Cog
):
    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    @app_commands.command(
        name="diagnostics",
        description=(
            "Checks the bot and "
            "verification configuration."
        ),
    )
    @app_commands.guild_only()
    async def diagnostics(
        self,
        interaction: discord.Interaction,
    ) -> None:
        assert (
            interaction.guild
            is not None
        )

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        report = (
            await build_diagnostic_report(
                self.bot,
                interaction.guild,
            )
        )

        embed = (
            build_diagnostics_embed(
                interaction.guild,
                report,
            )
        )

        await interaction.followup.send(
            embed=embed,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        DiagnosticsCommand(
            bot
        )
    )