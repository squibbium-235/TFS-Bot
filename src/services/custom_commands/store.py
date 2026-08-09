from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from src.services.permission_store import(
    LEVEL_PUBLIC,
    normalise_level,
)


COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]{1,32}$")

SEND_MESSAGE = "send_message"
SEND_EMBED = "send_embed"
ADD_REACTION = "add_reaction"
ADD_ROLE = "add_role"
REMOVE_ROLE = "remove_role"
DELETE_MESSAGE = "delete_message"

VALID_ACTIONS = {
    SEND_MESSAGE,
    SEND_EMBED,
    ADD_REACTION,
    ADD_ROLE,
    REMOVE_ROLE,
    DELETE_MESSAGE,
}

@dataclass
class CustomCommand:
    guild_id: int
    name: str
    description: str
    enabled: bool
    required_level: str
    cooldown_seconds: int
    delete_trigger: bool
    created_by: int
    actions: list[dict[str, Any]]
    created_at: str
    updated_at: str
    
class CustomCommandStore:
    def __init__(
        self,
        db_path: str = "data/tfsbot.sqlite3",
    ) -> None:
        path = Path(db_path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        
        self.db_path = str(path)
        
    @staticmethod
    def _now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()
        
    @staticmethod
    def normalise_name(name: str) -> str:
        name = name.lower().strip()
        
        if not COMMAND_NAME_RE.fullmatch(name):
            raise ValueError(
                "Name must be 1-32 characters using "
                "lowercase letters, numbers, hyphens, "
                "or underscores."
            )
            
        return name
    
    async def initialise(self) -> None:
        async with aiosqlite.connect(
            self.db_path
        ) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS custom_commands (
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    required_level TEXT NOT NULL DEFAULT 'public',
                    cooldown_seconds INTEGER NOT NULL DEFAULT 0,
                    delete_trigger INTEGER NOT NULL DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, name)
                )
                """
            )
            
            await database.commit()
            
    async def create(
        self,
        guild_id: int,
        name: str,
        description: str,
        created_by: int,
        required_level: str = LEVEL_PUBLIC,
        cooldown_seconds: int = 0,
        delete_trigger: bool = False,
    ) -> None:
        name = self.normalise_name(name)
        required_level = normalise_level(
            required_level
        )
        
        now = self._now
        
        async with aiosqlite.connect(self.db_path) as database:
            try:
                await database.execure(
                    """
                    INSERT INTO custom_commands (
                        guild_id,
                        name,
                        description,
                        enabled,
                        required_level,
                        cooldown_seconds,
                        delete_trigger,
                        created_by,
                        actions_json,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?,
                        ?,
                        ?,
                        1,
                        ?,
                        ?,
                        ?,
                        ?,
                        '[]',
                        ?,
                        ?
                    )
                    """,
                    (
                        guild_id,
                        name,
                        description.strip(),
                        required_level,
                        max(
                            0,
                            min(
                                cooldown_seconds,
                                86400,
                            ),
                        ),
                        int(delete_trigger),
                        created_by,
                        now,
                        now,
                    ),
                )
                
            except aiosqlite.IntegrityError as error:
                raise ValueError(
                    f"Custom command \"{name}\" already exists."
                ) from error
                
            await database.commit()
            
    async def get(
        self,
        guild_id: int,
        name: str,
    ) -> CustomCommand | None:
        name = self.normalise_name(name)
        
        async with aiosqlite.connect(
            self.db_path
        ) as database:
            database.row_factory = aiosqlite.Row
            
            cursor = await database.execute(
                """
                SELECT *
                FROM custom_commands
                WHERE guild_id = ?
                AND name = ?
                """,
                (
                    guild_id,
                    name,
                ),
            )
            
            row = await cursor.fetchone()
            
        if row is None:
            return None
        
        return self._from_row(row)
    
    async def list(
        self,
        guild_id: int,
    ) -> list[CustomCommand]:
        async with aiosqlite.connect(
            self.db_path
        ) as database:
            database.row_factory = aiosqlite.Row
            
            cursor = await database.execute(
                """
                SELECT *
                FROM custom_commands
                WHERE guild_id = ?
                ORDER BY name
                """,
                (guild_id,),
            )
            
            rows = await cursor.fetchall()
            
        return [
            self._from_row(row)
            for row in rows
        ]
        
    async def delete(
        self,
        guild_id: int,
        name: str,
    ) -> bool:
        name = self.normalise_name(name)
        
        async with aiosqlite.connect(self.db_path) as database:
            cursor = await database.execute(
                """
                DELETE FROM custom_commands
                WHERE guild_ID = ?
                AND name = ?
                """,
                (
                    guild_id,
                    name,
                ),
            )
            
            await database.commit()
            
            return cursor.rowcount > 0
        
    async def update(
        self,
        guild_id: int,
        name: str,
        *,
        description: str | None = None,
        enabled: bool | None = None,
        required_level: str | None = None,
        cooldown_seconds: int | None = None,
        delete_trigger: bool | None = None,
    ) -> bool:
        name = self.normalise_name(name)
        
        fields: list[str] = []
        values: list[object] = []
        
        if description is not None:
            fields.append(
                "description = ?"
            )
            values.append(
                description.strip()
            )
            
        if enabled is not None:
            fields.append(
                "enabled = ?"
            )
            values.append(
                int(enabled)
            )
            
        if required_level is not None:
            fields.append(
                "required_level = ?"
            )
            values.append(
                normalise_level(
                    required_level
                )
            )
            
        if cooldown_seconds is not None:
            fields.append(
                "cooldown_seconds = ?"
            )
            values.append(
                max(
                    0,
                    min(
                        cooldown_seconds,
                        86400,
                    ),
                )
            )
            
        if delete_trigger is not None:
            fields.append(
                "delete_trigger = ?"
            )
            values.append(
                int(delete_trigger)
            )

        if not fields:
            return False

        fields.append(
            "updated_at = ?"
        )

        values.extend(
            (
                self._now(),
                guild_id,
                name,
            )
        )

        async with aiosqlite.connect(
            self.db_path
        ) as database:
            cursor = await database.execute(
                f"""
                UPDATE custom_commands
                SET {", ".join(fields)}
                WHERE guild_id = ?
                AND name = ?
                """,
                values,
            )

            await database.commit()

            return cursor.rowcount > 0

    async def add_action(
        self,
        guild_id: int,
        name: str,
        action_type: str,
        data: dict[str, Any],
    ) -> int:
        if action_type not in VALID_ACTIONS:
            raise ValueError(
                f"Unknown action type "
                f"`{action_type}`."
            )

        command = await self.get(
            guild_id,
            name,
        )

        if command is None:
            raise ValueError(
                f"Custom command `{name}` "
                "does not exist."
            )

        command.actions.append(
            {
                "type": action_type,
                "data": data,
            }
        )

        await self._save_actions(
            command
        )

        return len(command.actions)

    async def add_embed_field(
        self,
        guild_id: int,
        name: str,
        action_number: int,
        field: dict[str, Any],
    ) -> None:
        command = await self.get(
            guild_id,
            name,
        )

        if command is None:
            raise ValueError(
                "That command does not exist."
            )

        if not (
            1
            <= action_number
            <= len(command.actions)
        ):
            raise ValueError(
                "That action does not exist."
            )

        action = command.actions[
            action_number - 1
        ]

        if action.get("type") != SEND_EMBED:
            raise ValueError(
                "That action is not an embed."
            )

        data = action.setdefault(
            "data",
            {},
        )

        fields = data.setdefault(
            "fields",
            [],
        )

        if not isinstance(fields, list):
            fields = []
            data["fields"] = fields

        if len(fields) >= 25:
            raise ValueError(
                "Discord embeds can contain "
                "at most 25 fields."
            )

        fields.append(field)

        await self._save_actions(
            command
        )

    async def remove_action(
        self,
        guild_id: int,
        name: str,
        action_number: int,
    ) -> bool:
        command = await self.get(
            guild_id,
            name,
        )

        if command is None:
            return False

        if not (
            1
            <= action_number
            <= len(command.actions)
        ):
            return False

        command.actions.pop(
            action_number - 1
        )

        await self._save_actions(
            command
        )

        return True

    async def move_action(
        self,
        guild_id: int,
        name: str,
        action_number: int,
        new_position: int,
    ) -> bool:
        command = await self.get(
            guild_id,
            name,
        )

        if command is None:
            return False

        action_count = len(
            command.actions
        )

        if not (
            1
            <= action_number
            <= action_count
        ):
            return False

        if not (
            1
            <= new_position
            <= action_count
        ):
            return False

        action = command.actions.pop(
            action_number - 1
        )

        command.actions.insert(
            new_position - 1,
            action,
        )

        await self._save_actions(
            command
        )

        return True

    async def clear_actions(
        self,
        guild_id: int,
        name: str,
    ) -> int:
        command = await self.get(
            guild_id,
            name,
        )

        if command is None:
            return 0

        removed_count = len(
            command.actions
        )

        command.actions.clear()

        await self._save_actions(
            command
        )

        return removed_count

    async def _save_actions(
        self,
        command: CustomCommand,
    ) -> None:
        async with aiosqlite.connect(
            self.db_path
        ) as database:
            await database.execute(
                """
                UPDATE custom_commands
                SET actions_json = ?,
                    updated_at = ?
                WHERE guild_id = ?
                AND name = ?
                """,
                (
                    json.dumps(
                        command.actions,
                        ensure_ascii=False,
                    ),
                    self._now(),
                    command.guild_id,
                    command.name,
                ),
            )

            await database.commit()

    @staticmethod
    def _from_row(
        row: aiosqlite.Row,
    ) -> CustomCommand:
        try:
            actions = json.loads(
                row["actions_json"]
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ):
            actions = []

        if not isinstance(
            actions,
            list,
        ):
            actions = []

        return CustomCommand(
            guild_id=int(
                row["guild_id"]
            ),
            name=str(
                row["name"]
            ),
            description=str(
                row["description"]
            ),
            enabled=bool(
                row["enabled"]
            ),
            required_level=str(
                row["required_level"]
            ),
            cooldown_seconds=int(
                row["cooldown_seconds"]
            ),
            delete_trigger=bool(
                row["delete_trigger"]
            ),
            created_by=int(
                row["created_by"]
            ),
            actions=actions,
            created_at=str(
                row["created_at"]
            ),
            updated_at=str(
                row["updated_at"]
            ),
        )