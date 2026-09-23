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
    name: str
    payload: dict[str, Any]
    created_at: str
    updated_at: str


class SavedEmbedStore:
    def __init__(
        self,
        database_path: str | Path,
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
                CREATE TABLE IF NOT EXISTS saved_embeds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_saved_embeds_name
                ON saved_embeds (
                    name COLLATE NOCASE
                )
                """
            )

            await database.commit()

    async def list_embeds(
        self,
    ) -> list[SavedEmbed]:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM saved_embeds
                ORDER BY name COLLATE NOCASE ASC
                """
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
        saved_embed_id: int,
    ) -> SavedEmbed | None:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM saved_embeds
                WHERE id = ?
                LIMIT 1
                """,
                (
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
        name: str,
        payload: dict[str, Any],
    ) -> SavedEmbed:
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
                        name,
                        payload_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
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
                "already exists."
            ) from caught

        saved_embed = await self.get_embed(
            saved_embed_id
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
        saved_embed_id: int,
        name: str,
        payload: dict[str, Any],
    ) -> SavedEmbed:
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
                    WHERE id = ?
                    """,
                    (
                        cleaned_name,
                        self._serialise_payload(
                            payload
                        ),
                        self._now(),
                        saved_embed_id,
                    ),
                )

                await database.commit()

                if cursor.rowcount == 0:
                    raise ValueError(
                        "That saved embed no "
                        "longer exists."
                    )

        except DatabaseIntegrityError as caught:
            raise ValueError(
                "A saved embed with that name "
                "already exists."
            ) from caught

        saved_embed = await self.get_embed(
            saved_embed_id
        )

        if saved_embed is None:
            raise RuntimeError(
                "Saved embed was updated but "
                "could not be loaded."
            )

        return saved_embed

    async def delete_embed(
        self,
        saved_embed_id: int,
    ) -> bool:
        async with open_database(
            self.database_path
        ) as database:
            cursor = await database.execute(
                """
                DELETE FROM saved_embeds
                WHERE id = ?
                """,
                (
                    saved_embed_id,
                ),
            )

            await database.commit()

        return cursor.rowcount > 0

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