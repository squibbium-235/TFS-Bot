"""
Slash-command permission gate.

Levels rank public < staff < admin < owner.
PermissionCommandTree checks every
interaction. A DM is allowed. A missing
permission store fails closed.
"""

from __future__ import annotations

import discord
from discord import app_commands

from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
    LEVEL_VALUES,
    PermissionStore,
    get_bot_dev_user_ids,
    normalise_command_key,
)


class PermissionDenied(app_commands.CheckFailure):
    """
    Raised when a member is below the level
    configured for a slash command.

    It subclasses CheckFailure so the bot's
    app-command error handler can reply with
    the message built here.
    """

    def __init__(
        self,
        command_key: str,
        required_level: str,
        user_level: str,
    ) -> None:
        self.command_key = command_key
        self.required_level = required_level
        self.user_level = user_level

        super().__init__(
            f"You need `{required_level}` permission to use `{command_key}`. "
            f"Your level is `{user_level}`."
        )


def command_key_from_interaction(interaction: discord.Interaction) -> str:
    """
    Normalised qualified name of the slash
    command, or an empty string when the
    interaction has no command.

    An empty key skips the permission check.
    """
    if interaction.command is None:
        return ""

    return normalise_command_key(interaction.command.qualified_name)


def get_permission_store(client: discord.Client) -> PermissionStore | None:
    return getattr(client, "permission_store", None)


async def get_member_level_name(
    member: discord.Member,
    permission_store: PermissionStore,
) -> str:
    """
    Highest permission level for a member.

    Bot-dev user ids and the Discord guild
    owner are owner. Configured owner, admin,
    and staff roles are then checked in that
    order. Administrator or manage_guild
    counts as admin only when none of those
    roles match, so a staff role stays staff
    even if the member also has Administrator.
    Anyone else is public.
    """
    bot_dev_user_ids = get_bot_dev_user_ids()

    if member.id in bot_dev_user_ids:
        return LEVEL_OWNER

    if member.guild.owner_id == member.id:
        return LEVEL_OWNER

    role_ids = await permission_store.get_role_ids(member.guild.id)

    owner_role_id = role_ids.get(LEVEL_OWNER)
    admin_role_id = role_ids.get(LEVEL_ADMIN)
    staff_role_id = role_ids.get(LEVEL_STAFF)

    member_role_ids = {role.id for role in member.roles}

    if owner_role_id is not None and owner_role_id in member_role_ids:
        return LEVEL_OWNER

    if admin_role_id is not None and admin_role_id in member_role_ids:
        return LEVEL_ADMIN

    if staff_role_id is not None and staff_role_id in member_role_ids:
        return LEVEL_STAFF

    if member.guild_permissions.administrator:
        return LEVEL_ADMIN

    if member.guild_permissions.manage_guild:
        return LEVEL_ADMIN

    return LEVEL_PUBLIC


def member_meets_level(
    member_level: str,
    required_level: str,
) -> bool:
    """
    True when member_level is at least
    required_level on the public < staff <
    admin < owner scale.
    """
    return LEVEL_VALUES[member_level] >= LEVEL_VALUES[required_level]


class PermissionCommandTree(app_commands.CommandTree):
    """
    Command tree that enforces configured
    permission levels before a slash command
    runs.
    """

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """
        Allow the interaction or raise
        PermissionDenied.

        No command key, a public requirement,
        or a DM (guild is None) returns True.
        A missing permission store returns
        False, which blocks the command
        without a permission message.
        """
        command_key = command_key_from_interaction(interaction)

        if not command_key:
            return True

        # DMs have no guild roles to compare.
        if interaction.guild is None:
            return True

        permission_store = get_permission_store(interaction.client)

        # Fail closed: do not run the command if the store was not attached.
        if permission_store is None:
            return False

        required_level = await permission_store.get_required_level_name(
            guild_id=interaction.guild.id,
            command_key=command_key,
        )

        if required_level == LEVEL_PUBLIC:
            return True

        if not isinstance(interaction.user, discord.Member):
            raise PermissionDenied(
                command_key=command_key,
                required_level=required_level,
                user_level=LEVEL_PUBLIC,
            )

        user_level = await get_member_level_name(
            member=interaction.user,
            permission_store=permission_store,
        )

        if member_meets_level(
            member_level=user_level,
            required_level=required_level,
        ):
            return True

        raise PermissionDenied(
            command_key=command_key,
            required_level=required_level,
            user_level=user_level,
        )