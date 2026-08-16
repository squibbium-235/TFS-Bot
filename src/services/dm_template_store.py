from __future__ import annotations

from collections import UserDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.services.database import (
    DatabaseRow,
    open_database,
)


DM_TEMPLATE_APPROVED = "approved"
DM_TEMPLATE_DENIED = "denied"
DM_TEMPLATE_KICKED = "kicked"
DM_TEMPLATE_BANNED = "banned"
DM_TEMPLATE_QUESTIONING = "questioning"

DM_TEMPLATE_ORDER = [
    DM_TEMPLATE_APPROVED,
    DM_TEMPLATE_DENIED,
    DM_TEMPLATE_KICKED,
    DM_TEMPLATE_BANNED,
    DM_TEMPLATE_QUESTIONING,
]

DM_TEMPLATE_LABELS = {
    DM_TEMPLATE_APPROVED: "Approved application",
    DM_TEMPLATE_DENIED: "Rejected application",
    DM_TEMPLATE_KICKED: "Kicked after rejection",
    DM_TEMPLATE_BANNED: "Banned after rejection",
    DM_TEMPLATE_QUESTIONING: "Questioning opened",
}

DEFAULT_DM_TEMPLATES = {
    DM_TEMPLATE_APPROVED: (
        "Your verification application for {server_name} has been approved."
    ),
    DM_TEMPLATE_DENIED: (
        "Your verification application for {server_name} has been rejected."
        "{reason_block}"
    ),
    DM_TEMPLATE_KICKED: (
        "Your verification application for {server_name} has been rejected and you "
        "have been kicked from the server."
        "{reason_block}"
    ),
    DM_TEMPLATE_BANNED: (
        "Your verification application for {server_name} has been rejected and you "
        "have been banned from the server."
        "{reason_block}"
    ),
    DM_TEMPLATE_QUESTIONING: (
        "Staff have some questions about your verification application for {server_name}.\n"
        "Reply to this DM to answer them. Your messages and media will be forwarded to staff."
    ),
}


@dataclass(frozen=True)
class StoredDmTemplate:
    guild_id: int
    template_key: str
    template_text: str
    is_custom: bool
    updated_at: str | None


class SafeFormatDict(UserDict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalise_template_key(template_key: str) -> str:
    cleaned = template_key.lower().strip().replace("-", "_").replace(" ", "_")

    if cleaned not in DEFAULT_DM_TEMPLATES:
        valid_keys = ", ".join(DM_TEMPLATE_ORDER)
        raise ValueError(f"Invalid DM template `{template_key}`. Valid templates: {valid_keys}.")

    return cleaned


def render_template_text(template_text: str, context: Mapping[str, Any]) -> str:
    try:
        return template_text.format_map(SafeFormatDict(dict(context)))
    except Exception:
        # A broken template should not stop a moderation action from completing.
        # Return the raw template so the user still gets something instead of silence.
        return template_text


class DmTemplateStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)

    async def initialise(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        async with open_database(self.database_path) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_dm_templates (
                    guild_id INTEGER NOT NULL,
                    template_key TEXT NOT NULL,
                    template_text TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, template_key)
                )
                """
            )

            await database.commit()

    async def get_template(
        self,
        guild_id: int,
        template_key: str,
    ) -> StoredDmTemplate:
        template_key = normalise_template_key(template_key)

        async with open_database(self.database_path) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT template_text, updated_at
                FROM guild_dm_templates
                WHERE guild_id = ?
                AND template_key = ?
                LIMIT 1
                """,
                (guild_id, template_key),
            )

            row = await cursor.fetchone()

        if row is None:
            return StoredDmTemplate(
                guild_id=guild_id,
                template_key=template_key,
                template_text=DEFAULT_DM_TEMPLATES[template_key],
                is_custom=False,
                updated_at=None,
            )

        return StoredDmTemplate(
            guild_id=guild_id,
            template_key=template_key,
            template_text=str(row["template_text"]),
            is_custom=True,
            updated_at=str(row["updated_at"]),
        )

    async def get_all_templates(self, guild_id: int) -> list[StoredDmTemplate]:
        return [
            await self.get_template(guild_id, template_key)
            for template_key in DM_TEMPLATE_ORDER
        ]

    async def set_template(
        self,
        guild_id: int,
        template_key: str,
        template_text: str,
    ) -> None:
        template_key = normalise_template_key(template_key)
        template_text = template_text.strip()

        if not template_text:
            raise ValueError("Template text cannot be empty.")

        async with open_database(self.database_path) as database:
            await database.execute(
                """
                INSERT INTO guild_dm_templates (
                    guild_id,
                    template_key,
                    template_text,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, template_key)
                DO UPDATE SET
                    template_text = excluded.template_text,
                    updated_at = excluded.updated_at
                """,
                (
                    guild_id,
                    template_key,
                    template_text,
                    self._now(),
                ),
            )

            await database.commit()

    async def reset_template(
        self,
        guild_id: int,
        template_key: str,
    ) -> None:
        template_key = normalise_template_key(template_key)

        async with open_database(self.database_path) as database:
            await database.execute(
                """
                DELETE FROM guild_dm_templates
                WHERE guild_id = ?
                AND template_key = ?
                """,
                (guild_id, template_key),
            )

            await database.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
