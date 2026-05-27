from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class PingCommand(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Checks whether the bot is alive.")
    async def ping_slash(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong.")

    @commands.command(name="ping")
    async def ping_text(self, ctx: commands.Context) -> None:
        await ctx.reply("Pong.", mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PingCommand(bot))
