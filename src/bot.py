from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import BotConfig
from .commands.verification.setup_verify import VerifyView


class TFSBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        self.config = config

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=config.prefix,
            intents=intents,
            help_command=None,
        )

        self.log = logging.getLogger("TFSBot")

    async def setup_hook(self) -> None:
        self.log.info("setup_hook started.")

        self.log.info("Loading ping command...")
        await self.load_extension("src.commands.ping")

        self.log.info("Loading info command...")
        await self.load_extension("src.commands.info")

        # Only keep this if the file exists.
        self.log.info("Loading setupverify command...")
        await self.load_extension("src.commands.verification.setup_verify")

        self.log.info("Registering persistent views...")
        self.add_view(VerifyView())

        if self.config.test_guild_id:
            guild = discord.Object(id=self.config.test_guild_id)

            self.log.info("Copying global commands to test guild %s...", guild.id)
            self.tree.copy_global_to(guild=guild)

            self.log.info("Syncing slash commands to test guild %s...", guild.id)
            synced = await self.tree.sync(guild=guild)

            self.log.info("Synced %s slash commands to test guild %s.", len(synced), guild.id)
        else:
            self.log.info("Syncing global slash commands...")
            synced = await self.tree.sync()

            self.log.info("Synced %s global slash commands.", len(synced))

        self.log.info("setup_hook finished.")

    async def on_ready(self) -> None:
        assert self.user is not None
        self.log.info("Logged in as %s (%s).", self.user, self.user.id)

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        self.log.exception("Text command failed: %s", error)

        await ctx.reply(
            f"Command failed: `{error}`",
            mention_author=False,
        )
