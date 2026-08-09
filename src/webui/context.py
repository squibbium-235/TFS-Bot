from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import discord
from flask import session


class WebUIContext:
    def __init__(
        self,
        bot: discord.Client,
    ) -> None:
        self.bot = bot
        
    def template_context(
        self,
        *,
        title: str,
        active_page: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "title": title,
            "active_page": active_page,
            "is_owner": self.is_owner(),
            "webui_role": self.current_role(),
            "display_name": self.display_name(),
            **extra,
        }

    def run_coro(
        self,
        coro: Coroutine[Any, Any, Any],
    ) -> Any:
        future = asyncio.run_coroutine_threadsafe(
            coro,
            self.bot.loop,
        )

        return future.result(
            timeout=15
        )

    def is_logged_in(self) -> bool:
        return (
            session.get("logged_in")
            is True
        )

    def current_role(self) -> str:
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

        return "viewer"

    def is_owner(self) -> bool:
        return (
            self.current_role()
            == "owner"
        )

    def display_name(self) -> str:
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