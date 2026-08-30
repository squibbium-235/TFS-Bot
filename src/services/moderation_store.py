from __future__ import annotations

import json

from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

from src.services.database import (
    DatabaseRow,
    open_database,
)


@dataclass(frozen=True)
class ModerationCase:
    id: int
    guild_id: int
    case_number: int
    user_id: int
    moderator_id: int | None

    action: str
    reason: str | None

    duration_seconds: int | None
    expires_at: str | None

    source: str
    source_reference: str | None

    details: dict[str, Any]

    log_channel_id: int | None
    log_message_id: int | None

    created_at: str


@dataclass(frozen=True)
class UserModProfile:
    guild_id: int
    user_id: int

    channel_id: int
    message_id: int
    thread_id: int

    created_at: str
    updated_at: str


class ModerationStore:
    def __init__(
        self,
        database_path: str | Path,
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
                CREATE TABLE IF NOT EXISTS
                moderation_case_counters (
                    guild_id INTEGER PRIMARY KEY,
                    last_case_number INTEGER NOT NULL
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS
                moderation_cases (
                    id INTEGER PRIMARY KEY
                        AUTOINCREMENT,

                    guild_id INTEGER NOT NULL,
                    case_number INTEGER NOT NULL,

                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER,

                    action TEXT NOT NULL,
                    reason TEXT,

                    duration_seconds INTEGER,
                    expires_at TEXT,

                    source TEXT NOT NULL,
                    source_reference TEXT,

                    details_json TEXT NOT NULL
                        DEFAULT '{}',

                    log_channel_id INTEGER,
                    log_message_id INTEGER,

                    created_at TEXT NOT NULL,

                    UNIQUE (
                        guild_id,
                        case_number
                    )
                )
                """
            )

            await database.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                moderation_cases_source_reference
                ON moderation_cases (
                    guild_id,
                    source,
                    source_reference
                )
                WHERE source_reference IS NOT NULL
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS
                moderation_cases_user
                ON moderation_cases (
                    guild_id,
                    user_id,
                    created_at DESC
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS
                user_mod_profiles (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,

                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    thread_id INTEGER NOT NULL,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    PRIMARY KEY (
                        guild_id,
                        user_id
                    )
                )
                """
            )

            await database.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS
                user_mod_profiles_thread
                ON user_mod_profiles (
                    thread_id
                )
                """
            )

            await database.commit()

    async def create_case(
        self,
        *,
        guild_id: int,
        user_id: int,
        moderator_id: int | None,
        action: str,
        reason: str | None = None,
        duration_seconds: int | None = None,
        expires_at: str | None = None,
        source: str = "discord",
        source_reference: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> ModerationCase:
        created_at = self._now()

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            try:
                await database.execute(
                    "BEGIN IMMEDIATE"
                )

                cursor = await database.execute(
                    """
                    SELECT last_case_number
                    FROM moderation_case_counters
                    WHERE guild_id = ?
                    """,
                    (
                        guild_id,
                    ),
                )

                row = await cursor.fetchone()

                if row is None:
                    case_number = 1

                    await database.execute(
                        """
                        INSERT INTO
                            moderation_case_counters (
                                guild_id,
                                last_case_number
                            )
                        VALUES (?, ?)
                        """,
                        (
                            guild_id,
                            case_number,
                        ),
                    )

                else:
                    case_number = (
                        int(
                            row[
                                "last_case_number"
                            ]
                        )
                        + 1
                    )

                    await database.execute(
                        """
                        UPDATE
                            moderation_case_counters
                        SET
                            last_case_number = ?
                        WHERE guild_id = ?
                        """,
                        (
                            case_number,
                            guild_id,
                        ),
                    )

                cursor = await database.execute(
                    """
                    INSERT INTO moderation_cases (
                        guild_id,
                        case_number,
                        user_id,
                        moderator_id,
                        action,
                        reason,
                        duration_seconds,
                        expires_at,
                        source,
                        source_reference,
                        details_json,
                        created_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        guild_id,
                        case_number,
                        user_id,
                        moderator_id,
                        action,
                        reason,
                        duration_seconds,
                        expires_at,
                        source,
                        source_reference,
                        json.dumps(
                            details or {},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        created_at,
                    ),
                )

                case_id = cursor.lastrowid

                if case_id is None:
                    raise RuntimeError(
                        "SQLite did not return "
                        "a moderation case ID."
                    )

                await database.commit()

            except Exception:
                await database.rollback()
                raise

        moderation_case = await self.get_case_by_id(
            int(case_id)
        )

        if moderation_case is None:
            raise RuntimeError(
                "Moderation case was created "
                "but could not be read back."
            )

        return moderation_case

    async def get_case(
        self,
        guild_id: int,
        case_number: int,
    ) -> ModerationCase | None:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM moderation_cases
                WHERE guild_id = ?
                  AND case_number = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    case_number,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_case(
            row
        )

    async def get_case_by_id(
        self,
        case_id: int,
    ) -> ModerationCase | None:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM moderation_cases
                WHERE id = ?
                LIMIT 1
                """,
                (
                    case_id,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_case(
            row
        )

    async def get_case_by_source_reference(
        self,
        *,
        guild_id: int,
        source: str,
        source_reference: str,
    ) -> ModerationCase | None:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM moderation_cases
                WHERE guild_id = ?
                  AND source = ?
                  AND source_reference = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    source,
                    source_reference,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_case(
            row
        )

    async def list_cases_for_user(
        self,
        *,
        guild_id: int,
        user_id: int,
        limit: int = 25,
    ) -> list[ModerationCase]:
        safe_limit = max(
            1,
            min(
                limit,
                100,
            ),
        )

        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM moderation_cases
                WHERE guild_id = ?
                  AND user_id = ?
                ORDER BY
                    case_number DESC
                LIMIT ?
                """,
                (
                    guild_id,
                    user_id,
                    safe_limit,
                ),
            )

            rows = await cursor.fetchall()

        return [
            self._row_to_case(
                row
            )
            for row in rows
        ]

    async def count_cases_for_user(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> int:
        async with open_database(
            self.database_path
        ) as database:
            cursor = await database.execute(
                """
                SELECT COUNT(*)
                FROM moderation_cases
                WHERE guild_id = ?
                  AND user_id = ?
                """,
                (
                    guild_id,
                    user_id,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return 0

        return int(
            row[0]
        )

    async def set_case_log_message(
        self,
        *,
        case_id: int,
        channel_id: int,
        message_id: int,
    ) -> None:
        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                UPDATE moderation_cases
                SET
                    log_channel_id = ?,
                    log_message_id = ?
                WHERE id = ?
                """,
                (
                    channel_id,
                    message_id,
                    case_id,
                ),
            )

            await database.commit()

    async def get_profile(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> UserModProfile | None:
        async with open_database(
            self.database_path
        ) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM user_mod_profiles
                WHERE guild_id = ?
                  AND user_id = ?
                LIMIT 1
                """,
                (
                    guild_id,
                    user_id,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_profile(
            row
        )

    async def save_profile(
        self,
        *,
        guild_id: int,
        user_id: int,
        channel_id: int,
        message_id: int,
        thread_id: int,
    ) -> UserModProfile:
        now = self._now()

        async with open_database(
            self.database_path
        ) as database:
            await database.execute(
                """
                INSERT INTO user_mod_profiles (
                    guild_id,
                    user_id,
                    channel_id,
                    message_id,
                    thread_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT (
                    guild_id,
                    user_id
                )
                DO UPDATE SET
                    channel_id =
                        excluded.channel_id,
                    message_id =
                        excluded.message_id,
                    thread_id =
                        excluded.thread_id,
                    updated_at =
                        excluded.updated_at
                """,
                (
                    guild_id,
                    user_id,
                    channel_id,
                    message_id,
                    thread_id,
                    now,
                    now,
                ),
            )

            await database.commit()

        profile = await self.get_profile(
            guild_id=guild_id,
            user_id=user_id,
        )

        if profile is None:
            raise RuntimeError(
                "Moderation profile was saved "
                "but could not be read back."
            )

        return profile

    async def delete_profile(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> bool:
        async with open_database(
            self.database_path
        ) as database:
            cursor = await database.execute(
                """
                DELETE FROM user_mod_profiles
                WHERE guild_id = ?
                  AND user_id = ?
                """,
                (
                    guild_id,
                    user_id,
                ),
            )

            await database.commit()

        return cursor.rowcount > 0

    @staticmethod
    def _row_to_case(
        row: DatabaseRow,
    ) -> ModerationCase:
        try:
            details = json.loads(
                row["details_json"]
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            details = {}

        if not isinstance(
            details,
            dict,
        ):
            details = {}

        return ModerationCase(
            id=int(
                row["id"]
            ),
            guild_id=int(
                row["guild_id"]
            ),
            case_number=int(
                row["case_number"]
            ),
            user_id=int(
                row["user_id"]
            ),
            moderator_id=(
                int(
                    row["moderator_id"]
                )
                if (
                    row["moderator_id"]
                    is not None
                )
                else None
            ),
            action=str(
                row["action"]
            ),
            reason=(
                str(
                    row["reason"]
                )
                if (
                    row["reason"]
                    is not None
                )
                else None
            ),
            duration_seconds=(
                int(
                    row[
                        "duration_seconds"
                    ]
                )
                if (
                    row[
                        "duration_seconds"
                    ]
                    is not None
                )
                else None
            ),
            expires_at=(
                str(
                    row["expires_at"]
                )
                if (
                    row["expires_at"]
                    is not None
                )
                else None
            ),
            source=str(
                row["source"]
            ),
            source_reference=(
                str(
                    row[
                        "source_reference"
                    ]
                )
                if (
                    row[
                        "source_reference"
                    ]
                    is not None
                )
                else None
            ),
            details=dict(
                details
            ),
            log_channel_id=(
                int(
                    row[
                        "log_channel_id"
                    ]
                )
                if (
                    row[
                        "log_channel_id"
                    ]
                    is not None
                )
                else None
            ),
            log_message_id=(
                int(
                    row[
                        "log_message_id"
                    ]
                )
                if (
                    row[
                        "log_message_id"
                    ]
                    is not None
                )
                else None
            ),
            created_at=str(
                row["created_at"]
            ),
        )

    @staticmethod
    def _row_to_profile(
        row: DatabaseRow,
    ) -> UserModProfile:
        return UserModProfile(
            guild_id=int(
                row["guild_id"]
            ),
            user_id=int(
                row["user_id"]
            ),
            channel_id=int(
                row["channel_id"]
            ),
            message_id=int(
                row["message_id"]
            ),
            thread_id=int(
                row["thread_id"]
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