from __future__ import annotations

import json
from src.services.database import open_sync_database
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SETTING_REVIEW_CHANNEL_ID = "review_channel_id"
SETTING_APPLICATION_LOG_CHANNEL_ID = "application_log_channel_id"
SETTING_VERIFICATION_FORM_KEY = "verification_form_key"
SETTING_APPROVED_ADD_ROLE_ID = "approved_add_role_id"
SETTING_APPROVED_REMOVE_ROLE_ID = "approved_remove_role_id"
SETTING_AUTOMOD_ENABLED = "automod_enabled"

# Optional deployment-provided preset. Put one blocked term per line. Lines starting with # are ignored.
# This keeps the repo from hardcoding nasty terms while still letting the owner load a default list.
DEFAULT_AUTOMOD_TERMS_PATH = Path("data/default_automod_terms.txt")
BUILT_IN_DEFAULT_AUTOMOD_TERMS: tuple[str, ...] = ()


class GuildSettingsStore:
    def __init__(
        self,
        database_path: str = "data/tfsbot.sqlite3",
        legacy_json_path: str = "data/guild_settings.json",
    ) -> None:
        self.database_path = Path(database_path)
        self.legacy_json_path = Path(legacy_json_path)

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialise()

    def initialise(self) -> None:
        with open_sync_database(self.database_path) as database:
            database.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, setting_key)
                )
                """
            )

            database.execute(
                """
                CREATE TABLE IF NOT EXISTS verification_automod_terms (
                    guild_id INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, term)
                )
                """
            )

            database.commit()

        self.migrate_from_legacy_json()

    def migrate_from_legacy_json(self) -> None:
        if not self.legacy_json_path.exists():
            return

        try:
            with self.legacy_json_path.open("r", encoding="utf-8") as file:
                data: dict[str, Any] = json.load(file)

        except (OSError, json.JSONDecodeError):
            return

        guilds = data.get("guilds", {})

        if not isinstance(guilds, dict):
            return

        for raw_guild_id, guild_data in guilds.items():
            if not isinstance(guild_data, dict):
                continue

            try:
                guild_id = int(raw_guild_id)
            except (TypeError, ValueError):
                continue

            for setting_key in (
                SETTING_REVIEW_CHANNEL_ID,
                SETTING_APPLICATION_LOG_CHANNEL_ID,
                SETTING_VERIFICATION_FORM_KEY,
            ):
                value = guild_data.get(setting_key)

                if value is None or str(value).strip() == "":
                    continue

                self._set_value(
                    guild_id=guild_id,
                    setting_key=setting_key,
                    setting_value=str(value),
                    overwrite=False,
                )

    def get_review_channel_id(self, guild_id: int) -> int | None:
        return self._get_int_value(guild_id, SETTING_REVIEW_CHANNEL_ID)

    def set_review_channel_id(self, guild_id: int, channel_id: int) -> None:
        self._set_value(guild_id, SETTING_REVIEW_CHANNEL_ID, str(channel_id))

    def get_application_log_channel_id(self, guild_id: int) -> int | None:
        return self._get_int_value(guild_id, SETTING_APPLICATION_LOG_CHANNEL_ID)

    def set_application_log_channel_id(
        self,
        guild_id: int,
        channel_id: int,
    ) -> None:
        self._set_value(guild_id, SETTING_APPLICATION_LOG_CHANNEL_ID, str(channel_id))

    def get_verification_form_key(self, guild_id: int) -> str | None:
        return self._get_value(guild_id, SETTING_VERIFICATION_FORM_KEY)

    def set_verification_form_key(self, guild_id: int, form_key: str) -> None:
        self._set_value(guild_id, SETTING_VERIFICATION_FORM_KEY, form_key)

    def get_approved_add_role_id(self, guild_id: int) -> int | None:
        return self._get_int_value(guild_id, SETTING_APPROVED_ADD_ROLE_ID)

    def set_approved_add_role_id(self, guild_id: int, role_id: int) -> None:
        self._set_value(guild_id, SETTING_APPROVED_ADD_ROLE_ID, str(role_id))

    def clear_approved_add_role_id(self, guild_id: int) -> None:
        self._delete_value(guild_id, SETTING_APPROVED_ADD_ROLE_ID)

    def get_approved_remove_role_id(self, guild_id: int) -> int | None:
        return self._get_int_value(guild_id, SETTING_APPROVED_REMOVE_ROLE_ID)

    def set_approved_remove_role_id(self, guild_id: int, role_id: int) -> None:
        self._set_value(guild_id, SETTING_APPROVED_REMOVE_ROLE_ID, str(role_id))

    def clear_approved_remove_role_id(self, guild_id: int) -> None:
        self._delete_value(guild_id, SETTING_APPROVED_REMOVE_ROLE_ID)

    def is_automod_enabled(self, guild_id: int) -> bool:
        value = self._get_value(guild_id, SETTING_AUTOMOD_ENABLED)

        if value is None:
            return True

        return value == "1"

    def set_automod_enabled(self, guild_id: int, enabled: bool) -> None:
        self._set_value(guild_id, SETTING_AUTOMOD_ENABLED, "1" if enabled else "0")

    def add_automod_term(self, guild_id: int, term: str) -> None:
        cleaned = self._normalise_automod_term(term)

        if not cleaned:
            raise ValueError("Automod term cannot be empty.")

        with open_sync_database(self.database_path) as database:
            database.execute(
                """
                INSERT OR IGNORE INTO verification_automod_terms (
                    guild_id,
                    term,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (guild_id, cleaned, self._now()),
            )

            database.commit()

    def remove_automod_term(self, guild_id: int, term: str) -> bool:
        cleaned = self._normalise_automod_term(term)

        with open_sync_database(self.database_path) as database:
            cursor = database.execute(
                """
                DELETE FROM verification_automod_terms
                WHERE guild_id = ?
                AND term = ?
                """,
                (guild_id, cleaned),
            )

            database.commit()

        return cursor.rowcount > 0

    def list_automod_terms(self, guild_id: int) -> list[str]:
        with open_sync_database(self.database_path) as database:
            cursor = database.execute(
                """
                SELECT term
                FROM verification_automod_terms
                WHERE guild_id = ?
                ORDER BY term ASC
                """,
                (guild_id,),
            )

            rows = cursor.fetchall()

        return [str(row[0]) for row in rows]

    def clear_automod_terms(self, guild_id: int) -> None:
        with open_sync_database(self.database_path) as database:
            database.execute(
                """
                DELETE FROM verification_automod_terms
                WHERE guild_id = ?
                """,
                (guild_id,),
            )

            database.commit()

    def set_automod_terms(self, guild_id: int, terms: list[str]) -> None:
        cleaned_terms = self._normalise_automod_terms_list(terms)

        with open_sync_database(self.database_path) as database:
            database.execute(
                """
                DELETE FROM verification_automod_terms
                WHERE guild_id = ?
                """,
                (guild_id,),
            )

            for term in cleaned_terms:
                database.execute(
                    """
                    INSERT OR IGNORE INTO verification_automod_terms (
                        guild_id,
                        term,
                        created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (guild_id, term, self._now()),
                )

            database.commit()

    def add_automod_terms(self, guild_id: int, terms: list[str]) -> int:
        cleaned_terms = self._normalise_automod_terms_list(terms)

        added_count = 0

        with open_sync_database(self.database_path) as database:
            for term in cleaned_terms:
                cursor = database.execute(
                    """
                    INSERT OR IGNORE INTO verification_automod_terms (
                        guild_id,
                        term,
                        created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (guild_id, term, self._now()),
                )

                if cursor.rowcount > 0:
                    added_count += 1

            database.commit()

        return added_count

    def get_default_automod_terms(self) -> list[str]:
        terms: list[str] = list(BUILT_IN_DEFAULT_AUTOMOD_TERMS)

        if DEFAULT_AUTOMOD_TERMS_PATH.exists():
            try:
                raw_lines = DEFAULT_AUTOMOD_TERMS_PATH.read_text(encoding="utf-8").splitlines()
            except OSError:
                raw_lines = []

            for raw_line in raw_lines:
                stripped = raw_line.strip()

                if not stripped or stripped.startswith("#"):
                    continue

                terms.append(stripped)

        return self._normalise_automod_terms_list(terms)

    def add_default_automod_terms(self, guild_id: int) -> int:
        return self.add_automod_terms(
            guild_id=guild_id,
            terms=self.get_default_automod_terms(),
        )

    def _get_value(self, guild_id: int, setting_key: str) -> str | None:
        with open_sync_database(self.database_path) as database:
            cursor = database.execute(
                """
                SELECT setting_value
                FROM guild_settings
                WHERE guild_id = ?
                AND setting_key = ?
                LIMIT 1
                """,
                (guild_id, setting_key),
            )

            row = cursor.fetchone()

        if row is None:
            return None

        return str(row[0])

    def _get_int_value(self, guild_id: int, setting_key: str) -> int | None:
        value = self._get_value(guild_id, setting_key)

        if value is None:
            return None

        try:
            return int(value)
        except ValueError:
            return None

    def _delete_value(self, guild_id: int, setting_key: str) -> None:
        with open_sync_database(self.database_path) as database:
            database.execute(
                """
                DELETE FROM guild_settings
                WHERE guild_id = ?
                AND setting_key = ?
                """,
                (guild_id, setting_key),
            )

            database.commit()

    def _set_value(
        self,
        guild_id: int,
        setting_key: str,
        setting_value: str,
        *,
        overwrite: bool = True,
    ) -> None:
        if overwrite:
            query = """
                INSERT INTO guild_settings (
                    guild_id,
                    setting_key,
                    setting_value,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, setting_key)
                DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
            """
        else:
            query = """
                INSERT OR IGNORE INTO guild_settings (
                    guild_id,
                    setting_key,
                    setting_value,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
            """

        with open_sync_database(self.database_path) as database:
            database.execute(
                query,
                (
                    guild_id,
                    setting_key,
                    setting_value,
                    self._now(),
                ),
            )

            database.commit()

    @classmethod
    def _normalise_automod_terms_list(cls, terms: list[str] | tuple[str, ...]) -> list[str]:
        cleaned_terms: list[str] = []
        seen: set[str] = set()

        for term in terms:
            cleaned = cls._normalise_automod_term(term)

            if not cleaned or cleaned in seen:
                continue

            cleaned_terms.append(cleaned)
            seen.add(cleaned)

        return cleaned_terms

    @staticmethod
    def _normalise_automod_term(term: str) -> str:
        return term.strip().casefold()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
