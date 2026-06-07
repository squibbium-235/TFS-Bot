from __future__ import annotations

import os
from dataclasses import dataclass


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int_list(raw_value: str | None) -> tuple[int, ...]:
    if not raw_value:
        return ()

    values: list[int] = []

    for raw_item in raw_value.split(","):
        item = raw_item.strip()

        if not item:
            continue

        values.append(int(item))

    return tuple(values)


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
    webui_password_login_enabled: bool = True

    webui_discord_auth_enabled: bool = False
    discord_oauth_client_id: str = ""
    discord_oauth_client_secret: str = ""
    discord_oauth_redirect_uri: str = ""
    webui_discord_guild_id: int | None = None
    webui_discord_allowed_role_ids: tuple[int, ...] = ()
    webui_discord_owner_role_ids: tuple[int, ...] = ()
    webui_discord_viewer_role_ids: tuple[int, ...] = ()

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

        webui_enabled = env_bool("WEBUI_ENABLED", False)
        webui_host = os.getenv("WEBUI_HOST", "127.0.0.1")
        webui_port = int(os.getenv("WEBUI_PORT", "5050"))

        webui_password_login_enabled = env_bool("WEBUI_PASSWORD_LOGIN_ENABLED", True)
        webui_discord_auth_enabled = env_bool("WEBUI_AUTH_DISCORD_ENABLED", False)

        discord_oauth_client_id = os.getenv("DISCORD_OAUTH_CLIENT_ID", "").strip()
        discord_oauth_client_secret = os.getenv("DISCORD_OAUTH_CLIENT_SECRET", "").strip()
        discord_oauth_redirect_uri = os.getenv("DISCORD_OAUTH_REDIRECT_URI", "").strip()

        guild_id_raw = os.getenv("WEBUI_DISCORD_GUILD_ID", "").strip()
        webui_discord_guild_id = int(guild_id_raw) if guild_id_raw else None

        webui_discord_allowed_role_ids = parse_int_list(
            os.getenv("WEBUI_DISCORD_ALLOWED_ROLE_IDS")
        )

        webui_discord_owner_role_ids = parse_int_list(
            os.getenv("WEBUI_DISCORD_OWNER_ROLE_IDS")
        )

        webui_discord_viewer_role_ids = parse_int_list(
            os.getenv("WEBUI_DISCORD_VIEWER_ROLE_IDS")
        )

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

        if webui_enabled and webui_discord_auth_enabled:
            missing_discord_settings = []

            if not discord_oauth_client_id:
                missing_discord_settings.append("DISCORD_OAUTH_CLIENT_ID")

            if not discord_oauth_client_secret:
                missing_discord_settings.append("DISCORD_OAUTH_CLIENT_SECRET")

            if not discord_oauth_redirect_uri:
                missing_discord_settings.append("DISCORD_OAUTH_REDIRECT_URI")

            if webui_discord_guild_id is None:
                missing_discord_settings.append("WEBUI_DISCORD_GUILD_ID")

            if (
                not webui_discord_allowed_role_ids
                and not webui_discord_owner_role_ids
                and not webui_discord_viewer_role_ids
            ):
                missing_discord_settings.append(
                    "WEBUI_DISCORD_OWNER_ROLE_IDS or WEBUI_DISCORD_VIEWER_ROLE_IDS"
                )

            if missing_discord_settings:
                joined = ", ".join(missing_discord_settings)
                raise RuntimeError(
                    f"Discord WebUI login is enabled, but these settings are missing: {joined}."
                )

        if (
            webui_enabled
            and not webui_discord_auth_enabled
            and (not webui_password_login_enabled or not webui_credentials)
        ):
            raise RuntimeError(
                "WEBUI_ENABLED is true, but no WebUI login method is configured."
            )

        return BotConfig(
            discord_token=token,
            prefix=prefix,
            test_guild_id=test_guild_id,
            webui_enabled=webui_enabled,
            webui_host=webui_host,
            webui_port=webui_port,
            webui_credentials=tuple(webui_credentials),
            webui_password_login_enabled=webui_password_login_enabled,
            webui_discord_auth_enabled=webui_discord_auth_enabled,
            discord_oauth_client_id=discord_oauth_client_id,
            discord_oauth_client_secret=discord_oauth_client_secret,
            discord_oauth_redirect_uri=discord_oauth_redirect_uri,
            webui_discord_guild_id=webui_discord_guild_id,
            webui_discord_allowed_role_ids=webui_discord_allowed_role_ids,
            webui_discord_owner_role_ids=webui_discord_owner_role_ids,
            webui_discord_viewer_role_ids=webui_discord_viewer_role_ids,
            application_db_path=application_db_path,
        )