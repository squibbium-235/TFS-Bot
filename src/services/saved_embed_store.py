"""
Per-guild saved Discord embed payloads.

Saved embed names are unique within a guild,
ignoring case.

Older Sanctuary Servo versions stored embeds
globally. When that schema is found, the old
table is renamed to saved_embeds_legacy_global
rather than guessing which guild owns each
existing embed.
"""

from __future__ import annotations

import json

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.services.database import (
    DatabaseIntegrityError,
    DatabaseRow,
    open_database,
)


@dataclass(frozen=True)
class SavedEmbed:
    id: int
    guild_id: int
    name: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str


class SavedEmbedStore:
    """
    Create, update and delete saved embeds.

    Every embed belongs to exactly one Discord
    guild.

    Names are unique within that guild, rather
    than globally across Sanctuary Servo.
    """

    def __init__(
        self,
        database_path: str | Path,
    ) -> None:
        self.database_path = Path(
            database_path
        )

    async def initialise(self) -> None:
        """
        Create the per-guild saved-embed table.

        An old global saved_embeds table is
        preserved as saved_embeds_legacy_global.

        Legacy rows are deliberately not assigned
        automatically because doing so could expose
        one guild's saved content to another.
        """
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        async with open_database(
            self.database_path
        ) as database:
            table_cursor = await database.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name = 'saved_embeds'
                LIMIT 1
                """
            )

            existing_table = (
                await table_cursor.fetchone()
            )

            if existing_table is not None:
                columns_cursor = (
                    await database.execute(
                        """
                        PRAGMA table_info(
                            saved_embeds
                        )
                        """
                    )
                )

                columns = (
                    await columns_cursor.fetchall()
                )

                column_names = {
                    str(row[1])
                    for row in columns
                }

                if "guild_id" not in column_names:
                    legacy_cursor = (
                        await database.execute(
                            """
                            SELECT name
                            FROM sqlite_master
                            WHERE type = 'table'
                            AND name = ?
                            LIMIT 1
                            """,
                            (
                                "saved_embeds_legacy_global",
                            ),
                        )
                    )

                    legacy_table = (
                        await legacy_cursor.fetchone()
                    )

                    if legacy_table is not None:
                        raise RuntimeError(
                            "Cannot migrate saved embeds: "
                            "saved_embeds_legacy_global "
                            "already exists while the "
                            "current saved_embeds table "
                            "still uses the old schema."
                        )

                    # This named index follows the
                    # table during an SQLite rename.
                    # Drop it first so the new table
                    # can use its own indexes without
                    # a naming collision.
                    await database.execute(
                        """
                        DROP INDEX IF EXISTS
                            idx_saved_embeds_name
                        """
                    )

                    await database.execute(
                        """
                        ALTER TABLE saved_embeds
                        RENAME TO
                            saved_embeds_legacy_global
                        """
                    )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_embeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL COLLATE NOCASE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (
                        guild_id,
                        name
                    )
                )
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_saved_embeds_guild_name
                ON saved_embeds (
                    guild_id,
                    name COLLATE NOCASE
                )
                """
            )

            await database.commit()

    async def list_embeds(
        self,
        guild_id: int,
    ) -> list[SavedEmbed]:
        guild_id = self._clean_guild_id(
            guild_id
        )

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM saved_embeds
                WHERE guild_id = ?
                ORDER BY name COLLATE NOCASE ASC
                """,
                (
                    guild_id,
                ),
            )

            rows = await cursor.fetchall()

        return [
            self._row_to_saved_embed(
                row
            )
            for row in rows
        ]

    async def get_embed(
        self,
        guild_id: int,
        saved_embed_id: int,
    ) -> SavedEmbed | None:
        guild_id = self._clean_guild_id(
            guild_id
        )

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM saved_embeds
                WHERE guild_id = ?
                AND id = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    saved_embed_id,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_saved_embed(
            row
        )

    async def create_embed(
        self,
        *,
        guild_id: int,
        name: str,
        payload: dict[str, Any],
    ) -> SavedEmbed:
        """
        Create one guild-owned saved embed.

        Duplicate names are rejected only within
        the same guild.
        """
        guild_id = self._clean_guild_id(
            guild_id
        )

        cleaned_name = self._clean_name(
            name
        )

        now = self._now()

        try:
            async with open_database(
                self.database_path
            ) as database:
                cursor = await database.execute(
                    """
                    INSERT INTO saved_embeds (
                        guild_id,
                        name,
                        payload_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        cleaned_name,
                        self._serialise_payload(
                            payload
                        ),
                        now,
                        now,
                    ),
                )

                await database.commit()

                saved_embed_id = int(
                    cursor.lastrowid
                )

        except DatabaseIntegrityError as caught:
            raise ValueError(
                "A saved embed with that name "
                "already exists in this server."
            ) from caught

        saved_embed = await self.get_embed(
            guild_id,
            saved_embed_id,
        )

        if saved_embed is None:
            raise RuntimeError(
                "Saved embed was created but "
                "could not be loaded."
            )

        return saved_embed

    async def update_embed(
        self,
        *,
        guild_id: int,
        saved_embed_id: int,
        name: str,
        payload: dict[str, Any],
    ) -> SavedEmbed:
        """
        Update one saved embed only when it belongs
        to the supplied guild.
        """
        guild_id = self._clean_guild_id(
            guild_id
        )

        cleaned_name = self._clean_name(
            name
        )

        try:
            async with open_database(
                self.database_path
            ) as database:
                cursor = await database.execute(
                    """
                    UPDATE saved_embeds
                    SET
                        name = ?,
                        payload_json = ?,
                        updated_at = ?
                    WHERE guild_id = ?
                    AND id = ?
                    """,
                    (
                        cleaned_name,
                        self._serialise_payload(
                            payload
                        ),
                        self._now(),
                        guild_id,
                        saved_embed_id,
                    ),
                )

                await database.commit()

                if cursor.rowcount == 0:
                    raise ValueError(
                        "That saved embed does not "
                        "exist in this server."
                    )

        except DatabaseIntegrityError as caught:
            raise ValueError(
                "A saved embed with that name "
                "already exists in this server."
            ) from caught

        saved_embed = await self.get_embed(
            guild_id,
            saved_embed_id,
        )

        if saved_embed is None:
            raise RuntimeError(
                "Saved embed was updated but "
                "could not be loaded."
            )

        return saved_embed

    async def delete_embed(
        self,
        guild_id: int,
        saved_embed_id: int,
    ) -> bool:
        guild_id = self._clean_guild_id(
            guild_id
        )

        async with open_database(
            self.database_path
        ) as database:
            cursor = await database.execute(
                """
                DELETE FROM saved_embeds
                WHERE guild_id = ?
                AND id = ?
                """,
                (
                    guild_id,
                    saved_embed_id,
                ),
            )

            await database.commit()

        return cursor.rowcount > 0

    async def legacy_embed_count(
        self,
    ) -> int:
        """
        Return how many old global embeds remain
        preserved from the pre-guild schema.
        """
        async with open_database(
            self.database_path
        ) as database:
            cursor = await database.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name = ?
                LIMIT 1
                """,
                (
                    "saved_embeds_legacy_global",
                ),
            )

            if await cursor.fetchone() is None:
                return 0

            count_cursor = await database.execute(
                """
                SELECT COUNT(*)
                FROM saved_embeds_legacy_global
                """
            )

            row = await count_cursor.fetchone()

        if row is None:
            return 0

        return int(
            row[0]
        )

    @staticmethod
    def _clean_guild_id(
        guild_id: int,
    ) -> int:
        try:
            cleaned = int(
                guild_id
            )

        except (
            TypeError,
            ValueError,
        ) as caught:
            raise ValueError(
                "Guild ID is invalid."
            ) from caught

        if cleaned <= 0:
            raise ValueError(
                "Guild ID is invalid."
            )

        return cleaned

    @staticmethod
    def _clean_name(
        name: str,
    ) -> str:
        cleaned = name.strip()

        if not cleaned:
            raise ValueError(
                "Saved embed name cannot be empty."
            )

        if len(cleaned) > 100:
            raise ValueError(
                "Saved embed name must be "
                "100 characters or fewer."
            )

        return cleaned

    @staticmethod
    def _serialise_payload(
        payload: dict[str, Any],
    ) -> str:
        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Saved embed payload must "
                "be an object."
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

    @staticmethod
    def _deserialise_payload(
        raw_value: str,
    ) -> dict[str, Any]:
        try:
            value = json.loads(
                raw_value
            )

        except json.JSONDecodeError:
            return {}

        if not isinstance(
            value,
            dict,
        ):
            return {}

        return value

    def _row_to_saved_embed(
        self,
        row: DatabaseRow,
    ) -> SavedEmbed:
        return SavedEmbed(
            id=int(
                row["id"]
            ),
            guild_id=int(
                row["guild_id"]
            ),
            name=str(
                row["name"]
            ),
            payload=(
                self._deserialise_payload(
                    str(
                        row[
                            "payload_json"
                        ]
                    )
                )
            ),
            created_at=str(
                row["created_at"]
            ),
            updated_at=str(
                row["updated_at"]
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()