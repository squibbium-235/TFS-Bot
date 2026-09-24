"""
Welcome settings and delivery records.

Enabling welcome sets enabled_since when it is not
already set. Disabling clears it. Only approvals
actioned at or after that time, and not already
recorded in welcome_deliveries, are eligible to be
sent. Embed colour is stored as Discord's "color".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.services.database import (
    DatabaseRow,
    open_database,
)


DEFAULT_WELCOME_EMBED: dict[str, Any] = {
    "title": "Welcome {user}!",
    "description": (
        "Welcome to **{server}**!\n"
        "We hope you enjoy your stay!"
    ),
    "color": 0x5865F2,
}


@dataclass(frozen=True)
class WelcomeSettings:
    guild_id: int
    enabled: bool
    channel_id: int | None
    embed_data: dict[str, Any]
    enabled_since: str | None
    updated_at: str


@dataclass(frozen=True)
class ApprovedApplication:
    application_id: str
    guild_id: int
    user_id: int
    actioned_at: str


class WelcomeStore:
    """
    Persist welcome embeds and which approvals
    have already been welcomed.

    get_settings returns defaults without writing
    when the guild has no row yet.
    """
    def __init__(
        self,
        database_path: str,
    ) -> None:
        self.database_path = Path(
            database_path
        )

    async def initialise(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS welcome_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    channel_id INTEGER,
                    embed_json TEXT NOT NULL,
                    enabled_since TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS welcome_deliveries (
                    application_id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    result TEXT NOT NULL,
                    message_id INTEGER,
                    detail TEXT,
                    processed_at TEXT NOT NULL
                )
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_welcome_deliveries_guild
                ON welcome_deliveries (
                    guild_id,
                    processed_at DESC
                )
                """
            )

            await database.commit()

    async def get_settings(
        self,
        guild_id: int,
    ) -> WelcomeSettings:
        """
        Return stored settings, or defaults.

        A missing row is not inserted. The default
        embed is a copy, so callers can edit it.
        """
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM welcome_settings
                WHERE guild_id = ?
                LIMIT 1
                """,
                (guild_id,),
            )

            row = await cursor.fetchone()

        if row is None:
            return WelcomeSettings(
                guild_id=guild_id,
                enabled=False,
                channel_id=None,
                embed_data=self.default_embed_data(),
                enabled_since=None,
                updated_at=self._now(),
            )

        return self._row_to_settings(
            row
        )

    async def save_config(
        self,
        *,
        guild_id: int,
        channel_id: int | None,
        embed_data: dict[str, Any],
    ) -> WelcomeSettings:
        """
        Store the channel and embed, keeping enabled
        and enabled_since as they already are.
        """
        existing = await self.get_settings(
            guild_id
        )

        settings = WelcomeSettings(
            guild_id=guild_id,
            enabled=existing.enabled,
            channel_id=channel_id,
            embed_data=self.normalise_embed_data(
                embed_data
            ),
            enabled_since=(
                existing.enabled_since
            ),
            updated_at=self._now(),
        )

        await self._save_settings(
            settings
        )

        return settings

    async def set_channel(
        self,
        *,
        guild_id: int,
        channel_id: int | None,
    ) -> WelcomeSettings:
        existing = await self.get_settings(
            guild_id
        )

        return await self.save_config(
            guild_id=guild_id,
            channel_id=channel_id,
            embed_data=existing.embed_data,
        )

    async def set_embed_data(
        self,
        *,
        guild_id: int,
        embed_data: dict[str, Any],
    ) -> WelcomeSettings:
        existing = await self.get_settings(
            guild_id
        )

        return await self.save_config(
            guild_id=guild_id,
            channel_id=existing.channel_id,
            embed_data=embed_data,
        )

    async def set_enabled(
        self,
        *,
        guild_id: int,
        enabled: bool,
    ) -> WelcomeSettings:
        """
        Turn welcome on or off for this guild.

        Turning it on keeps enabled_since when welcome
        was already on. Otherwise the window starts
        now, so older approvals are not welcomed.
        Turning it off clears enabled_since.
        """
        existing = await self.get_settings(
            guild_id
        )

        if enabled:
            enabled_since = (
                existing.enabled_since
                if existing.enabled
                and existing.enabled_since
                else self._now()
            )
        else:
            enabled_since = None

        settings = WelcomeSettings(
            guild_id=guild_id,
            enabled=enabled,
            channel_id=existing.channel_id,
            embed_data=existing.embed_data,
            enabled_since=enabled_since,
            updated_at=self._now(),
        )

        await self._save_settings(
            settings
        )

        return settings

    async def list_enabled_settings(
        self,
    ) -> list[WelcomeSettings]:
        """
        Return guilds that can send welcomes.

        Enabled, a channel, and enabled_since are
        all required. A guild missing any of those
        is omitted.
        """
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM welcome_settings
                WHERE enabled = 1
                AND channel_id IS NOT NULL
                AND enabled_since IS NOT NULL
                ORDER BY guild_id ASC
                """
            )

            rows = await cursor.fetchall()

        return [
            self._row_to_settings(row)
            for row in rows
        ]

    async def list_unprocessed_approvals(
        self,
        *,
        guild_id: int,
        since: str,
        limit: int = 25,
    ) -> list[ApprovedApplication]:
        """
        Return approved applications not yet welcomed.

        actioned_at must be at or after since, compared
        as text. Anything already in welcome_deliveries
        is excluded, including a failed attempt.
        Oldest approvals come first. The limit is
        clamped to the range 1 to 100.
        """
        safe_limit = max(
            1,
            min(limit, 100),
        )

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT
                    applications.id,
                    applications.guild_id,
                    applications.user_id,
                    applications.actioned_at
                FROM applications
                WHERE applications.guild_id = ?
                AND applications.status = 'approved'
                AND applications.actioned_at IS NOT NULL
                AND applications.actioned_at >= ?
                AND NOT EXISTS (
                    SELECT 1
                    FROM welcome_deliveries
                    WHERE welcome_deliveries.application_id = applications.id
                )
                ORDER BY applications.actioned_at ASC
                LIMIT ?
                """,
                (
                    guild_id,
                    since,
                    safe_limit,
                ),
            )

            rows = await cursor.fetchall()

        approvals: list[
            ApprovedApplication
        ] = []

        for row in rows:
            actioned_at = row[
                "actioned_at"
            ]

            if actioned_at is None:
                continue

            approvals.append(
                ApprovedApplication(
                    application_id=str(
                        row["id"]
                    ),
                    guild_id=int(
                        row["guild_id"]
                    ),
                    user_id=int(
                        row["user_id"]
                    ),
                    actioned_at=str(
                        actioned_at
                    ),
                )
            )

        return approvals

    async def mark_delivery(
        self,
        *,
        application_id: str,
        guild_id: int,
        user_id: int,
        result: str,
        message_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        """
        Record that this application has been processed.

        A second call for the same application replaces
        the result, so the row still blocks another send.
        result is cut at 40 characters and detail at 1000.
        """
        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                INSERT INTO welcome_deliveries (
                    application_id,
                    guild_id,
                    user_id,
                    result,
                    message_id,
                    detail,
                    processed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(application_id)
                DO UPDATE SET
                    result = excluded.result,
                    message_id = excluded.message_id,
                    detail = excluded.detail,
                    processed_at = excluded.processed_at
                """,
                (
                    application_id,
                    guild_id,
                    user_id,
                    result[:40],
                    message_id,
                    (
                        detail[:1000]
                        if detail
                        else None
                    ),
                    self._now(),
                ),
            )

            await database.commit()

    async def _save_settings(
        self,
        settings: WelcomeSettings,
    ) -> None:
        embed_json = json.dumps(
            self.normalise_embed_data(
                settings.embed_data
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )

        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                INSERT INTO welcome_settings (
                    guild_id,
                    enabled,
                    channel_id,
                    embed_json,
                    enabled_since,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id)
                DO UPDATE SET
                    enabled = excluded.enabled,
                    channel_id = excluded.channel_id,
                    embed_json = excluded.embed_json,
                    enabled_since = excluded.enabled_since,
                    updated_at = excluded.updated_at
                """,
                (
                    settings.guild_id,
                    1 if settings.enabled else 0,
                    settings.channel_id,
                    embed_json,
                    settings.enabled_since,
                    settings.updated_at,
                ),
            )

            await database.commit()

    def _row_to_settings(
        self,
        row: DatabaseRow,
    ) -> WelcomeSettings:
        raw_embed_json = str(
            row["embed_json"]
        )

        try:
            parsed = json.loads(
                raw_embed_json
            )
        except json.JSONDecodeError:
            parsed = self.default_embed_data()

        if not isinstance(parsed, dict):
            parsed = self.default_embed_data()

        return WelcomeSettings(
            guild_id=int(
                row["guild_id"]
            ),
            enabled=bool(
                row["enabled"]
            ),
            channel_id=(
                int(row["channel_id"])
                if row["channel_id"]
                is not None
                else None
            ),
            embed_data=(
                self.normalise_embed_data(
                    parsed
                )
            ),
            enabled_since=(
                str(row["enabled_since"])
                if row["enabled_since"]
                is not None
                else None
            ),
            updated_at=str(
                row["updated_at"]
            ),
        )

    @staticmethod
    def default_embed_data(
    ) -> dict[str, Any]:
        """
        Return a fresh copy of the built-in welcome embed.
        """
        return json.loads(
            json.dumps(
                DEFAULT_WELCOME_EMBED
            )
        )

    @classmethod
    def normalise_embed_data(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return JSON-safe embed data using the key color.

        A colour key is copied to color and removed.
        Values that cannot be serialised, or a value
        that is not an object, become the default embed.
        """
        try:
            cleaned = json.loads(
                json.dumps(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            return cls.default_embed_data()

        if not isinstance(cleaned, dict):
            return cls.default_embed_data()

        if "colour" in cleaned:
            if "color" not in cleaned:
                cleaned["color"] = cleaned[
                    "colour"
                ]

            cleaned.pop(
                "colour",
                None,
            )

        return cleaned

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()