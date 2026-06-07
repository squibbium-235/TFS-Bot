from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from src.utils.form_builder import FormAnswer


APPLICATION_STATUS_PENDING = "pending"
APPLICATION_STATUS_APPROVED = "approved"
APPLICATION_STATUS_REJECTED = "rejected"
APPLICATION_STATUS_KICKED = "kicked"
APPLICATION_STATUS_BANNED = "banned"
APPLICATION_STATUS_LEFT = "left"
APPLICATION_STATUS_CANCELLED = "cancelled"


@dataclass(frozen=True)
class StoredApplication:
    id: str
    guild_id: int
    user_id: int
    status: str
    answers: list[FormAnswer]

    review_channel_id: int | None
    review_message_id: int | None

    log_channel_id: int | None
    log_message_id: int | None

    questioning_thread_id: int | None
    question_controls_message_id: int | None

    moderator_id: int | None
    action_reason: str | None
    dm_sent: bool | None

    submitted_at: str
    updated_at: str
    actioned_at: str | None

    @property
    def review_message_url(self) -> str | None:
        if self.review_channel_id is None or self.review_message_id is None:
            return None

        return (
            f"https://discord.com/channels/"
            f"{self.guild_id}/{self.review_channel_id}/{self.review_message_id}"
        )

    @property
    def log_message_url(self) -> str | None:
        if self.log_channel_id is None or self.log_message_id is None:
            return None

        return (
            f"https://discord.com/channels/"
            f"{self.guild_id}/{self.log_channel_id}/{self.log_message_id}"
        )

    @property
    def questioning_thread_url(self) -> str | None:
        if self.questioning_thread_id is None:
            return None

        return (
            f"https://discord.com/channels/"
            f"{self.guild_id}/{self.questioning_thread_id}"
        )

    @property
    def best_message_url(self) -> str | None:
        return self.log_message_url or self.review_message_url


class ApplicationStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)

    async def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY,

                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,

                    status TEXT NOT NULL,

                    answers_json TEXT NOT NULL,

                    review_channel_id INTEGER,
                    review_message_id INTEGER,

                    log_channel_id INTEGER,
                    log_message_id INTEGER,

                    questioning_thread_id INTEGER,
                    question_controls_message_id INTEGER,

                    moderator_id INTEGER,
                    action_reason TEXT,
                    dm_sent INTEGER,

                    submitted_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    actioned_at TEXT
                )
                """
            )

            await self._ensure_column(
                database=database,
                table_name="applications",
                column_name="question_controls_message_id",
                column_definition="INTEGER",
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_applications_guild_user
                ON applications (guild_id, user_id)
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_applications_status
                ON applications (status)
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_applications_questioning_thread
                ON applications (questioning_thread_id)
                """
            )

            await database.commit()

    async def create_application(
        self,
        application_id: str,
        guild_id: int,
        user_id: int,
        answers: list[FormAnswer],
    ) -> None:
        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                INSERT INTO applications (
                    id,
                    guild_id,
                    user_id,
                    status,
                    answers_json,
                    submitted_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id,
                    guild_id,
                    user_id,
                    APPLICATION_STATUS_PENDING,
                    self._serialise_answers(answers),
                    now,
                    now,
                ),
            )

            await database.commit()

    async def set_review_message(
        self,
        application_id: str,
        review_channel_id: int,
        review_message_id: int,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE applications
                SET review_channel_id = ?,
                    review_message_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    review_channel_id,
                    review_message_id,
                    self._now(),
                    application_id,
                ),
            )

            await database.commit()

    async def set_log_message(
        self,
        application_id: str,
        log_channel_id: int,
        log_message_id: int,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE applications
                SET log_channel_id = ?,
                    log_message_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    log_channel_id,
                    log_message_id,
                    self._now(),
                    application_id,
                ),
            )

            await database.commit()

    async def set_questioning_thread(
        self,
        application_id: str,
        questioning_thread_id: int | None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE applications
                SET questioning_thread_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    questioning_thread_id,
                    self._now(),
                    application_id,
                ),
            )

            await database.commit()

    async def set_question_controls_message(
        self,
        application_id: str,
        question_controls_message_id: int | None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE applications
                SET question_controls_message_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    question_controls_message_id,
                    self._now(),
                    application_id,
                ),
            )

            await database.commit()

    async def get_application(
        self,
        application_id: str,
    ) -> StoredApplication | None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE id = ?
                """,
                (application_id,),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_application(row)

    async def get_pending_application_by_questioning_thread(
        self,
        questioning_thread_id: int,
    ) -> StoredApplication | None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE questioning_thread_id = ?
                AND status = ?
                LIMIT 1
                """,
                (questioning_thread_id, APPLICATION_STATUS_PENDING),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_application(row)

    async def get_active_questioning_application_for_user(
        self,
        user_id: int,
    ) -> StoredApplication | None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE user_id = ?
                AND status = ?
                AND questioning_thread_id IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id, APPLICATION_STATUS_PENDING),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_application(row)
    

    async def get_pending_application_for_user(
        self,
        guild_id: int,
        user_id: int,
    ) -> StoredApplication | None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE guild_id = ?
                AND user_id = ?
                AND status = ?
                ORDER BY submitted_at DESC
                LIMIT 1
                """,
                (
                    guild_id,
                    user_id,
                    APPLICATION_STATUS_PENDING,
                ),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_application(row)

    async def list_pending_applications_for_guild(
        self,
        guild_id: int,
    ) -> list[StoredApplication]:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE guild_id = ?
                AND status = ?
                ORDER BY submitted_at ASC
                """,
                (guild_id, APPLICATION_STATUS_PENDING),
            )

            rows = await cursor.fetchall()

        return [self._row_to_application(row) for row in rows]

    async def list_pending_applications(self) -> list[StoredApplication]:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE status = ?
                ORDER BY submitted_at ASC
                """,
                (APPLICATION_STATUS_PENDING,),
            )

            rows = await cursor.fetchall()

        return [self._row_to_application(row) for row in rows]

    async def list_applications_with_log_messages(self) -> list[StoredApplication]:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE log_message_id IS NOT NULL
                ORDER BY actioned_at DESC, updated_at DESC
                """
            )

            rows = await cursor.fetchall()

        return [self._row_to_application(row) for row in rows]

    async def get_previous_application_links(
        self,
        guild_id: int,
        user_id: int,
        exclude_application_id: str | None = None,
        limit: int = 5,
    ) -> list[str]:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM applications
                WHERE guild_id = ?
                AND user_id = ?
                AND id != ?
                ORDER BY submitted_at DESC
                LIMIT ?
                """,
                (
                    guild_id,
                    user_id,
                    exclude_application_id or "",
                    limit,
                ),
            )

            rows = await cursor.fetchall()

        applications = [self._row_to_application(row) for row in rows]

        previous_lines: list[str] = []

        for index, application in enumerate(applications, start=1):
            message_url = application.best_message_url

            if message_url is None:
                continue

            try:
                submitted_at = datetime.fromisoformat(application.submitted_at)
                submitted_text = f"<t:{int(submitted_at.timestamp())}:R>"
            except ValueError:
                submitted_text = "`Unknown date`"

            previous_lines.append(
                f"[Application {index}]({message_url}) - {submitted_text}"
            )

        return previous_lines

    async def mark_actioned(
        self,
        application_id: str,
        status: str,
        moderator_id: int,
        reason: str | None = None,
        dm_sent: bool | None = None,
    ) -> None:
        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE applications
                SET status = ?,
                    moderator_id = ?,
                    action_reason = ?,
                    dm_sent = ?,
                    updated_at = ?,
                    actioned_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    moderator_id,
                    reason,
                    self._bool_to_int(dm_sent),
                    now,
                    now,
                    application_id,
                ),
            )

            await database.commit()

    @staticmethod
    async def _ensure_column(
        database: aiosqlite.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        cursor = await database.execute(f"PRAGMA table_info({table_name})")
        rows = await cursor.fetchall()
        existing_columns = {row[1] for row in rows}

        if column_name in existing_columns:
            return

        await database.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _serialise_answers(answers: list[FormAnswer]) -> str:
        return json.dumps(
            [
                {
                    "key": answer.key,
                    "label": answer.label,
                    "value": answer.value,
                }
                for answer in answers
            ],
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialise_answers(raw_json: str) -> list[FormAnswer]:
        raw_answers = json.loads(raw_json)

        return [
            FormAnswer(
                key=str(answer.get("key") or answer.get("label") or "unknown"),
                label=str(answer.get("label", "")),
                value=str(answer.get("value", "")),
            )
            for answer in raw_answers
        ]

    @staticmethod
    def _bool_to_int(value: bool | None) -> int | None:
        if value is None:
            return None

        return 1 if value else 0

    @staticmethod
    def _int_to_bool(value: int | None) -> bool | None:
        if value is None:
            return None

        return bool(value)

    def _row_to_application(self, row: aiosqlite.Row) -> StoredApplication:
        row_keys = set(row.keys())

        return StoredApplication(
            id=row["id"],
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            status=row["status"],
            answers=self._deserialise_answers(row["answers_json"]),
            review_channel_id=row["review_channel_id"],
            review_message_id=row["review_message_id"],
            log_channel_id=row["log_channel_id"],
            log_message_id=row["log_message_id"],
            questioning_thread_id=row["questioning_thread_id"],
            question_controls_message_id=(
                row["question_controls_message_id"]
                if "question_controls_message_id" in row_keys
                else None
            ),
            moderator_id=row["moderator_id"],
            action_reason=row["action_reason"],
            dm_sent=self._int_to_bool(row["dm_sent"]),
            submitted_at=row["submitted_at"],
            updated_at=row["updated_at"],
            actioned_at=row["actioned_at"],
        )
