from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from .config import BotConfig
from .services.application_store import ApplicationStore
from .services.dm_template_store import DmTemplateStore
from .services.forms.form_store import FormStore
from .services.guild_settings import GuildSettingsStore
from .services.invite_tracker import InviteTrackerStore
from .services.permission_store import PermissionStore
from .utils.permissions import PermissionCommandTree, PermissionDenied
from .webui.app import start_webui
from .services.custom_commands.store import CustomCommandStore


class TFSBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        self.config = config

        self.log = logging.getLogger("TFSBot")

        self.guild_settings = GuildSettingsStore(config.application_db_path)
        self.application_store = ApplicationStore(config.application_db_path)
        self.custom_command_store = CustomCommandStore(config.application_db_path)
        self.form_store = FormStore(config.application_db_path)
        self.permission_store = PermissionStore(config.application_db_path)
        self.dm_template_store = DmTemplateStore(config.application_db_path)
        self.invite_tracker = InviteTrackerStore(config.application_db_path)
        self.invite_tracker_ready = False
        self.verification_departure_suppression: set[tuple[int, int]] = set()

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
            tree_cls=PermissionCommandTree,
        )

        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.application_store.initialise()
        self.log.info("Application database initialised.")
        
        await self.custom_command_store.initialise()
        self.log.info("Custom command database initialised.")

        self.guild_settings.initialise()
        self.log.info("Guild settings database initialised.")

        await self.form_store.initialise()
        self.log.info("Form database initialised.")

        await self.permission_store.initialise()
        self.log.info("Permission database initialised.")

        await self.dm_template_store.initialise()
        self.log.info("DM template database initialised.")

        await self.invite_tracker.initialise()
        self.log.info("Invite tracker database initialised.")

        self.log.info("setup_hook started.")

        self.log.info("Loading ping command...")
        await self.load_extension("src.commands.ping")

        self.log.info("Loading info command...")
        await self.load_extension("src.commands.info")

        self.log.info("Loading permissions command...")
        await self.load_extension("src.commands.permissions.permissions")

        self.log.info("Loading setupverify command...")
        await self.load_extension("src.commands.verification.setup_verify")

        self.log.info("Loading form editor command...")
        await self.load_extension("src.commands.forms.form_editor")
        
        self.log.info("Loading custom commands...")
        await self.load_extension(
            "src.commands.custom_commands.custom_commands"
        )

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
        from .commands.verification.verification import (
            ApplicationQuestionControlsView,
            ApplicationReviewView,
        )

        pending_applications = await self.application_store.list_pending_applications()

        restored_count = 0

        for application in pending_applications:
            if (
                application.review_message_id is not None
                and application.questioning_thread_id is None
            ):
                self.add_view(
                    ApplicationReviewView(application.id),
                    message_id=application.review_message_id,
                )

                restored_count += 1

            if application.question_controls_message_id is not None:
                self.add_view(
                    ApplicationQuestionControlsView(application.id),
                    message_id=application.question_controls_message_id,
                )

                restored_count += 1

        self.log.info(
            "Restored %s pending application view(s).",
            restored_count,
        )


    async def on_message(self, message: discord.Message) -> None:
        if self.user is not None and message.author.id == self.user.id:
            return

        from .commands.verification.verification import handle_question_bridge_message

        handled = await handle_question_bridge_message(self, message)

        if handled:
            return

        if message.author.bot:
            return

        await self.process_commands(message)

    async def on_member_join(self, member: discord.Member) -> None:
        await self.invite_tracker.track_member_join(member)

    async def on_invite_create(self, invite: discord.Invite) -> None:
        await self.invite_tracker.sync_invite(invite)

    async def on_invite_delete(self, invite: discord.Invite) -> None:
        guild = invite.guild

        if guild is None:
            return

        await self.invite_tracker.delete_invite_snapshot(guild.id, invite.code)

    async def on_member_remove(self, member: discord.Member) -> None:
        from .commands.verification.verification import handle_member_left_during_verification

        await handle_member_left_during_verification(self, member)

    async def on_ready(self) -> None:
        if self.user is None:
            self.log.info("Bot is ready, but self.user is somehow None. Very normal.")
            return

        self.log.info(
            "Logged in as %s (%s).",
            self.user,
            self.user.id,
        )

        if not self.invite_tracker_ready:
            synced_count = 0

            for guild in self.guilds:
                if await self.invite_tracker.sync_guild_invites(guild):
                    synced_count += 1

            self.invite_tracker_ready = True
            self.log.info(
                "Invite cache synced for %s guild(s).",
                synced_count,
            )

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, PermissionDenied):
            await self._send_ephemeral_interaction_error(
                interaction,
                str(error),
            )
            return

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