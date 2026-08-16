from __future__ import annotations

from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

import aiosqlite

from src.services.database import (
    DatabaseRow,
    open_database,
)


@dataclass(
    frozen=True
)
class AuditEntry:
    id: int
    source: str
    actor_id: str | None
    actor_name: str
    guild_id: int | None
    action: str
    detail: str
    created_at: str


class AuditStore:
    def __init__(
        self,
        database_path: str,
    ) -> None:
        self.database_path = Path(
            database_path
        )

    async def initialise(
        self,
    ) -> None:
        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    actor_id TEXT,
                    actor_name TEXT NOT NULL,
                    guild_id INTEGER,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_created
                ON audit_log (created_at DESC)
                """
            )

            await database.commit()

    async def log(
        self,
        *,
        source: str,
        actor_name: str,
        action: str,
        actor_id: str | None = None,
        guild_id: int | None = None,
        detail: str = "",
    ) -> None:
        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                INSERT INTO audit_log (
                    source,
                    actor_id,
                    actor_name,
                    guild_id,
                    action,
                    detail,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    actor_id,
                    actor_name,
                    guild_id,
                    action,
                    detail[:2000],
                    self._now(),
                ),
            )

            await database.commit()

    async def list_recent(
        self,
        limit: int = 20,
    ) -> list[AuditEntry]:
        limit = max(
            1,
            min(
                limit,
                100,
            ),
        )

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = (
                DatabaseRow
            )

            rows = await (
                await database.execute(
                    """
                    SELECT *
                    FROM audit_log
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            ).fetchall()

        return [
            AuditEntry(
                id=row["id"],
                source=row["source"],
                actor_id=row["actor_id"],
                actor_name=row[
                    "actor_name"
                ],
                guild_id=row["guild_id"],
                action=row["action"],
                detail=row["detail"],
                created_at=row[
                    "created_at"
                ],
            )
            for row in rows
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()