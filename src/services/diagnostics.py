from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import discord

from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
    VERIFICATION_FORM_PATH,
)


STATUS_GOOD = "good"
STATUS_WARN = "warn"
STATUS_BAD = "bad"


@dataclass(
    frozen=True
)
class DiagnosticItem:
    label: str
    value: str
    status: str
    detail: str | None = None


@dataclass(
    frozen=True
)
class DiagnosticReport:
    items: list[DiagnosticItem]

    @property
    def good_count(self) -> int:
        return sum(
            item.status == STATUS_GOOD
            for item in self.items
        )

    @property
    def warning_count(self) -> int:
        return sum(
            item.status == STATUS_WARN
            for item in self.items
        )

    @property
    def error_count(self) -> int:
        return sum(
            item.status == STATUS_BAD
            for item in self.items
        )

    @property
    def healthy(self) -> bool:
        return self.error_count == 0


def channel_permissions_text(
    permissions: discord.Permissions,
) -> list[str]:
    missing: list[str] = []

    if not permissions.view_channel:
        missing.append(
            "View Channel"
        )

    if not permissions.send_messages:
        missing.append(
            "Send Messages"
        )

    if not permissions.embed_links:
        missing.append(
            "Embed Links"
        )

    if not permissions.attach_files:
        missing.append(
            "Attach Files"
        )

    if not permissions.read_message_history:
        missing.append(
            "Read Message History"
        )

    return missing


def check_channel(
    *,
    guild: discord.Guild,
    channel_id: int | None,
    label: str,
) -> DiagnosticItem:
    if channel_id is None:
        return DiagnosticItem(
            label=label,
            value="Not configured",
            status=STATUS_WARN,
            detail=(
                "No channel has been "
                "configured."
            ),
        )

    channel = guild.get_channel(
        channel_id
    )

    if not isinstance(
        channel,
        discord.TextChannel,
    ):
        return DiagnosticItem(
            label=label,
            value=(
                f"Missing channel "
                f"({channel_id})"
            ),
            status=STATUS_BAD,
            detail=(
                "The configured channel "
                "no longer exists."
            ),
        )

    member = guild.me

    if member is None:
        return DiagnosticItem(
            label=label,
            value=f"#{channel.name}",
            status=STATUS_WARN,
            detail=(
                "Could not determine the "
                "bot member permissions."
            ),
        )

    permissions = (
        channel.permissions_for(
            member
        )
    )

    missing_permissions = (
        channel_permissions_text(
            permissions
        )
    )

    if missing_permissions:
        return DiagnosticItem(
            label=label,
            value=f"#{channel.name}",
            status=STATUS_BAD,
            detail=(
                "Missing permissions: "
                + ", ".join(
                    missing_permissions
                )
            ),
        )

    return DiagnosticItem(
        label=label,
        value=f"#{channel.name}",
        status=STATUS_GOOD,
        detail=(
            "Channel exists and the bot "
            "can use it."
        ),
    )


def check_role(
    *,
    guild: discord.Guild,
    role_id: int | None,
    label: str,
    required: bool = False,
) -> DiagnosticItem:
    if role_id is None:
        return DiagnosticItem(
            label=label,
            value="Not configured",
            status=(
                STATUS_WARN
                if required
                else STATUS_GOOD
            ),
            detail=(
                "No role configured."
            ),
        )

    role = guild.get_role(
        role_id
    )

    if role is None:
        return DiagnosticItem(
            label=label,
            value=(
                f"Missing role "
                f"({role_id})"
            ),
            status=STATUS_BAD,
            detail=(
                "The configured role "
                "no longer exists."
            ),
        )

    member = guild.me

    if member is None:
        return DiagnosticItem(
            label=label,
            value=role.name,
            status=STATUS_WARN,
            detail=(
                "Could not determine the "
                "bot's role hierarchy."
            ),
        )

    if role >= member.top_role:
        return DiagnosticItem(
            label=label,
            value=role.name,
            status=STATUS_BAD,
            detail=(
                "The bot's highest role "
                "must be above this role."
            ),
        )

    return DiagnosticItem(
        label=label,
        value=role.name,
        status=STATUS_GOOD,
        detail=(
            "Role exists and is below "
            "the bot's highest role."
        ),
    )


async def build_diagnostic_report(
    bot,
    guild: discord.Guild,
) -> DiagnosticReport:
    items: list[
        DiagnosticItem
    ] = []

    settings = getattr(
        bot,
        "guild_settings",
        None,
    )

    if settings is None:
        return DiagnosticReport(
            items=[
                DiagnosticItem(
                    label="Guild settings",
                    value="Unavailable",
                    status=STATUS_BAD,
                )
            ]
        )

    items.append(
        DiagnosticItem(
            label="Discord connection",
            value=(
                f"Online as {bot.user}"
                if bot.user
                else "Not ready"
            ),
            status=(
                STATUS_GOOD
                if bot.user
                else STATUS_BAD
            ),
        )
    )

    review_channel_id = (
        settings
        .get_review_channel_id(
            guild.id
        )
    )

    log_channel_id = (
        settings
        .get_application_log_channel_id(
            guild.id
        )
    )

    items.append(
        check_channel(
            guild=guild,
            channel_id=(
                review_channel_id
            ),
            label=(
                "Application review "
                "channel"
            ),
        )
    )

    items.append(
        check_channel(
            guild=guild,
            channel_id=(
                log_channel_id
            ),
            label=(
                "Application log channel"
            ),
        )
    )

    add_role_id = (
        settings
        .get_approved_add_role_id(
            guild.id
        )
    )

    remove_role_id = (
        settings
        .get_approved_remove_role_id(
            guild.id
        )
    )

    items.append(
        check_role(
            guild=guild,
            role_id=add_role_id,
            label=(
                "Approval add role"
            ),
        )
    )

    items.append(
        check_role(
            guild=guild,
            role_id=remove_role_id,
            label=(
                "Approval remove role"
            ),
        )
    )

    form_store = getattr(
        bot,
        "form_store",
        None,
    )

    verification_form_key = (
        settings
        .get_verification_form_key(
            guild.id
        )
        or FORM_KEY_VERIFICATION
    )

    if form_store is None:
        items.append(
            DiagnosticItem(
                label="Verification form",
                value="Form store unavailable",
                status=STATUS_BAD,
            )
        )

    else:
        try:
            form = (
                await form_store
                .get_form_config(
                    guild_id=guild.id,
                    form_key=(
                        verification_form_key
                    ),
                    fallback_json_path=(
                        VERIFICATION_FORM_PATH
                    ),
                )
            )

            items.append(
                DiagnosticItem(
                    label="Verification form",
                    value=(
                        f"{form.form_key} - "
                        f"{form.title}"
                    ),
                    status=STATUS_GOOD,
                    detail=(
                        "Verification form "
                        "loaded successfully."
                    ),
                )
            )

        except Exception as error:
            items.append(
                DiagnosticItem(
                    label="Verification form",
                    value=(
                        verification_form_key
                    ),
                    status=STATUS_BAD,
                    detail=str(
                        error
                    ),
                )
            )

    database_path = getattr(
        getattr(
            bot,
            "application_store",
            None,
        ),
        "database_path",
        None,
    )

    if database_path is None:
        items.append(
            DiagnosticItem(
                label="Database",
                value="Unavailable",
                status=STATUS_BAD,
            )
        )

    else:
        path = Path(
            database_path
        )

        if not path.exists():
            items.append(
                DiagnosticItem(
                    label="Database",
                    value=str(path),
                    status=STATUS_BAD,
                    detail=(
                        "Database file does "
                        "not exist."
                    ),
                )
            )

        else:
            try:
                with path.open(
                    "ab"
                ):
                    pass

                size_bytes = (
                    path.stat().st_size
                )

                items.append(
                    DiagnosticItem(
                        label="Database",
                        value=(
                            f"{size_bytes:,} "
                            "bytes"
                        ),
                        status=STATUS_GOOD,
                        detail=(
                            "Database exists "
                            "and is writable."
                        ),
                    )
                )

            except OSError as error:
                items.append(
                    DiagnosticItem(
                        label="Database",
                        value=str(path),
                        status=STATUS_BAD,
                        detail=str(error),
                    )
                )

    invite_ready = bool(
        getattr(
            bot,
            "invite_tracker_ready",
            False,
        )
    )

    items.append(
        DiagnosticItem(
            label="Invite tracking",
            value=(
                "Ready"
                if invite_ready
                else "Not synchronised"
            ),
            status=(
                STATUS_GOOD
                if invite_ready
                else STATUS_WARN
            ),
        )
    )

    member = guild.me

    if member is None:
        items.append(
            DiagnosticItem(
                label="Moderation permissions",
                value="Unknown",
                status=STATUS_WARN,
            )
        )

    else:
        guild_permissions = (
            member.guild_permissions
        )

        missing: list[str] = []

        if not guild_permissions.manage_roles:
            missing.append(
                "Manage Roles"
            )

        if not guild_permissions.kick_members:
            missing.append(
                "Kick Members"
            )

        if not guild_permissions.ban_members:
            missing.append(
                "Ban Members"
            )

        if missing:
            items.append(
                DiagnosticItem(
                    label=(
                        "Moderation "
                        "permissions"
                    ),
                    value="Incomplete",
                    status=STATUS_BAD,
                    detail=(
                        "Missing: "
                        + ", ".join(
                            missing
                        )
                    ),
                )
            )

        else:
            items.append(
                DiagnosticItem(
                    label=(
                        "Moderation "
                        "permissions"
                    ),
                    value="Ready",
                    status=STATUS_GOOD,
                )
            )

    return DiagnosticReport(
        items=items
    )