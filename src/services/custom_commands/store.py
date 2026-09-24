"""
Per-guild custom commands and their action lists.

Names are 1 to 32 characters: lower-case letters,
digits, hyphens, or underscores. Actions are one
JSON list on the command row. Edits load that list,
change it in memory, then write the whole list
back, so two overlapping edits can overwrite each
other. Cooldowns are clamped to 0 through 86400
seconds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from src.services.database import (
    DatabaseIntegrityError,
    DatabaseRow,
    open_database,
)

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
    """
    One custom command, including its action list.

    The list is mutable. Action helpers edit it in
    place and then save the JSON.
    """
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
    """
    Create and edit custom commands for one guild.

    New commands start enabled, with no actions.
    required_level uses the same names as the
    permission store.
    """
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
        """
        Return a stored command name.

        The name is stripped and lower-cased, then
        must match 1-32 characters of letters,
        digits, hyphens, or underscores.
        """
        name = name.lower().strip()
        
        if not COMMAND_NAME_RE.fullmatch(name):
            raise ValueError(
                "Name must be 1-32 characters using "
                "lowercase letters, numbers, hyphens, "
                "or underscores."
            )
            
        return name
    
    async def initialise(self) -> None:
        async with open_database(
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
        """
        Insert a command with an empty action list.

        A duplicate name raises ValueError. The
        cooldown is clamped to 0 through 86400.
        """
        name = self.normalise_name(name)
        required_level = normalise_level(
            required_level
        )
        
        now = self._now()
        
        async with open_database(self.db_path) as database:
            try:
                await database.execute(
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
                
            except DatabaseIntegrityError as error:
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
        
        async with open_database(
            self.db_path
        ) as database:
            database.row_factory = DatabaseRow
            
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
        async with open_database(
            self.db_path
        ) as database:
            database.row_factory = DatabaseRow
            
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
        
        async with open_database(self.db_path) as database:
            # guild_ID matches guild_id: SQLite folds
            # unquoted identifiers, so this still
            # deletes the intended row.
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
        """
        Change only the fields that were passed.

        None means leave that column alone. If no
        field was passed, the row is not touched
        and this returns false. A missing command
        also returns false.
        """
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

        async with open_database(
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

    async def rename(
        self,
        guild_id: int,
        old_name: str,
        new_name: str,
    ) -> bool:
        """
        Rename a command inside the same guild.

        The same name returns true without writing.
        A name that is already taken raises
        ValueError. A missing old name returns false.
        """
        old_name = self.normalise_name(old_name)
        new_name = self.normalise_name(new_name)

        if old_name == new_name:
            return True

        async with open_database(
            self.db_path
        ) as database:
            cursor = await database.execute(
                """
                SELECT 1
                FROM custom_commands
                WHERE guild_id = ?
                AND name = ?
                """,
                (
                    guild_id,
                    new_name,
                ),
            )

            if await cursor.fetchone() is not None:
                raise ValueError(
                    f"Custom command `{new_name}` already exists."
                )

            cursor = await database.execute(
                """
                UPDATE custom_commands
                SET name = ?,
                    updated_at = ?
                WHERE guild_id = ?
                AND name = ?
                """,
                (
                    new_name,
                    self._now(),
                    guild_id,
                    old_name,
                ),
            )

            await database.commit()

            return cursor.rowcount > 0

    async def update_action(
        self,
        guild_id: int,
        name: str,
        action_number: int,
        action_type: str,
        data: dict[str, Any],
    ) -> bool:
        """
        Replace one action. action_number is 1-based.

        Returns false when the command or the action
        slot does not exist. The whole action object
        is replaced, not merged.
        """
        if action_type not in VALID_ACTIONS:
            raise ValueError(
                f"Unknown action type `{action_type}`."
            )

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

        command.actions[
            action_number - 1
        ] = {
            "type": action_type,
            "data": data,
        }

        await self._save_actions(
            command
        )

        return True

    async def add_action(
        self,
        guild_id: int,
        name: str,
        action_type: str,
        data: dict[str, Any],
    ) -> int:
        """
        Append an action and return its 1-based number.

        A missing command raises ValueError.
        """
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
        """
        Append a field to a send_embed action.

        The action must already be an embed. A
        non-list fields value is replaced with a
        list. Discord's limit of 25 fields is enforced.
        """
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
        """
        Move an action to another 1-based position.

        Both positions must already be inside the
        list; they are not clamped. Returns false
        when the command or either position is missing.
        """
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
        """
        Remove every action and return how many went.

        A missing command returns 0.
        """
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
        """
        Write the in-memory action list back to the row.

        This replaces the whole JSON blob. It does
        not re-read the row, so a concurrent edit
        saved earlier is overwritten.
        """
        async with open_database(
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
        row: DatabaseRow,
    ) -> CustomCommand:
        """
        Build a command from a row.

        actions_json that is not a JSON list becomes
        an empty list, so a damaged row still loads.
        """
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