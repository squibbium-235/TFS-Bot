from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.verification.verification import VerifyView
from src.utils.embed_builder import EmbedFactory


def build_verify_embed() -> discord.Embed:
    embed = EmbedFactory.base(
        title="Welcome To The Furry Sanctuary!",
        description="Click the button below to **VERIFY**!",
    )

    embed.add_field(
        name="Please follow our rules at all times",
        value="Press the verify button to start your application.",
        inline=False,
    )

    return embed


class SetupVerifyCommand(commands.Cog):
    config_group = app_commands.Group(
        name="config",
        description="Configure verification settings.",
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @config_group.command(
        name="channels",
        description="Sets verification-related channels.",
    )
    @app_commands.describe(
        setting="Which verification channel to configure.",
        channel="The channel to use for this setting.",
    )
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="Verification panel", value="verification_panel"),
            app_commands.Choice(name="Review applications", value="review"),
            app_commands.Choice(name="Application logs", value="application_log"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config_channels(
        self,
        interaction: discord.Interaction,
        setting: app_commands.Choice[str],
        channel: discord.TextChannel,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.",
                ephemeral=True,
            )
            return

        if setting.value == "verification_panel":
            embed = build_verify_embed()

            await channel.send(embed=embed, view=VerifyView())

            await interaction.response.send_message(
                f"Verification panel posted in {channel.mention}.",
                ephemeral=True,
            )
            return

        if setting.value == "review":
            self.bot.guild_settings.set_review_channel_id(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
            )

            await interaction.response.send_message(
                f"Verification applications will now be sent to {channel.mention}.",
                ephemeral=True,
            )
            return

        if setting.value == "application_log":
            self.bot.guild_settings.set_application_log_channel_id(
                guild_id=interaction.guild.id,
                channel_id=channel.id,
            )

            await interaction.response.send_message(
                f"Completed verification applications will now be logged in {channel.mention}.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Unknown channel setting.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_view(VerifyView())
    await bot.add_cog(SetupVerifyCommand(bot))