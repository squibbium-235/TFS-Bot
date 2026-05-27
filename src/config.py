from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    discord_token: str
    prefix: str = "!"
    test_guild_id: int | None = None

    @staticmethod
    def from_environment() -> "BotConfig":
        token = os.getenv("DISCORD_TOKEN")

        if not token:
            raise RuntimeError(
                "Missing DISCORD_TOKEN. Put it in your .env file or environment variables."
            )

        prefix = os.getenv("BOT_PREFIX", "!")

        test_guild_raw = os.getenv("TEST_GUILD_ID")
        test_guild_id = int(test_guild_raw) if test_guild_raw else None

        return BotConfig(
            discord_token=token,
            prefix=prefix,
            test_guild_id=test_guild_id,
        )
