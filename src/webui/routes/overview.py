from __future__ import annotations

import sqlite3

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
from typing import Any

import discord

from src.services.database import (
    DatabaseError,
    DatabaseRow,
    open_sync_database,
)

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.services.forms.constants import (
    FORM_KEY_VERIFICATION,
)

from src.webui.helpers import (
    require_login,
    webui_context,
)

from src.services.diagnostics import (
    build_diagnostic_report,
)


blueprint = Blueprint(
    "overview",
    __name__,
)


def get_database_path() -> Path | None:
    context = webui_context()

    application_store = getattr(
        context.bot,
        "application_store",
        None,
    )

    if application_store is None:
        return None

    raw_path = getattr(
        application_store,
        "database_path",
        None,
    )

    if raw_path is None:
        return None

    return Path(
        raw_path
    )


def format_file_size(
    size_bytes: int,
) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"

    size = float(
        size_bytes
    )

    for suffix in [
        "KB",
        "MB",
        "GB",
        "TB",
    ]:
        size /= 1024

        if size < 1024:
            return (
                f"{size:.1f} {suffix}"
            )

    return f"{size:.1f} PB"


def format_datetime_text(
    value: str | None,
) -> str:
    if not value:
        return "Unknown"

    try:
        parsed = datetime.fromisoformat(
            value
        )

    except ValueError:
        return value

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    local_time = parsed.astimezone()

    return local_time.strftime(
        "%d %b %Y %H:%M"
    )


def make_message_url(
    guild_id: int,
    channel_id: int | None,
    message_id: int | None,
) -> str | None:
    if (
        channel_id is None
        or message_id is None
    ):
        return None

    return (
        "https://discord.com/channels/"
        f"{guild_id}/"
        f"{channel_id}/"
        f"{message_id}"
    )


def make_thread_url(
    guild_id: int,
    thread_id: int | None,
) -> str | None:
    if thread_id is None:
        return None

    return (
        "https://discord.com/channels/"
        f"{guild_id}/"
        f"{thread_id}"
    )


def get_user_display(
    user_id: int,
) -> str:
    context = webui_context()

    user = context.bot.get_user(
        user_id
    )

    if user is not None:
        return (
            f"{user} ({user_id})"
        )

    return str(
        user_id
    )

def get_status_class(
    status: str,
) -> str:
    cleaned = (
        status
        .lower()
        .strip()
    )

    if cleaned in {
        "approved",
        "ready",
        "enabled",
        "set",
        "ok",
    }:
        return "good"

    if cleaned in {
        "pending",
        "questioning",
        "starting",
        "not set",
        "unknown",
    }:
        return "warn"

    if cleaned in {
        "rejected",
        "denied",
        "kicked",
        "banned",
        "left",
        "disabled",
        "missing",
    }:
        return "bad"

    return ""


def display_status(
    status: str,
    questioning_thread_id: int | None = None,
) -> str:
    cleaned = (
        status
        .lower()
        .strip()
    )

    if (
        cleaned == "pending"
        and questioning_thread_id
        is not None
    ):
        return "Questioning"

    return {
        "pending": "Pending",
        "approved": "Approved",
        "rejected": "Rejected",
        "denied": "Rejected",
        "kicked": "Kicked",
        "banned": "Banned",
        "left": "Left",
        "cancelled": "Cancelled",
    }.get(
        cleaned,
        status.title(),
    )


def empty_application_stats(
) -> dict[str, Any]:
    return {
        "status_counts": {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "kicked": 0,
            "banned": 0,
            "left": 0,
            "cancelled": 0,
        },
        "today": {
            "approved": 0,
            "rejected": 0,
            "kicked": 0,
            "banned": 0,
            "left": 0,
        },
        "today_total": 0,
        "total_count": 0,
        "pending_count": 0,
        "questioning_count": 0,
        "pending_applications": [],
        "recent_outcomes": [],
    }


def count_applications_for_overview(
    guild: discord.Guild,
) -> dict[str, Any]:
    database_path = (
        get_database_path()
    )

    if (
        database_path is None
        or not database_path.exists()
    ):
        return (
            empty_application_stats()
        )

    today_key = (
        datetime.now(
            timezone.utc
        )
        .date()
        .isoformat()
    )

    try:
        with open_sync_database(
            database_path
        ) as database:
            database.row_factory = (
                DatabaseRow
            )

            status_rows = (
                database.execute(
                    """
                    SELECT
                        status,
                        COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    GROUP BY status
                    """,
                    (guild.id,),
                )
                .fetchall()
            )

            today_rows = (
                database.execute(
                    """
                    SELECT
                        status,
                        COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    AND actioned_at IS NOT NULL
                    AND substr(
                        actioned_at,
                        1,
                        10
                    ) = ?
                    GROUP BY status
                    """,
                    (
                        guild.id,
                        today_key,
                    ),
                )
                .fetchall()
            )

            total_row = (
                database.execute(
                    """
                    SELECT
                        COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    """,
                    (guild.id,),
                )
                .fetchone()
            )

            questioning_row = (
                database.execute(
                    """
                    SELECT
                        COUNT(*) AS total
                    FROM applications
                    WHERE guild_id = ?
                    AND status = 'pending'
                    AND questioning_thread_id
                        IS NOT NULL
                    """,
                    (guild.id,),
                )
                .fetchone()
            )

            pending_rows = (
                database.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        status,
                        submitted_at,
                        review_channel_id,
                        review_message_id,
                        questioning_thread_id
                    FROM applications
                    WHERE guild_id = ?
                    AND status = 'pending'
                    ORDER BY submitted_at ASC
                    LIMIT 10
                    """,
                    (guild.id,),
                )
                .fetchall()
            )

            outcome_rows = (
                database.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        status,
                        actioned_at,
                        updated_at,
                        log_channel_id,
                        log_message_id,
                        questioning_thread_id
                    FROM applications
                    WHERE guild_id = ?
                    AND status != 'pending'
                    ORDER BY COALESCE(
                        actioned_at,
                        updated_at
                    ) DESC
                    LIMIT 10
                    """,
                    (guild.id,),
                )
                .fetchall()
            )

    except DatabaseError:
        return (
            empty_application_stats()
        )

    stats = (
        empty_application_stats()
    )

    status_counts = stats[
        "status_counts"
    ]

    for row in status_rows:
        key = str(
            row["status"]
        ).lower()

        if key == "denied":
            key = "rejected"

        status_counts[key] = int(
            row["total"]
        )

    today = stats["today"]

    for row in today_rows:
        key = str(
            row["status"]
        ).lower()

        if key == "denied":
            key = "rejected"

        if key in today:
            today[key] = int(
                row["total"]
            )

    pending_applications: list[
        dict[str, Any]
    ] = []

    for row in pending_rows:
        state = display_status(
            str(row["status"]),
            row[
                "questioning_thread_id"
            ],
        )

        pending_applications.append(
            {
                "id": row["id"],
                "user": get_user_display(
                    int(row["user_id"])
                ),
                "state": state,
                "state_class": (
                    get_status_class(
                        state
                    )
                ),
                "submitted_at": (
                    format_datetime_text(
                        row["submitted_at"]
                    )
                ),
                "review_url": (
                    make_message_url(
                        guild.id,
                        row[
                            "review_channel_id"
                        ],
                        row[
                            "review_message_id"
                        ],
                    )
                ),
                "thread_url": (
                    make_thread_url(
                        guild.id,
                        row[
                            "questioning_thread_id"
                        ],
                    )
                ),
            }
        )

    recent_outcomes: list[
        dict[str, Any]
    ] = []

    for row in outcome_rows:
        state = display_status(
            str(row["status"]),
            row[
                "questioning_thread_id"
            ],
        )

        recent_outcomes.append(
            {
                "id": row["id"],
                "user": get_user_display(
                    int(row["user_id"])
                ),
                "state": state,
                "state_class": (
                    get_status_class(
                        state
                    )
                ),
                "actioned_at": (
                    format_datetime_text(
                        row["actioned_at"]
                        or row["updated_at"]
                    )
                ),
                "log_url": (
                    make_message_url(
                        guild.id,
                        row[
                            "log_channel_id"
                        ],
                        row[
                            "log_message_id"
                        ],
                    )
                ),
                "thread_url": (
                    make_thread_url(
                        guild.id,
                        row[
                            "questioning_thread_id"
                        ],
                    )
                ),
            }
        )

    stats.update(
        {
            "today_total": sum(
                today.values()
            ),
            "total_count": int(
                total_row["total"]
                if total_row
                else 0
            ),
            "pending_count": (
                status_counts.get(
                    "pending",
                    0,
                )
            ),
            "questioning_count": int(
                questioning_row["total"]
                if questioning_row
                else 0
            ),
            "pending_applications": (
                pending_applications
            ),
            "recent_outcomes": (
                recent_outcomes
            ),
        }
    )

    return stats


def build_overview_context(
    guild: discord.Guild,
) -> dict[str, Any]:
    context = webui_context()

    settings_store = (
        context.guild_settings_store()
    )
    
    diagnostic_report = (
        context.run_coro(
            build_diagnostic_report(
                context.bot,
                guild,
            )
        )
    )

    app_stats = (
        count_applications_for_overview(
            guild
        )
    )

    review_channel_id = (
        settings_store
        .get_review_channel_id(
            guild.id
        )
    )

    log_channel_id = (
        settings_store
        .get_application_log_channel_id(
            guild.id
        )
    )

    add_role_id = (
        settings_store
        .get_approved_add_role_id(
            guild.id
        )
    )

    remove_role_id = (
        settings_store
        .get_approved_remove_role_id(
            guild.id
        )
    )

    automod_enabled = (
        settings_store
        .is_automod_enabled(
            guild.id
        )
    )

    automod_terms = (
        settings_store
        .list_automod_terms(
            guild.id
        )
    )

    verification_form_key = (
        settings_store
        .get_verification_form_key(
            guild.id
        )
        or FORM_KEY_VERIFICATION
    )

    database_path = (
        get_database_path()
    )

    database_size = (
        database_path.stat().st_size
        if (
            database_path
            and database_path.exists()
        )
        else 0
    )

    invite_ready = bool(
        getattr(
            context.bot,
            "invite_tracker_ready",
            False,
        )
    )

    health_items = [
        {
            "label": item.label,
            "value": (
                item.value
                if not item.detail
                else (
                    f"{item.value} - "
                    f"{item.detail}"
                )
            ),
            "class": item.status,
        }
        for item
        in diagnostic_report.items
    ]

    ignored_warning_labels = {
        "Automod",
        "Server members",
    }

    warning_items = [
        item
        for item in health_items
        if item["class"]
        in {
            "warn",
            "bad",
        }
    ]

    app_stats[
        "health_items"
    ] = health_items

    app_stats[
        "warning_items"
    ] = warning_items

    app_stats[
        "warning_count"
    ] = len(
        warning_items
    )

    return app_stats


@blueprint.route("/")
def index():
    context = webui_context()

    login_error = (
        require_login()
    )

    if login_error is not None:
        return login_error

    selected_guild = (
        context.selected_guild(
            request.args.get(
                "guild_id"
            )
        )
    )

    overview = None
    error = None

    try:
        if selected_guild is not None:
            overview = (
                build_overview_context(
                    selected_guild
                )
            )

    except Exception as caught_error:
        error = str(
            caught_error
        )

    return render_template(
        "overview/index.html",
        **context.template_context(
            title="TFSBot Overview",
            active_page="overview",
            guilds=(
                context.available_guilds()
            ),
            selected_guild_id=(
                str(
                    selected_guild.id
                )
                if selected_guild
                else None
            ),
            overview=overview,
            error=error,
            message=None,
        ),
    )