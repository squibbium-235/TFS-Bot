from __future__ import annotations

import platform
import time

import discord
from discord import app_commands
from discord.ext import commands

from ..utils.embed_builder import EmbedFactory


STARTED_AT = time.monotonic()


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)

    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}d {hours}h {minutes}m"

    if hours:
        return f"{hours}h {minutes}m"

    return f"{minutes}m {seconds}s"


def build_info_embed(bot: commands.Bot, guild: discord.Guild | None) -> discord.Embed:
    uptime = format_uptime(time.monotonic() - STARTED_AT)

    embed = EmbedFactory.base(
        title="TFSBot Info - \"This bot serves the server\"",
        description="General bot status and runtime information.",
    )

    embed.add_field(name="Bot", value=bot.user.mention if bot.user else "Unknown", inline=True)
    embed.add_field(name="Python", value=platform.python_version(), inline=True)
    embed.add_field(name="discord.py", value=discord.__version__, inline=True)
    embed.add_field(name="Uptime", value=uptime, inline=True)
    embed.add_field(name="Server", value=guild.name if guild else "DM / Unknown", inline=True)

    if guild:
        embed.add_field(name="Members", value=str(guild.member_count or "Unknown"), inline=True)

    return embed


class InfoCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="info", description="Shows information about the bot.")
    async def info_slash(self, interaction: discord.Interaction) -> None:
        embed = build_info_embed(self.bot, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="info")
    async def info_text(self, ctx: commands.Context) -> None:
        embed = build_info_embed(self.bot, ctx.guild)
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCommand(bot))
