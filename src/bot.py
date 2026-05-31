from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .config import BotConfig
from .services.application_store import ApplicationStore
from .services.guild_settings import GuildSettingsStore
from .webui.app import start_webui


class TFSBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        self.config = config

        self.log = logging.getLogger("TFSBot")

        self.guild_settings = GuildSettingsStore()
        self.application_store = ApplicationStore(config.application_db_path)

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
        )

        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.application_store.initialise()
        self.log.info("Application database initialised.")

        self.log.info("setup_hook started.")

        self.log.info("Loading ping command...")
        await self.load_extension("src.commands.ping")

        self.log.info("Loading info command...")
        await self.load_extension("src.commands.info")

        self.log.info("Loading setupverify command...")
        await self.load_extension("src.commands.verification.setup_verify")

        if self.config.webui_enabled:
            self.log.info("Starting web UI...")
            start_webui(self)

        await self.restore_application_views()

        if self.config.test_guild_id:
            guild = discord.Object(id=self.config.test_guild_id)

            self.log.info(
                "Copying global commands to test guild %s...",
                self.config.test_guild_id,
            )

            self.tree.copy_global_to(guild=guild)

            self.log.info(
                "Syncing slash commands to test guild %s...",
                self.config.test_guild_id,
            )

            synced = await self.tree.sync(guild=guild)

            self.log.info(
                "Synced %s command(s) to test guild %s.",
                len(synced),
                self.config.test_guild_id,
            )

        else:
            self.log.info("Syncing global slash commands...")

            synced = await self.tree.sync()

            self.log.info(
                "Synced %s global command(s).",
                len(synced),
            )

    async def restore_application_views(self) -> None:
        from .commands.verification.verification import ApplicationReviewView

        pending_applications = await self.application_store.list_pending_applications()

        restored_count = 0

        for application in pending_applications:
            if application.review_message_id is None:
                continue

            self.add_view(
                ApplicationReviewView(application.id),
                message_id=application.review_message_id,
            )

            restored_count += 1

        self.log.info(
            "Restored %s pending application view(s).",
            restored_count,
        )

    async def on_ready(self) -> None:
        if self.user is None:
            self.log.info("Bot is ready, but self.user is somehow None. Very normal.")
            return

        self.log.info(
            "Logged in as %s (%s).",
            self.user,
            self.user.id,
        )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await self._send_ephemeral_interaction_error(
                interaction,
                "You do not have permission to use this command.",
            )
            return

        if isinstance(error, app_commands.BotMissingPermissions):
            await self._send_ephemeral_interaction_error(
                interaction,
                "I do not have the permissions needed to do that.",
            )
            return

        if isinstance(error, app_commands.CheckFailure):
            await self._send_ephemeral_interaction_error(
                interaction,
                "You cannot use this command here.",
            )
            return

        self.log.exception(
            "Unhandled app command error: %s",
            error,
            exc_info=error,
        )

        await self._send_ephemeral_interaction_error(
            interaction,
            "Something went wrong while running that command.",
        )

    async def _send_ephemeral_interaction_error(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(
                    message,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    message,
                    ephemeral=True,
                )

        except discord.HTTPException:
            self.log.exception(
                "Failed to send interaction error response.",
            )

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        self.log.exception(
            "Unhandled prefix command error: %s",
            error,
            exc_info=error,
        )

        try:
            await ctx.reply(
                "Something went wrong while running that command.",
                mention_author=False,
            )

        except discord.HTTPException:
            self.log.exception(
                "Failed to send prefix command error response.",
            )