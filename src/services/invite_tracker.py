from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import discord

from src.services.database import (
    DatabaseRow,
    open_database,
)


@dataclass(frozen=True)
class TrackedInviteInfo:
    guild_id: int
    user_id: int
    invite_code: str | None
    invite_url: str | None
    inviter_id: int | None
    inviter_name: str | None
    uses: int | None
    joined_at: str


class InviteTrackerStore:
    def __init__(self, database_path: str = "data/tfsbot.sqlite3") -> None:
        database_path_object = Path(database_path)
        database_path_object.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = database_path_object

    async def initialise(self) -> None:
        async with open_database(self.database_path) as database:
            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS invite_snapshots (
                    guild_id INTEGER NOT NULL,
                    invite_code TEXT NOT NULL,
                    inviter_id INTEGER,
                    inviter_name TEXT,
                    uses INTEGER,
                    channel_id INTEGER,
                    invite_url TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, invite_code)
                )
                """
            )

            await database.execute(
                """
                CREATE TABLE IF NOT EXISTS member_invites (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    invite_code TEXT,
                    invite_url TEXT,
                    inviter_id INTEGER,
                    inviter_name TEXT,
                    uses INTEGER,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )

            await database.commit()

    async def sync_guild_invites(self, guild: discord.Guild) -> bool:
        invites = await self._fetch_invites(guild)

        if invites is None:
            return False

        now = self._now()

        async with open_database(self.database_path) as database:
            await database.execute(
                "DELETE FROM invite_snapshots WHERE guild_id = ?",
                (guild.id,),
            )

            for invite in invites:
                await database.execute(
                    """
                    INSERT INTO invite_snapshots (
                        guild_id,
                        invite_code,
                        inviter_id,
                        inviter_name,
                        uses,
                        channel_id,
                        invite_url,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id, invite_code)
                    DO UPDATE SET
                        inviter_id = excluded.inviter_id,
                        inviter_name = excluded.inviter_name,
                        uses = excluded.uses,
                        channel_id = excluded.channel_id,
                        invite_url = excluded.invite_url,
                        updated_at = excluded.updated_at
                    """,
                    self._invite_to_row_values(guild.id, invite, now),
                )

            await database.commit()

        return True

    async def sync_invite(self, invite: discord.Invite) -> None:
        if invite.guild is None:
            return

        now = self._now()

        async with open_database(self.database_path) as database:
            await database.execute(
                """
                INSERT INTO invite_snapshots (
                    guild_id,
                    invite_code,
                    inviter_id,
                    inviter_name,
                    uses,
                    channel_id,
                    invite_url,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, invite_code)
                DO UPDATE SET
                    inviter_id = excluded.inviter_id,
                    inviter_name = excluded.inviter_name,
                    uses = excluded.uses,
                    channel_id = excluded.channel_id,
                    invite_url = excluded.invite_url,
                    updated_at = excluded.updated_at
                """,
                self._invite_to_row_values(invite.guild.id, invite, now),
            )

            await database.commit()

    async def delete_invite_snapshot(
        self,
        guild_id: int,
        invite_code: str,
    ) -> None:
        async with open_database(self.database_path) as database:
            await database.execute(
                """
                DELETE FROM invite_snapshots
                WHERE guild_id = ?
                AND invite_code = ?
                """,
                (guild_id, invite_code),
            )

            await database.commit()

    async def track_member_join(self, member: discord.Member) -> TrackedInviteInfo | None:
        old_snapshots = await self._get_invite_snapshots(member.guild.id)
        current_invites = await self._fetch_invites(member.guild)

        matched_invite: discord.Invite | None = None

        if current_invites is not None:
            for invite in current_invites:
                old_uses = old_snapshots.get(invite.code, {}).get("uses")
                current_uses = invite.uses

                if current_uses is None:
                    continue

                if old_uses is None:
                    continue

                if current_uses > old_uses:
                    matched_invite = invite
                    break

            await self.sync_guild_invites(member.guild)

        info = await self._store_member_invite(
            member=member,
            invite=matched_invite,
        )

        return info

    async def get_member_invite_info(
        self,
        guild_id: int,
        user_id: int,
    ) -> TrackedInviteInfo | None:
        async with open_database(self.database_path) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT *
                FROM member_invites
                WHERE guild_id = ?
                AND user_id = ?
                LIMIT 1
                """,
                (guild_id, user_id),
            )

            row = await cursor.fetchone()

        if row is None:
            return None

        return self._row_to_info(row)

    async def _store_member_invite(
        self,
        member: discord.Member,
        invite: discord.Invite | None,
    ) -> TrackedInviteInfo:
        inviter = invite.inviter if invite is not None else None
        joined_at = self._now()
        invite_code = invite.code if invite is not None else None
        invite_url = invite.url if invite is not None else None
        inviter_id = inviter.id if inviter is not None else None
        inviter_name = str(inviter) if inviter is not None else None
        uses = invite.uses if invite is not None else None

        async with open_database(self.database_path) as database:
            await database.execute(
                """
                INSERT INTO member_invites (
                    guild_id,
                    user_id,
                    invite_code,
                    invite_url,
                    inviter_id,
                    inviter_name,
                    uses,
                    joined_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id)
                DO UPDATE SET
                    invite_code = excluded.invite_code,
                    invite_url = excluded.invite_url,
                    inviter_id = excluded.inviter_id,
                    inviter_name = excluded.inviter_name,
                    uses = excluded.uses,
                    joined_at = excluded.joined_at
                """,
                (
                    member.guild.id,
                    member.id,
                    invite_code,
                    invite_url,
                    inviter_id,
                    inviter_name,
                    uses,
                    joined_at,
                ),
            )

            await database.commit()

        return TrackedInviteInfo(
            guild_id=member.guild.id,
            user_id=member.id,
            invite_code=invite_code,
            invite_url=invite_url,
            inviter_id=inviter_id,
            inviter_name=inviter_name,
            uses=uses,
            joined_at=joined_at,
        )

    async def _get_invite_snapshots(
        self,
        guild_id: int,
    ) -> dict[str, dict[str, int | None]]:
        async with open_database(self.database_path) as database:
            database.row_factory = DatabaseRow

            cursor = await database.execute(
                """
                SELECT invite_code, uses
                FROM invite_snapshots
                WHERE guild_id = ?
                """,
                (guild_id,),
            )

            rows = await cursor.fetchall()

        return {
            str(row["invite_code"]): {"uses": row["uses"]}
            for row in rows
        }

    @staticmethod
    async def _fetch_invites(guild: discord.Guild) -> list[discord.Invite] | None:
        try:
            return await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

    @staticmethod
    def _invite_to_row_values(
        guild_id: int,
        invite: discord.Invite,
        updated_at: str,
    ) -> tuple[int, str, int | None, str | None, int | None, int | None, str, str]:
        inviter = invite.inviter
        channel = invite.channel

        return (
            guild_id,
            invite.code,
            inviter.id if inviter is not None else None,
            str(inviter) if inviter is not None else None,
            invite.uses,
            channel.id if channel is not None else None,
            invite.url,
            updated_at,
        )

    @staticmethod
    def _row_to_info(row: DatabaseRow) -> TrackedInviteInfo:
        return TrackedInviteInfo(
            guild_id=int(row["guild_id"]),
            user_id=int(row["user_id"]),
            invite_code=row["invite_code"],
            invite_url=row["invite_url"],
            inviter_id=row["inviter_id"],
            inviter_name=row["inviter_name"],
            uses=row["uses"],
            joined_at=row["joined_at"],
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
