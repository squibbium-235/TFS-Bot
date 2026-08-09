from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import discord

from src.services.forms.form_loader import FormConfig, FormLoader
from src.utils.form_builder import FormQuestion


FORM_KEY_VERIFICATION = "verification"

VALID_QUESTION_KEY_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")



def get_default_verification_form_config() -> FormConfig:
    return FormConfig(
        title="Verification Application",
        custom_id_prefix="verify:application",
        questions=[
            FormQuestion(
                key="name",
                label="What's your name?",
                style=discord.TextStyle.short,
                placeholder="Or perhaps, a preferred nickname instead?",
                required=True,
                min_length=1,
                max_length=100,
            ),
            FormQuestion(
                key="gender",
                label="What gender do you identify with?",
                style=discord.TextStyle.short,
                placeholder="What are your pronouns?",
                required=True,
                min_length=1,
                max_length=100,
            ),
            FormQuestion(
                key="age",
                label="What's your exact age?",
                style=discord.TextStyle.short,
                placeholder="Do NOT add ranges - lying will result in a ban.",
                required=True,
                min_length=1,
                max_length=100,
            ),
            FormQuestion(
                key="hobbies",
                label="What are your hobbies/interests?",
                style=discord.TextStyle.paragraph,
                placeholder="Tell us a bit about yoursel! Please be descriptive as low effort applications will not be accepted",
                required=True,
                min_length=1,
                max_length=1000,
            ),
            FormQuestion(
                key="where",
                label="How/where did you find TFS?",
                style=discord.TextStyle.paragraph,
                placeholder="Be specific: discovery, Disboard, etc. If it was a friend, please provide their username.",
                required=True,
                min_length=1,
                max_length=500,
            ),
            FormQuestion(
                key="long",
                label="How long have you been in the fandom?",
                style=discord.TextStyle.short,
                placeholder="if you aren't a furry, just say \"N/A\"!",
                required=True,
                min_length=1,
                max_length=500,
            ),
            FormQuestion(
                key="getin",
                label="How did you get into the furry fandom?",
                style=discord.TextStyle.paragraph,
                placeholder="If you aren't a furry, please let us know why you want to join the server!",
                required=True,
                min_length=1,
                max_length=1000,
            ),
            FormQuestion(
                key="rules",
                label="Have you read and agreed to the #Rules?",
                style=discord.TextStyle.short,
                placeholder="If not, please review them before verifying!",
                required=True,
                min_length=1,
                max_length=50,
            ),
        ],
    )

@dataclass(frozen=True)
class StoredForm:
    guild_id: int
    form_key: str
    title: str
    custom_id_prefix: str
    created_at: str
    updated_at: str

@dataclass(frozen=True)
class StoredFormQuestion:
    id: int
    guild_id: int
    form_key: str
    question_key: str
    label: str
    style: str
    required: bool
    placeholder: str | None
    min_length: int | None
    max_length: int | None
    sort_order: int


class FormStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)

    async def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS forms (
                    guild_id INTEGER NOT NULL,
                    form_key TEXT NOT NULL,

                    title TEXT NOT NULL,
                    custom_id_prefix TEXT NOT NULL,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    PRIMARY KEY (guild_id, form_key)
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS form_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    guild_id INTEGER NOT NULL,
                    form_key TEXT NOT NULL,

                    question_key TEXT NOT NULL,
                    label TEXT NOT NULL,
                    style TEXT NOT NULL,

                    required INTEGER NOT NULL,
                    placeholder TEXT,
                    min_length INTEGER,
                    max_length INTEGER,

                    sort_order INTEGER NOT NULL,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    UNIQUE (guild_id, form_key, question_key),

                    FOREIGN KEY (guild_id, form_key)
                    REFERENCES forms (guild_id, form_key)
                    ON DELETE CASCADE
                )
                """
            )

            await database.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_form_questions_lookup
                ON form_questions (guild_id, form_key, sort_order)
                """
            )

            await database.commit()

    async def ensure_form_from_json(
        self,
        guild_id: int,
        form_key: str,
        json_path: str,
    ) -> None:
        existing_form = await self.get_form_config_or_none(
            guild_id=guild_id,
            form_key=form_key,
        )

        if existing_form is not None:
            return

        form = self._load_form_or_default(form_key, json_path)
        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                INSERT INTO forms (
                    guild_id,
                    form_key,
                    title,
                    custom_id_prefix,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    form_key,
                    form.title,
                    form.custom_id_prefix,
                    now,
                    now,
                ),
            )

            for index, question in enumerate(form.questions, start=1):
                await database.execute(
                    """
                    INSERT INTO form_questions (
                        guild_id,
                        form_key,
                        question_key,
                        label,
                        style,
                        required,
                        placeholder,
                        min_length,
                        max_length,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        form_key,
                        question.key,
                        question.label,
                        self._style_to_string(question.style),
                        self._bool_to_int(question.required),
                        question.placeholder,
                        question.min_length,
                        question.max_length,
                        index,
                        now,
                        now,
                    ),
                )

            await database.commit()

    async def reset_form_from_json(
        self,
        guild_id: int,
        form_key: str,
        json_path: str,
    ) -> None:
        form = self._load_form_or_default(form_key, json_path)
        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                DELETE FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (guild_id, form_key),
            )

            await database.execute(
                """
                INSERT INTO forms (
                    guild_id,
                    form_key,
                    title,
                    custom_id_prefix,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, form_key)
                DO UPDATE SET
                    title = excluded.title,
                    custom_id_prefix = excluded.custom_id_prefix,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id,
                    form_key,
                    form.title,
                    form.custom_id_prefix,
                    now,
                    now,
                ),
            )

            for index, question in enumerate(form.questions, start=1):
                await database.execute(
                    """
                    INSERT INTO form_questions (
                        guild_id,
                        form_key,
                        question_key,
                        label,
                        style,
                        required,
                        placeholder,
                        min_length,
                        max_length,
                        sort_order,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        form_key,
                        question.key,
                        question.label,
                        self._style_to_string(question.style),
                        self._bool_to_int(question.required),
                        question.placeholder,
                        question.min_length,
                        question.max_length,
                        index,
                        now,
                        now,
                    ),
                )

            await database.commit()

    async def reset_verification_form_from_json(
        self,
        guild_id: int,
        json_path: str,
    ) -> None:
        await self.reset_form_from_json(
            guild_id=guild_id,
            form_key=FORM_KEY_VERIFICATION,
            json_path=json_path,
        )

    async def list_forms(
        self,
        guild_id: int,
    ) -> list[StoredForm]:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM forms
                WHERE guild_id = ?
                ORDER BY form_key ASC
                """,
                (guild_id,),
            )

            rows = await cursor.fetchall()

        return [
            StoredForm(
                guild_id=row["guild_id"],
                form_key=row["form_key"],
                title=row["title"],
                custom_id_prefix=row["custom_id_prefix"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def get_form_config(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
    ) -> FormConfig:
        await self.ensure_form_from_json(
            guild_id=guild_id,
            form_key=form_key,
            json_path=fallback_json_path,
        )

        form = await self.get_form_config_or_none(
            guild_id=guild_id,
            form_key=form_key,
        )

        if form is None:
            raise RuntimeError("Form could not be loaded.")

        return form

    async def get_form_config_or_none(
        self,
        guild_id: int,
        form_key: str,
    ) -> FormConfig | None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            form_cursor = await database.execute(
                """
                SELECT *
                FROM forms
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (guild_id, form_key),
            )

            form_row = await form_cursor.fetchone()

            if form_row is None:
                return None

            question_cursor = await database.execute(
                """
                SELECT *
                FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                ORDER BY sort_order ASC
                """,
                (guild_id, form_key),
            )

            question_rows = await question_cursor.fetchall()

        questions = [
            FormQuestion(
                key=row["question_key"],
                label=row["label"],
                style=self._string_to_style(row["style"]),
                placeholder=row["placeholder"],
                required=self._int_to_bool(row["required"]),
                min_length=row["min_length"],
                max_length=row["max_length"],
            )
            for row in question_rows
        ]

        return FormConfig(
            title=form_row["title"],
            custom_id_prefix=form_row["custom_id_prefix"],
            questions=questions,
        )

    async def list_questions(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
    ) -> list[StoredFormQuestion]:
        await self.ensure_form_from_json(
            guild_id=guild_id,
            form_key=form_key,
            json_path=fallback_json_path,
        )

        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                ORDER BY sort_order ASC
                """,
                (guild_id, form_key),
            )

            rows = await cursor.fetchall()

        return [self._row_to_question(row) for row in rows]

    async def get_question(
        self,
        guild_id: int,
        form_key: str,
        question_key: str,
        fallback_json_path: str,
    ) -> StoredFormQuestion | None:
        await self.ensure_form_from_json(
            guild_id=guild_id,
            form_key=form_key,
            json_path=fallback_json_path,
        )

        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT *
                FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                AND question_key = ?
                """,
                (guild_id, form_key, question_key),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_question(row)

    async def add_question(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
        question_key: str,
        label: str,
        style: str,
        required: bool,
        placeholder: str | None,
        min_length: int | None,
        max_length: int | None,
    ) -> None:
        self._validate_question_values(
            question_key=question_key,
            label=label,
            style=style,
            placeholder=placeholder,
            min_length=min_length,
            max_length=max_length,
        )

        await self.ensure_form_from_json(
            guild_id=guild_id,
            form_key=form_key,
            json_path=fallback_json_path,
        )

        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            cursor = await database.execute(
                """
                SELECT COALESCE(MAX(sort_order), 0) + 1
                FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (guild_id, form_key),
            )

            next_sort_order = (await cursor.fetchone())[0]

            await database.execute(
                """
                INSERT INTO form_questions (
                    guild_id,
                    form_key,
                    question_key,
                    label,
                    style,
                    required,
                    placeholder,
                    min_length,
                    max_length,
                    sort_order,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    form_key,
                    question_key,
                    label,
                    style,
                    self._bool_to_int(required),
                    placeholder,
                    min_length,
                    max_length,
                    next_sort_order,
                    now,
                    now,
                ),
            )

            await database.execute(
                """
                UPDATE forms
                SET updated_at = ?
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (now, guild_id, form_key),
            )

            await database.commit()

    async def update_question(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
        question_key: str,
        label: str | None = None,
        style: str | None = None,
        required: bool | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        clear_placeholder: bool = False,
        clear_lengths: bool = False,
    ) -> bool:
        existing = await self.get_question(
            guild_id=guild_id,
            form_key=form_key,
            question_key=question_key,
            fallback_json_path=fallback_json_path,
        )

        if existing is None:
            return False

        new_label = label if label is not None else existing.label
        new_style = style if style is not None else existing.style
        new_required = required if required is not None else existing.required

        if clear_placeholder:
            new_placeholder = None
        elif placeholder is not None:
            new_placeholder = placeholder
        else:
            new_placeholder = existing.placeholder

        if clear_lengths:
            new_min_length = None
            new_max_length = None
        else:
            new_min_length = min_length if min_length is not None else existing.min_length
            new_max_length = max_length if max_length is not None else existing.max_length

        self._validate_question_values(
            question_key=question_key,
            label=new_label,
            style=new_style,
            placeholder=new_placeholder,
            min_length=new_min_length,
            max_length=new_max_length,
        )

        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            await database.execute(
                """
                UPDATE form_questions
                SET label = ?,
                    style = ?,
                    required = ?,
                    placeholder = ?,
                    min_length = ?,
                    max_length = ?,
                    updated_at = ?
                WHERE guild_id = ?
                AND form_key = ?
                AND question_key = ?
                """,
                (
                    new_label,
                    new_style,
                    self._bool_to_int(new_required),
                    new_placeholder,
                    new_min_length,
                    new_max_length,
                    now,
                    guild_id,
                    form_key,
                    question_key,
                ),
            )

            await database.execute(
                """
                UPDATE forms
                SET updated_at = ?
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (now, guild_id, form_key),
            )

            await database.commit()

        return True

    async def delete_question(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
        question_key: str,
    ) -> bool:
        await self.ensure_form_from_json(
            guild_id=guild_id,
            form_key=form_key,
            json_path=fallback_json_path,
        )

        async with aiosqlite.connect(self.database_path) as database:
            cursor = await database.execute(
                """
                DELETE FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                AND question_key = ?
                """,
                (guild_id, form_key, question_key),
            )

            deleted = cursor.rowcount > 0

            await database.commit()

        if deleted:
            await self.compact_question_order(guild_id, form_key)

        return deleted

    async def move_question(
        self,
        guild_id: int,
        form_key: str,
        fallback_json_path: str,
        question_key: str,
        new_position: int,
    ) -> bool:
        questions = await self.list_questions(
            guild_id=guild_id,
            form_key=form_key,
            fallback_json_path=fallback_json_path,
        )

        matching_question = next(
            (
                question
                for question in questions
                if question.question_key == question_key
            ),
            None,
        )

        if matching_question is None:
            return False

        questions_without_target = [
            question
            for question in questions
            if question.question_key != question_key
        ]

        clamped_position = max(1, min(new_position, len(questions)))
        insert_index = clamped_position - 1

        questions_without_target.insert(insert_index, matching_question)

        now = self._now()

        async with aiosqlite.connect(self.database_path) as database:
            for index, question in enumerate(questions_without_target, start=1):
                await database.execute(
                    """
                    UPDATE form_questions
                    SET sort_order = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (index, now, question.id),
                )

            await database.execute(
                """
                UPDATE forms
                SET updated_at = ?
                WHERE guild_id = ?
                AND form_key = ?
                """,
                (now, guild_id, form_key),
            )

            await database.commit()

        return True

    async def compact_question_order(
        self,
        guild_id: int,
        form_key: str,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT id
                FROM form_questions
                WHERE guild_id = ?
                AND form_key = ?
                ORDER BY sort_order ASC
                """,
                (guild_id, form_key),
            )

            rows = await cursor.fetchall()
            now = self._now()

            for index, row in enumerate(rows, start=1):
                await database.execute(
                    """
                    UPDATE form_questions
                    SET sort_order = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (index, now, row["id"]),
                )

            await database.commit()

    @staticmethod
    def _load_form_or_default(form_key: str, json_path: str) -> FormConfig:
        form_path = Path(json_path)

        if form_path.exists():
            return FormLoader.load_form(form_path)

        if form_key == FORM_KEY_VERIFICATION:
            return get_default_verification_form_config()

        raise FileNotFoundError(f"Form config does not exist: {form_path}")

    @staticmethod
    def _validate_question_values(
        question_key: str,
        label: str,
        style: str,
        placeholder: str | None,
        min_length: int | None,
        max_length: int | None,
    ) -> None:
        if not VALID_QUESTION_KEY_PATTERN.fullmatch(question_key):
            raise ValueError(
                "Question key must be 1-80 characters and only use lowercase letters, numbers, and underscores."
            )

        if not label.strip():
            raise ValueError("Question label cannot be empty.")

        if len(label) > 45:
            raise ValueError("Question label cannot be longer than 45 characters.")

        if style not in {"short", "paragraph"}:
            raise ValueError("Style must be either short or paragraph.")

        if placeholder is not None and len(placeholder) > 100:
            raise ValueError("Placeholder cannot be longer than 100 characters.")

        if min_length is not None and min_length < 0:
            raise ValueError("Minimum length cannot be negative.")

        if max_length is not None and max_length < 1:
            raise ValueError("Maximum length must be at least 1.")

        if max_length is not None and max_length > 4000:
            raise ValueError("Maximum length cannot be higher than 4000.")

        if (
            min_length is not None
            and max_length is not None
            and min_length > max_length
        ):
            raise ValueError("Minimum length cannot be higher than maximum length.")

    @staticmethod
    def _style_to_string(style: discord.TextStyle | str) -> str:
        if isinstance(style, str):
            lowered = style.lower().strip()

            if lowered in {"short", "paragraph"}:
                return lowered

        if style == discord.TextStyle.short:
            return "short"

        return "paragraph"

    @staticmethod
    def _string_to_style(style: str) -> discord.TextStyle:
        if style == "short":
            return discord.TextStyle.short

        return discord.TextStyle.paragraph

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _bool_to_int(value: bool) -> int:
        return 1 if value else 0

    @staticmethod
    def _int_to_bool(value: int) -> bool:
        return bool(value)

    def _row_to_question(self, row: aiosqlite.Row) -> StoredFormQuestion:
        return StoredFormQuestion(
            id=row["id"],
            guild_id=row["guild_id"],
            form_key=row["form_key"],
            question_key=row["question_key"],
            label=row["label"],
            style=row["style"],
            required=self._int_to_bool(row["required"]),
            placeholder=row["placeholder"],
            min_length=row["min_length"],
            max_length=row["max_length"],
            sort_order=row["sort_order"],
        )