"""Discord role allow-lists that decide Web UI owner and viewer access.

Stored role ids in the application database replace the environment
lists for that guild and level. An empty stored set falls back to the
environment. Owner matching wins over viewer matching.
"""

from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

import discord

from src.services.database import (
    DatabaseError,
    open_sync_database,
)


class WebUIAccessManager:
    """Read and replace the per-guild Web UI role allow-lists."""

    def __init__(
        self,
        bot: discord.Client,
    ) -> None:
        self.bot = bot

    def database_path(
        self,
    ) -> Path:
        """Prefer the live application store path, then config, then the default file."""
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
        """Create the role table if this database does not have it yet."""
        database_path = (
            self.database_path()
        )

        database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open_sync_database(
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

        with open_sync_database(
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
        """Replace every stored role for one guild and access level.

        Ids are deduplicated. An empty list deletes the rows, which makes
        later lookups fall back to the environment.
        """
        self.ensure_tables()

        cleaned_role_ids = sorted(
            set(role_ids)
        )

        now = datetime.now(
            timezone.utc
        ).isoformat()

        with open_sync_database(
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
        """Owner role ids from the environment, else the older allowed-role list.

        ``webui_discord_allowed_role_ids`` is used only when the owner list
        is empty.
        """
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
        """Stored ids when present, otherwise the environment list for that level.

        A database error is treated as no stored rows, not as a hard failure.
        Unknown access levels do not consult the environment.
        """
        try:
            stored_role_ids = (
                self.stored_role_ids(
                    guild_id,
                    access_level,
                )
            )

        except DatabaseError:
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
        """Label the list as SQLite, the environment fallback, or unset."""
        try:
            stored_role_ids = (
                self.stored_role_ids(
                    guild_id,
                    access_level,
                )
            )

        except DatabaseError:
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
        """True when the flag is on and at least one credential exists.

        The flag defaults to on when the config attribute is missing.
        """
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
        """Map one guild member payload to ``owner``, ``viewer``, or None.

        Only ``webui_discord_guild_id`` is considered. Owner is returned
        when any owner role overlaps, even if a viewer role also matches.
        No configured guild id refuses the login.
        """
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