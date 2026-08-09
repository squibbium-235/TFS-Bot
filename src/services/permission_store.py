from __future__ import annotations

import os
from pathlib import Path

import aiosqlite


LEVEL_PUBLIC = "public"
LEVEL_STAFF = "staff"
LEVEL_ADMIN = "admin"
LEVEL_OWNER = "owner"

LEVEL_VALUES = {
    LEVEL_PUBLIC: 0,
    LEVEL_STAFF: 1,
    LEVEL_ADMIN: 2,
    LEVEL_OWNER: 3,
}

LEVEL_NAMES = {
    LEVEL_PUBLIC: "Public",
    LEVEL_STAFF: "Staff",
    LEVEL_ADMIN: "Admin",
    LEVEL_OWNER: "Owner / Bot Dev",
}


DEFAULT_COMMAND_LEVELS = {
    # Public / normal-user-safe commands
    "ping": LEVEL_PUBLIC,
    "info": LEVEL_PUBLIC,

    # Users can check their own permission level
    "permissions.my_level": LEVEL_PUBLIC,

    # Form commands
    "form.create": LEVEL_OWNER,
    "form.list": LEVEL_OWNER,
    "form.view": LEVEL_OWNER,
    "form.preview": LEVEL_STAFF,
    "form.add": LEVEL_OWNER,
    "form.edit": LEVEL_OWNER,
    "form.delete": LEVEL_OWNER,
    "form.move": LEVEL_OWNER,
    "form.delete_form": LEVEL_OWNER,
    "form.reset_verification": LEVEL_OWNER,
    "form.publish": LEVEL_OWNER,
    "form.submissions": LEVEL_STAFF,

    # Verification setup/config commands
    "verification.panel": LEVEL_OWNER,
    "verification.review_channel": LEVEL_OWNER,
    "verification.log_channel": LEVEL_OWNER,
    "verification.approved_add_role": LEVEL_OWNER,
    "verification.approved_remove_role": LEVEL_OWNER,
    "verification.clear_approved_add_role": LEVEL_OWNER,
    "verification.clear_approved_remove_role": LEVEL_OWNER,
    "verification.automod_enabled": LEVEL_OWNER,
    "verification.automod_add": LEVEL_OWNER,
    "verification.automod_remove": LEVEL_OWNER,
    "verification.automod_list": LEVEL_OWNER,
    "verification.cancel_user": LEVEL_OWNER,
    "verification.cancel_all": LEVEL_OWNER,

    # Permission config commands
    "permissions.view": LEVEL_OWNER,
    "permissions.set_role": LEVEL_OWNER,
    "permissions.clear_role": LEVEL_OWNER,
    "permissions.set_command": LEVEL_OWNER,
    "permissions.reset_command": LEVEL_OWNER,
}


def normalise_level(level: str) -> str:
    cleaned = level.lower().strip().replace("-", "_").replace(" ", "_")

    if cleaned not in LEVEL_VALUES:
        raise ValueError(
            f"Invalid permission level `{level}`. "
            "Use public, staff, admin, or owner."
        )

    return cleaned


def normalise_command_key(command_key: str) -> str:
    return (
        command_key.lower()
        .strip()
        .replace(" ", ".")
        .replace("-", "_")
    )


def get_bot_dev_user_ids() -> set[int]:
    raw_value = os.getenv("BOT_DEV_USER_IDS", "")
    user_ids: set[int] = set()

    for item in raw_value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            user_ids.add(int(item))
        except ValueError:
            continue

    return user_ids


class PermissionStore:
    def __init__(self, db_path: str = "data/tfsbot.sqlite3") -> None:
        db_path_object = Path(db_path)
        db_path_object.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = str(db_path_object)

    async def initialise(self) -> None:
        async with aiosqlite.connect(self.db_path) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS permission_roles (
                    guild_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    role_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, level)
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS permission_command_levels (
                    guild_id INTEGER NOT NULL,
                    command_key TEXT NOT NULL,
                    level TEXT NOT NULL,
                    PRIMARY KEY (guild_id, command_key)
                )
                """
            )

            await database.commit()

    async def get_required_level_name(
        self,
        guild_id: int,
        command_key: str,
    ) -> str:
        command_key = normalise_command_key(command_key)
        parent_key = command_key.split(".")[0]

        async with aiosqlite.connect(self.db_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT level
                FROM permission_command_levels
                WHERE guild_id = ?
                AND command_key IN (?, ?)
                ORDER BY
                    CASE command_key
                        WHEN ? THEN 0
                        WHEN ? THEN 1
                        ELSE 2
                    END
                LIMIT 1
                """,
                (
                    guild_id,
                    command_key,
                    parent_key,
                    command_key,
                    parent_key,
                ),
            )

            row = await cursor.fetchone()

        if row is not None:
            return normalise_level(str(row["level"]))

        raw_level = (
            DEFAULT_COMMAND_LEVELS.get(command_key)
            or DEFAULT_COMMAND_LEVELS.get(parent_key)
            or LEVEL_PUBLIC
        )

        return normalise_level(raw_level)

    async def get_required_level_value(
        self,
        guild_id: int,
        command_key: str,
    ) -> int:
        level_name = await self.get_required_level_name(guild_id, command_key)
        return LEVEL_VALUES[level_name]

    async def set_command_level(
        self,
        guild_id: int,
        command_key: str,
        level: str,
    ) -> None:
        command_key = normalise_command_key(command_key)
        level = normalise_level(level)

        async with aiosqlite.connect(self.db_path) as database:
            await database.execute(
                """
                INSERT INTO permission_command_levels (
                    guild_id,
                    command_key,
                    level
                )
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, command_key)
                DO UPDATE SET level = excluded.level
                """,
                (guild_id, command_key, level),
            )

            await database.commit()

    async def reset_command_level(
        self,
        guild_id: int,
        command_key: str,
    ) -> None:
        command_key = normalise_command_key(command_key)

        async with aiosqlite.connect(self.db_path) as database:
            await database.execute(
                """
                DELETE FROM permission_command_levels
                WHERE guild_id = ?
                AND command_key = ?
                """,
                (guild_id, command_key),
            )

            await database.commit()

    async def get_all_command_levels(
        self,
        guild_id: int,
    ) -> dict[str, str]:
        custom_levels: dict[str, str] = {}

        async with aiosqlite.connect(self.db_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT command_key, level
                FROM permission_command_levels
                WHERE guild_id = ?
                """,
                (guild_id,),
            )

            rows = await cursor.fetchall()

        for row in rows:
            custom_levels[str(row["command_key"])] = normalise_level(str(row["level"]))

        keys = set(DEFAULT_COMMAND_LEVELS.keys()) | set(custom_levels.keys())

        command_levels: dict[str, str] = {}

        for key in sorted(keys):
            command_levels[key] = (
                custom_levels.get(key)
                or DEFAULT_COMMAND_LEVELS.get(key)
                or LEVEL_PUBLIC
            )

        return command_levels

    async def get_known_command_keys(self, guild_id: int) -> list[str]:
        command_levels = await self.get_all_command_levels(guild_id)
        return list(command_levels.keys())

    async def set_role(
        self,
        guild_id: int,
        level: str,
        role_id: int,
    ) -> None:
        level = normalise_level(level)

        if level == LEVEL_PUBLIC:
            raise ValueError("Public does not use a role.")

        async with aiosqlite.connect(self.db_path) as database:
            await database.execute(
                """
                INSERT INTO permission_roles (
                    guild_id,
                    level,
                    role_id
                )
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, level)
                DO UPDATE SET role_id = excluded.role_id
                """,
                (guild_id, level, role_id),
            )

            await database.commit()

    async def clear_role(
        self,
        guild_id: int,
        level: str,
    ) -> None:
        level = normalise_level(level)

        if level == LEVEL_PUBLIC:
            raise ValueError("Public does not use a role.")

        async with aiosqlite.connect(self.db_path) as database:
            await database.execute(
                """
                DELETE FROM permission_roles
                WHERE guild_id = ?
                AND level = ?
                """,
                (guild_id, level),
            )

            await database.commit()

    async def get_role_id(
        self,
        guild_id: int,
        level: str,
    ) -> int | None:
        level = normalise_level(level)

        async with aiosqlite.connect(self.db_path) as database:
            database.row_factory = aiosqlite.Row

            cursor = await database.execute(
                """
                SELECT role_id
                FROM permission_roles
                WHERE guild_id = ?
                AND level = ?
                LIMIT 1
                """,
                (guild_id, level),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return int(row["role_id"])

    async def get_role_ids(
        self,
        guild_id: int,
    ) -> dict[str, int | None]:
        return {
            LEVEL_STAFF: await self.get_role_id(guild_id, LEVEL_STAFF),
            LEVEL_ADMIN: await self.get_role_id(guild_id, LEVEL_ADMIN),
            LEVEL_OWNER: await self.get_role_id(guild_id, LEVEL_OWNER),
        }