from __future__ import annotations

import sqlite3

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

import discord


class WebUIAccessManager:
    def __init__(
        self,
        bot: discord.Client,
    ) -> None:
        self.bot = bot

    def database_path(
        self,
    ) -> Path:
        application_store = getattr(
            self.bot,
            "application_store",
            None,
        )

        if application_store is not None:
            raw_path = getattr(
                application_store,
                "database_path",
                None,
            )

            if raw_path is not None:
                return Path(
                    raw_path
                )

        return Path(
            getattr(
                self.bot.config,
                "application_db_path",
                "data/tfsbot.sqlite3",
            )
        )

    def ensure_tables(
        self,
    ) -> None:
        database_path = (
            self.database_path()
        )

        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sqlite3.connect(
            database_path
        ) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS webui_access_roles (
                    guild_id INTEGER NOT NULL,
                    access_level TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (
                        guild_id,
                        access_level,
                        role_id
                    )
                )
                """
            )

    def stored_role_ids(
        self,
        guild_id: int,
        access_level: str,
    ) -> tuple[int, ...]:
        self.ensure_tables()

        with sqlite3.connect(
            self.database_path()
        ) as database:
            rows = database.execute(
                """
                SELECT role_id
                FROM webui_access_roles
                WHERE guild_id = ?
                AND access_level = ?
                ORDER BY role_id ASC
                """,
                (
                    guild_id,
                    access_level,
                ),
            ).fetchall()

        return tuple(
            int(row[0])
            for row in rows
        )

    def set_stored_role_ids(
        self,
        guild_id: int,
        access_level: str,
        role_ids: list[int],
    ) -> None:
        self.ensure_tables()

        cleaned_role_ids = sorted(
            set(role_ids)
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        with sqlite3.connect(
            self.database_path()
        ) as database:
            database.execute(
                """
                DELETE FROM webui_access_roles
                WHERE guild_id = ?
                AND access_level = ?
                """,
                (
                    guild_id,
                    access_level,
                ),
            )

            database.executemany(
                """
                INSERT INTO webui_access_roles (
                    guild_id,
                    access_level,
                    role_id,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        guild_id,
                        access_level,
                        role_id,
                        now,
                    )
                    for role_id
                    in cleaned_role_ids
                ],
            )

    def env_owner_role_ids(
        self,
    ) -> tuple[int, ...]:
        owner_role_ids = tuple(
            getattr(
                self.bot.config,
                "webui_discord_owner_role_ids",
                (),
            )
        )

        if owner_role_ids:
            return owner_role_ids

        return tuple(
            getattr(
                self.bot.config,
                "webui_discord_allowed_role_ids",
                (),
            )
        )

    def env_viewer_role_ids(
        self,
    ) -> tuple[int, ...]:
        return tuple(
            getattr(
                self.bot.config,
                "webui_discord_viewer_role_ids",
                (),
            )
        )

    def effective_role_ids(
        self,
        guild_id: int,
        access_level: str,
    ) -> tuple[int, ...]:
        try:
            stored_role_ids = (
                self.stored_role_ids(
                    guild_id,
                    access_level,
                )
            )

        except sqlite3.Error:
            stored_role_ids = ()

        if stored_role_ids:
            return stored_role_ids

        if access_level == "owner":
            return (
                self.env_owner_role_ids()
            )

        if access_level == "viewer":
            return (
                self.env_viewer_role_ids()
            )

        return ()

    def effective_source(
        self,
        guild_id: int,
        access_level: str,
    ) -> str:
        try:
            stored_role_ids = (
                self.stored_role_ids(
                    guild_id,
                    access_level,
                )
            )

        except sqlite3.Error:
            stored_role_ids = ()

        if stored_role_ids:
            return "SQLite"

        if (
            access_level == "owner"
            and self.env_owner_role_ids()
        ):
            return ".env fallback"

        if (
            access_level == "viewer"
            and self.env_viewer_role_ids()
        ):
            return ".env fallback"

        return "Not set"

    def discord_login_enabled(
        self,
    ) -> bool:
        return bool(
            getattr(
                self.bot.config,
                "webui_discord_auth_enabled",
                False,
            )
        )

    def password_login_enabled(
        self,
    ) -> bool:
        return bool(
            getattr(
                self.bot.config,
                "webui_password_login_enabled",
                True,
            )
            and self.bot.config.webui_credentials
        )

    def build_context(
        self,
        guild: discord.Guild | None,
    ) -> dict[str, Any]:
        if guild is None:
            return {
                "owner_role_ids": [],
                "viewer_role_ids": [],
                "owner_source": "Not set",
                "viewer_source": "Not set",
                "discord_auth_status": (
                    "Enabled"
                    if self.discord_login_enabled()
                    else "Disabled"
                ),
                "discord_auth_class": (
                    "good"
                    if self.discord_login_enabled()
                    else "warn"
                ),
                "password_status": (
                    "Enabled"
                    if self.password_login_enabled()
                    else "Disabled"
                ),
                "password_class": (
                    "good"
                    if self.password_login_enabled()
                    else "warn"
                ),
                "owner_count": 0,
                "viewer_count": 0,
            }

        owner_role_ids = (
            self.effective_role_ids(
                guild.id,
                "owner",
            )
        )

        viewer_role_ids = (
            self.effective_role_ids(
                guild.id,
                "viewer",
            )
        )

        return {
            "owner_role_ids": [
                str(role_id)
                for role_id
                in owner_role_ids
            ],
            "viewer_role_ids": [
                str(role_id)
                for role_id
                in viewer_role_ids
            ],
            "owner_source": (
                self.effective_source(
                    guild.id,
                    "owner",
                )
            ),
            "viewer_source": (
                self.effective_source(
                    guild.id,
                    "viewer",
                )
            ),
            "discord_auth_status": (
                "Enabled"
                if self.discord_login_enabled()
                else "Disabled"
            ),
            "discord_auth_class": (
                "good"
                if self.discord_login_enabled()
                else "warn"
            ),
            "password_status": (
                "Enabled"
                if self.password_login_enabled()
                else "Disabled"
            ),
            "password_class": (
                "good"
                if self.password_login_enabled()
                else "warn"
            ),
            "owner_count": len(
                owner_role_ids
            ),
            "viewer_count": len(
                viewer_role_ids
            ),
        }

    def matching_discord_role(
        self,
        member_data: dict[str, Any],
    ) -> str | None:
        guild_id = getattr(
            self.bot.config,
            "webui_discord_guild_id",
            None,
        )

        if guild_id is None:
            return None

        member_role_ids = {
            str(role_id)
            for role_id
            in member_data.get(
                "roles",
                [],
            )
        }

        owner_role_ids = {
            str(role_id)
            for role_id
            in self.effective_role_ids(
                guild_id,
                "owner",
            )
        }

        viewer_role_ids = {
            str(role_id)
            for role_id
            in self.effective_role_ids(
                guild_id,
                "viewer",
            )
        }

        if owner_role_ids.intersection(
            member_role_ids
        ):
            return "owner"

        if viewer_role_ids.intersection(
            member_role_ids
        ):
            return "viewer"

        return None