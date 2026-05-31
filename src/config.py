from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WebUiCredential:
    username: str
    password: str


@dataclass(frozen=True)
class BotConfig:
    discord_token: str
    prefix: str = "!"
    test_guild_id: int | None = None

    webui_enabled: bool = False
    webui_host: str = "127.0.0.1"
    webui_port: int = 5050
    webui_credentials: tuple[WebUiCredential, ...] = ()
    application_db_path: str = "data/tfsbot.sqlite3"

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

        webui_enabled = os.getenv("WEBUI_ENABLED", "false").lower() == "true"
        webui_host = os.getenv("WEBUI_HOST", "127.0.0.1")
        webui_port = int(os.getenv("WEBUI_PORT", "5050"))

        webui_credentials: list[WebUiCredential] = []

        application_db_path = os.getenv(
            "APPLICATION_DB_PATH",
            "data/tfsbot.sqlite3",
        )

        for index in range(1, 3):
            username = os.getenv(f"WEBUI_USER_{index}_USERNAME")
            password = os.getenv(f"WEBUI_USER_{index}_PASSWORD")

            if username or password:
                if not username:
                    raise RuntimeError(f"WEBUI_USER_{index}_USERNAME is missing.")

                if not password:
                    raise RuntimeError(f"WEBUI_USER_{index}_PASSWORD is missing.")

                webui_credentials.append(
                    WebUiCredential(
                        username=username,
                        password=password,
                    )
                )

        if webui_enabled and not webui_credentials:
            raise RuntimeError(
                "WEBUI_ENABLED is true, but no web UI users are configured."
            )

        return BotConfig(
            discord_token=token,
            prefix=prefix,
            test_guild_id=test_guild_id,
            webui_enabled=webui_enabled,
            webui_host=webui_host,
            webui_port=webui_port,
            webui_credentials=tuple(webui_credentials),
            application_db_path=application_db_path,
        )