"""
Shared bot handles and session helpers for
Sanctuary Servo Web UI routes.

Route modules reach the Discord client,
stores, and upload manager through the
WebUIContext stored on the Flask app.

Flask runs on waitress threads, so coroutine
work is submitted to the Discord bot loop.

Discord OAuth sessions may access only guilds
that were confirmed as belonging to both the
logged-in Discord user and Sanctuary Servo.

Password sessions are emergency owner
sessions and may access every guild the bot
is currently in.
"""

from __future__ import annotations

import asyncio
from collections.abc import (
    Coroutine,
)
from typing import Any

import discord
from flask import session

from src.webui.access import (
    WebUIAccessManager,
)

from src.webui.uploads import (
    WebUIUploadManager,
)


class WebUIContext:
    """
    Bot, access manager, and upload manager
    for one Web UI process.
    """

    def __init__(
        self,
        bot: discord.Client,
    ) -> None:
        self.bot = bot

        self.access = (
            WebUIAccessManager(
                bot
            )
        )

        self.uploads = (
            WebUIUploadManager()
        )

    def template_context(
        self,
        *,
        title: str,
        active_page: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """
        Base template variables including
        the caller's role and display name.
        """
        return {
            "title": title,
            "active_page": active_page,
            "is_owner": (
                self.is_owner()
            ),
            "webui_role": (
                self.current_role()
            ),
            "display_name": (
                self.display_name()
            ),
            **extra,
        }

    def audit(
        self,
        *,
        action: str,
        detail: str = "",
        guild_id: int | None = None,
    ) -> None:
        """
        Write one Web UI audit row.

        The actor ID prefers the Discord user
        ID and falls back to the password
        username.
        """
        store = getattr(
            self.bot,
            "audit_store",
            None,
        )

        if store is None:
            return

        actor_id = (
            str(
                session.get(
                    "discord_user_id"
                )
                or session.get(
                    "username"
                )
                or ""
            )
            or None
        )

        self.run_coro(
            store.log(
                source="WebUI",
                actor_id=actor_id,
                actor_name=(
                    self.display_name()
                ),
                guild_id=guild_id,
                action=action,
                detail=detail,
            )
        )

    def run_coro(
        self,
        coro: Coroutine[
            Any,
            Any,
            Any,
        ],
    ) -> Any:
        """
        Run a bot-loop coroutine from a
        waitress thread and wait up to
        15 seconds.
        """
        future = (
            asyncio
            .run_coroutine_threadsafe(
                coro,
                self.bot.loop,
            )
        )

        return future.result(
            timeout=15
        )

    def is_logged_in(
        self,
    ) -> bool:
        """
        True only when the session login flag
        is exactly True.
        """
        return (
            session.get(
                "logged_in"
            )
            is True
        )

    def current_role(
        self,
    ) -> str:
        """
        Return owner, viewer, or an empty
        string.

        Password login does not store a
        Discord role, so a logged-in password
        session is treated as owner.
        """
        role = str(
            session.get(
                "webui_role"
            )
            or ""
        ).lower().strip()

        if role in {
            "owner",
            "viewer",
        }:
            return role

        if (
            session.get(
                "logged_in"
            )
            is True
            and session.get(
                "auth_method"
            )
            == "password"
        ):
            return "owner"

        return ""

    def is_owner(
        self,
    ) -> bool:
        """
        Return whether the current Web UI
        session has owner access.
        """
        return (
            self.current_role()
            == "owner"
        )

    def display_name(
        self,
    ) -> str:
        """
        Prefer the saved display name, then
        Discord username, then password
        username.
        """
        return str(
            session.get(
                "display_name"
            )
            or session.get(
                "discord_username"
            )
            or session.get(
                "username"
            )
            or "WebUI user"
        )

    def discord_session_guild_ids(
        self,
    ) -> set[int]:
        """
        Return guild IDs authorised for the
        current Discord OAuth session.

        Missing, invalid, or old sessions fail
        closed and therefore return no guilds.

        This means Discord users logged in
        before the guild-filtering feature was
        deployed must log out and back in.
        """
        if (
            not self.is_logged_in()
            or session.get(
                "auth_method"
            )
            != "discord"
        ):
            return set()

        raw_ids = session.get(
            "discord_guild_ids"
        )

        if not isinstance(
            raw_ids,
            list,
        ):
            return set()

        guild_ids: set[
            int
        ] = set()

        for raw_id in raw_ids:
            try:
                guild_id = int(
                    raw_id
                )

            except (
                TypeError,
                ValueError,
            ):
                continue

            if guild_id > 0:
                guild_ids.add(
                    guild_id
                )

        return guild_ids

    def accessible_guild_objects(
        self,
    ) -> list[discord.Guild]:
        """
        Return Discord guild objects the
        current Web UI session may access.

        Emergency password owners can access
        every guild the bot is in.

        Discord OAuth users may access only
        guild IDs saved after intersecting
        their Discord guild membership with
        the bot's guild list at login.
        """
        if not self.is_logged_in():
            return []

        auth_method = (
            session.get(
                "auth_method"
            )
        )

        if auth_method == "password":
            guilds = list(
                self.bot.guilds
            )

        elif auth_method == "discord":
            allowed_ids = (
                self
                .discord_session_guild_ids()
            )

            guilds = [
                guild
                for guild
                in self.bot.guilds
                if guild.id
                in allowed_ids
            ]

        else:
            return []

        guilds.sort(
            key=lambda guild: (
                guild.name.lower()
            )
        )

        return guilds

    def guild_is_accessible(
        self,
        guild_id: int,
    ) -> bool:
        """
        Return whether the current Web UI
        session may access this guild.
        """
        return any(
            guild.id
            == guild_id
            for guild
            in (
                self
                .accessible_guild_objects()
            )
        )

    def available_guilds(
        self,
    ) -> list[
        dict[
            str,
            str,
        ]
    ]:
        """
        Return only guilds available to the
        current logged-in user.

        Server names belonging only to the
        bot are deliberately not exposed.
        """
        return [
            {
                "id": str(
                    guild.id
                ),
                "name": (
                    guild.name
                ),
            }
            for guild
            in (
                self
                .accessible_guild_objects()
            )
        ]

    def selected_guild(
        self,
        guild_id_text: str | None,
    ) -> discord.Guild | None:
        """
        Resolve a requested guild only if the
        current Web UI session is authorised
        to access it.

        If an explicit guild ID is invalid or
        inaccessible, return None.

        Do not silently substitute another
        guild. That prevents a forged or stale
        request from accidentally applying an
        action to the wrong server.

        If no guild ID is supplied, return the
        first accessible guild.
        """
        accessible_guilds = (
            self
            .accessible_guild_objects()
        )

        if guild_id_text:
            try:
                guild_id = int(
                    guild_id_text
                )

            except ValueError:
                return None

            for guild in (
                accessible_guilds
            ):
                if guild.id == guild_id:
                    return guild

            return None

        if accessible_guilds:
            return (
                accessible_guilds[0]
            )

        return None

    @staticmethod
    def guild_roles(
        guild: discord.Guild,
    ) -> list[
        dict[
            str,
            str,
        ]
    ]:
        """
        Roles except @everyone, ordered
        highest position first.

        Callers must supply a guild resolved
        through selected_guild().
        """
        roles = [
            role
            for role
            in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda role: (
                role.position
            ),
            reverse=True,
        )

        return [
            {
                "id": str(
                    role.id
                ),
                "name": (
                    role.name
                ),
            }
            for role
            in roles
        ]

    @staticmethod
    def guild_text_channels(
        guild: discord.Guild,
    ) -> list[
        dict[
            str,
            str,
        ]
    ]:
        """
        Text channels ordered by category,
        then position, then channel name.

        Callers must supply a guild resolved
        through selected_guild().
        """
        channels = list(
            guild.text_channels
        )

        channels.sort(
            key=lambda channel: (
                (
                    channel.category.name
                    if channel.category
                    else ""
                ),
                channel.position,
                channel.name.lower(),
            )
        )

        return [
            {
                "id": str(
                    channel.id
                ),
                "name": (
                    channel.name
                ),
            }
            for channel
            in channels
        ]

    def template_store(
        self,
    ):
        """
        Return the DM template store or raise
        if the bot has not attached it.
        """
        store = getattr(
            self.bot,
            "dm_template_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "DM template store "
                "is not available."
            )

        return store

    def permission_store(
        self,
    ):
        """
        Return the permission store or raise
        if it is not attached.
        """
        store = getattr(
            self.bot,
            "permission_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Permission store "
                "is not available."
            )

        return store

    def guild_settings_store(
        self,
    ):
        """
        Return guild settings or raise if the
        store is not attached.
        """
        store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Guild settings store "
                "is not available."
            )

        return store

    def form_store(
        self,
    ):
        """
        Return the form store or raise if it
        is not attached.
        """
        store = getattr(
            self.bot,
            "form_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Form store "
                "is not available."
            )

        return store

    def invite_tracker_store(
        self,
    ):
        """
        Return the invite tracker or raise if
        it is not attached.
        """
        store = getattr(
            self.bot,
            "invite_tracker",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Invite tracker "
                "is not available."
            )

        return store

    def custom_command_store(
        self,
    ):
        """
        Return the custom-command store or
        raise if it is not attached.
        """
        store = getattr(
            self.bot,
            "custom_command_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Custom command store "
                "is not available."
            )

        return store