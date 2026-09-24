"""Shared bot handles and session helpers for Web UI routes.

Route modules reach the Discord client, stores, and upload manager through
the WebUIContext stored on the Flask app. Coroutine work is submitted to
the bot loop because Flask runs on waitress threads, not that loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
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
    """Bot, access manager, and upload manager for one Web UI process."""

    def __init__(
        self,
        bot: discord.Client,
    ) -> None:
        self.bot = bot

        self.access = WebUIAccessManager(
            bot
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
        """Base template variables, including the caller's role and name."""
        return {
            "title": title,
            "active_page": active_page,
            "is_owner": self.is_owner(),
            "webui_role": self.current_role(),
            "display_name": self.display_name(),
            **extra,
        }
        
    def audit(
        self,
        *,
        action: str,
        detail: str = "",
        guild_id: int | None = None,
    ) -> None:
        """Write one WebUI audit row, or return when the store is absent.

        The actor id prefers the Discord user id, then the password
        username. A blank id is stored as None.
        """
        store = getattr(
            self.bot,
            "audit_store",
            None,
        )

        if store is None:
            return

        actor_id = str(
            session.get(
                "discord_user_id"
            )
            or session.get(
                "username"
            )
            or ""
        ) or None

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
        coro: Coroutine[Any, Any, Any],
    ) -> Any:
        """Run a bot-loop coroutine from a waitress thread and wait 15 seconds.

        TimeoutError and the coroutine's own errors propagate to the route.
        """
        future = asyncio.run_coroutine_threadsafe(
            coro,
            self.bot.loop,
        )

        return future.result(
            timeout=15
        )

    def is_logged_in(self) -> bool:
        """True only when the session flag is exactly True."""
        return (
            session.get("logged_in")
            is True
        )

    def current_role(self) -> str:
        """Return ``owner``, ``viewer``, or an empty string.

        Password login does not store a Discord role, so a logged-in
        password session is treated as owner. Any other value is ignored.
        """
        role = str(
            session.get("webui_role")
            or ""
        ).lower().strip()

        if role in {
            "owner",
            "viewer",
        }:
            return role

        if (
            session.get("logged_in")
            is True
            and session.get("auth_method")
            == "password"
        ):
            return "owner"

        return ""

    def is_owner(self) -> bool:
        return (
            self.current_role()
            == "owner"
        )

    def display_name(self) -> str:
        """Prefer the saved display name, then Discord username, then password."""
        return str(
            session.get("display_name")
            or session.get(
                "discord_username"
            )
            or session.get("username")
            or "WebUI user"
        )

    def available_guilds(
        self,
    ) -> list[dict[str, str]]:
        """Guilds the bot is currently in, sorted by name without case."""
        return [
            {
                "id": str(guild.id),
                "name": guild.name,
            }
            for guild in sorted(
                self.bot.guilds,
                key=lambda item: (
                    item.name.lower()
                ),
            )
        ]

    def selected_guild(
        self,
        guild_id_text: str | None,
    ) -> discord.Guild | None:
        """Resolve a guild id, otherwise the first guild the bot can see.

        A non-numeric id is treated as missing rather than as an error.
        """
        if guild_id_text:
            try:
                guild_id = int(
                    guild_id_text
                )

            except ValueError:
                guild_id = 0

            guild = self.bot.get_guild(
                guild_id
            )

            if guild is not None:
                return guild

        if self.bot.guilds:
            return self.bot.guilds[0]

        return None

    @staticmethod
    def guild_roles(
        guild: discord.Guild,
    ) -> list[dict[str, str]]:
        """Roles except @everyone, highest position first."""
        roles = [
            role
            for role in guild.roles
            if not role.is_default()
        ]

        roles.sort(
            key=lambda item: (
                item.position
            ),
            reverse=True,
        )

        return [
            {
                "id": str(role.id),
                "name": role.name,
            }
            for role in roles
        ]

    @staticmethod
    def guild_text_channels(
        guild: discord.Guild,
    ) -> list[dict[str, str]]:
        """Text channels ordered by category name, then position, then name."""
        channels = list(
            guild.text_channels
        )

        channels.sort(
            key=lambda item: (
                (
                    item.category.name
                    if item.category
                    else ""
                ),
                item.position,
                item.name.lower(),
            )
        )

        return [
            {
                "id": str(channel.id),
                "name": channel.name,
            }
            for channel in channels
        ]

    def template_store(self):
        """Return the DM template store or raise if the bot has not attached it."""
        store = getattr(
            self.bot,
            "dm_template_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "DM template store is not available."
            )

        return store

    def permission_store(self):
        """Return the permission store or raise if it is not attached."""
        store = getattr(
            self.bot,
            "permission_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Permission store is not available."
            )

        return store

    def guild_settings_store(self):
        """Return guild settings or raise if they are not attached."""
        store = getattr(
            self.bot,
            "guild_settings",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Guild settings store is not available."
            )

        return store

    def form_store(self):
        """Return the form store or raise if it is not attached."""
        store = getattr(
            self.bot,
            "form_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Form store is not available."
            )

        return store

    def invite_tracker_store(self):
        """Return the invite tracker or raise if it is not attached."""
        store = getattr(
            self.bot,
            "invite_tracker",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Invite tracker is not available."
            )

        return store

    def custom_command_store(self):
        """Return the custom-command store or raise if it is not attached."""
        store = getattr(
            self.bot,
            "custom_command_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Custom command store is not available."
            )

        return store