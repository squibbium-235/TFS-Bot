from __future__ import annotations

from collections.abc import Callable
from typing import Any

import discord
from flask import Flask, redirect, render_template, request, session, url_for

from src.services.custom_commands.store import (
    ADD_REACTION,
    ADD_ROLE,
    DELETE_MESSAGE,
    REMOVE_ROLE,
    SEND_EMBED,
    SEND_MESSAGE,
)
from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
)


ACTION_LABELS = {
    SEND_MESSAGE: "Send Message",
    SEND_EMBED: "Send Embed",
    ADD_REACTION: "Add Reaction",
    ADD_ROLE: "Add Role",
    REMOVE_ROLE: "Remove Role",
    DELETE_MESSAGE: "Delete Message",
}


LEVELS = [
    {
        "value": LEVEL_PUBLIC,
        "label": "Public",
    },
    {
        "value": LEVEL_STAFF,
        "label": "Staff",
    },
    {
        "value": LEVEL_ADMIN,
        "label": "Admin",
    },
    {
        "value": LEVEL_OWNER,
        "label": "Owner",
    },
]


def parse_bool(
    value: str | None,
) -> bool:
    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_int(
    value: str | None,
    default: int = 0,
) -> int:
    try:
        return int(
            str(value or "").strip()
        )
    except ValueError:
        return default


def parse_float(
    value: str | None,
    default: float = 0,
) -> float:
    try:
        return float(
            str(value or "").strip()
        )
    except ValueError:
        return default


def parse_colour(
    value: str | None,
) -> int | None:
    value = (
        str(value or "")
        .strip()
        .lower()
        .removeprefix("#")
        .removeprefix("0x")
    )

    if not value:
        return None

    try:
        colour = int(
            value,
            16,
        )
    except ValueError as error:
        raise ValueError(
            "Embed colour must be a six-digit hex value."
        ) from error

    if not 0 <= colour <= 0xFFFFFF:
        raise ValueError(
            "Embed colour must be between 000000 and FFFFFF."
        )

    return colour


def get_creator_id(
    bot: discord.Client,
) -> int:
    discord_user_id = str(
        session.get(
            "discord_user_id"
        )
        or ""
    ).strip()

    if discord_user_id.isdigit():
        return int(
            discord_user_id
        )

    if bot.user is not None:
        return bot.user.id

    return 0


def build_action_data(
    action_type: str,
    action_number: int | None = None,
) -> dict[str, Any]:
    if action_type == SEND_MESSAGE:
        return {
            "content": request.form.get(
                "content",
                "",
            ),
            "reply": parse_bool(
                request.form.get(
                    "reply"
                )
            ),
        }

    if action_type == SEND_EMBED:
        fields: list[
            dict[str, Any]
        ] = []

        if action_number is not None:
            field_slots = request.form.getlist(
                "field_slot[]"
            )

            for slot in field_slots:
                name = request.form.get(
                    f"field_name_{slot}",
                    "",
                ).strip()

                value = request.form.get(
                    f"field_value_{slot}",
                    "",
                ).strip()

                inline = parse_bool(
                    request.form.get(
                        f"field_inline_{slot}"
                    )
                )

                if not name and not value:
                    continue

                if not name or not value:
                    raise ValueError(
                        "Embed fields need both a name and value."
                    )

                fields.append(
                    {
                        "name": name[:256],
                        "value": value[:1024],
                        "inline": inline,
                    }
                )

        if len(fields) > 25:
            raise ValueError(
                "Discord embeds can contain at most 25 fields."
            )

        return {
            "title": request.form.get(
                "title",
                "",
            )[:256],
            "description": request.form.get(
                "description",
                "",
            )[:4096],
            "colour": parse_colour(
                request.form.get(
                    "colour"
                )
            ),
            "reply": parse_bool(
                request.form.get(
                    "reply"
                )
            ),
            "author": request.form.get(
                "author",
                "",
            )[:256],
            "footer": request.form.get(
                "footer",
                "",
            )[:2048],
            "thumbnail": request.form.get(
                "thumbnail",
                "",
            ).strip(),
            "image": request.form.get(
                "image",
                "",
            ).strip(),
            "fields": fields,
        }

    if action_type == ADD_REACTION:
        emoji = request.form.get(
            "emoji",
            "",
        ).strip()

        if not emoji:
            raise ValueError(
                "Choose an emoji."
            )

        target = request.form.get(
            "target",
            "trigger",
        )

        if target not in {
            "trigger",
            "response",
        }:
            target = "trigger"

        return {
            "emoji": emoji,
            "target": target,
        }

    if action_type in {
        ADD_ROLE,
        REMOVE_ROLE,
    }:
        role_id = parse_int(
            request.form.get(
                "role_id"
            )
        )

        if not role_id:
            raise ValueError(
                "Choose a role."
            )

        target = request.form.get(
            "target",
            "invoker",
        )

        if target not in {
            "invoker",
            "target",
        }:
            target = "invoker"

        return {
            "role_id": role_id,
            "target": target,
        }

    if action_type == DELETE_MESSAGE:
        target = request.form.get(
            "target",
            "trigger",
        )

        if target not in {
            "trigger",
            "response",
        }:
            target = "trigger"

        delay = max(
            0,
            min(
                parse_float(
                    request.form.get(
                        "delay"
                    )
                ),
                86400,
            ),
        )

        return {
            "target": target,
            "delay": delay,
        }

    raise ValueError(
        f"Unknown action type `{action_type}`."
    )


def build_default_action(
    action_type: str,
) -> dict[str, Any]:
    if action_type == SEND_MESSAGE:
        return {
            "content": "",
            "reply": False,
        }

    if action_type == SEND_EMBED:
        return {
            "title": "",
            "description": "",
            "colour": 0x5865F2,
            "reply": False,
            "author": "",
            "footer": "",
            "thumbnail": "",
            "image": "",
            "fields": [],
        }

    if action_type == ADD_REACTION:
        return {
            "emoji": "✅",
            "target": "trigger",
        }

    if action_type in {
        ADD_ROLE,
        REMOVE_ROLE,
    }:
        return {
            "role_id": 0,
            "target": "invoker",
        }

    if action_type == DELETE_MESSAGE:
        return {
            "target": "trigger",
            "delay": 0,
        }

    raise ValueError(
        "Unknown action type."
    )


def register_custom_command_webui(
    *,
    app: Flask,
    bot: discord.Client,
    require_owner_page: Callable[[], Any],
    get_selected_guild: Callable[
        [str | None],
        discord.Guild | None,
    ],
    get_available_guilds: Callable[
        [],
        list[dict[str, str]],
    ],
    get_guild_roles: Callable[
        [discord.Guild],
        list[dict[str, str]],
    ],
    render_admin_page: Callable[..., str],
    run_coro_from_flask: Callable[
        [Any],
        Any,
    ],
) -> None:
    def get_store():
        store = getattr(
            bot,
            "custom_command_store",
            None,
        )

        if store is None:
            raise RuntimeError(
                "Custom command store is not available."
            )

        return store

    def render_page(
        *,
        selected_guild: discord.Guild | None,
        selected_command_name: str = "",
        message: str | None = None,
        error: str | None = None,
    ) -> str:
        commands = []
        selected_command = None
        roles: list[
            dict[str, str]
        ] = []

        if selected_guild is not None:
            store = get_store()

            commands = run_coro_from_flask(
                store.list(
                    selected_guild.id
                )
            )

            roles = get_guild_roles(
                selected_guild
            )

            if selected_command_name:
                selected_command = (
                    run_coro_from_flask(
                        store.get(
                            selected_guild.id,
                            selected_command_name,
                        )
                    )
                )

            if (
                selected_command is None
                and commands
            ):
                selected_command = commands[0]

        body = render_template(
            "custom_commands.html",
            guilds=get_available_guilds(),
            selected_guild_id=(
                str(
                    selected_guild.id
                )
                if selected_guild
                else None
            ),
            commands=commands,
            selected_command=selected_command,
            roles=roles,
            levels=LEVELS,
            action_labels=ACTION_LABELS,
            action_types=list(
                ACTION_LABELS.items()
            ),
            prefix=str(
                getattr(
                    bot.config,
                    "prefix",
                    "!",
                )
            ),
        )

        return render_admin_page(
            title="TFSBot Custom Commands",
            active_page="custom_commands",
            body_template=body,
            message=message,
            error=error,
        )

    @app.route(
        "/custom-commands",
        methods=[
            "GET",
            "POST",
        ],
    )
    def custom_commands_page():
        owner_error = require_owner_page()

        if owner_error is not None:
            return owner_error

        guild_id_text = (
            request.form.get(
                "guild_id"
            )
            if request.method == "POST"
            else request.args.get(
                "guild_id"
            )
        )

        selected_guild = (
            get_selected_guild(
                guild_id_text
            )
        )

        selected_command_name = (
            request.form.get(
                "command_name",
                "",
            )
            if request.method == "POST"
            else request.args.get(
                "command",
                "",
            )
        ).strip().lower()

        message: str | None = None
        error: str | None = None

        try:
            if request.method == "POST":
                if selected_guild is None:
                    raise RuntimeError(
                        "No server selected."
                    )

                store = get_store()

                action = request.form.get(
                    "action",
                    "",
                )

                if action == "create_command":
                    new_name = request.form.get(
                        "new_name",
                        "",
                    )

                    description = (
                        request.form.get(
                            "new_description",
                            "",
                        )
                    )

                    level = request.form.get(
                        "new_required_level",
                        LEVEL_PUBLIC,
                    )

                    cooldown = max(
                        0,
                        min(
                            parse_int(
                                request.form.get(
                                    "new_cooldown"
                                )
                            ),
                            86400,
                        ),
                    )

                    delete_trigger = (
                        parse_bool(
                            request.form.get(
                                "new_delete_trigger"
                            )
                        )
                    )

                    run_coro_from_flask(
                        store.create(
                            guild_id=selected_guild.id,
                            name=new_name,
                            description=description,
                            created_by=get_creator_id(
                                bot
                            ),
                            required_level=level,
                            cooldown_seconds=cooldown,
                            delete_trigger=delete_trigger,
                        )
                    )

                    selected_command_name = (
                        store.normalise_name(
                            new_name
                        )
                    )

                    message = (
                        f"Created `{selected_command_name}`."
                    )

                elif action == "save_command":
                    if not selected_command_name:
                        raise RuntimeError(
                            "No custom command selected."
                        )

                    old_name = (
                        selected_command_name
                    )

                    new_name = (
                        request.form.get(
                            "edited_name",
                            old_name,
                        )
                    )

                    new_name = (
                        store.normalise_name(
                            new_name
                        )
                    )

                    if (
                        new_name
                        != old_name
                    ):
                        renamed = (
                            run_coro_from_flask(
                                store.rename(
                                    selected_guild.id,
                                    old_name,
                                    new_name,
                                )
                            )
                        )

                        if not renamed:
                            raise RuntimeError(
                                "Custom command was not found."
                            )

                        selected_command_name = (
                            new_name
                        )

                    updated = (
                        run_coro_from_flask(
                            store.update(
                                selected_guild.id,
                                selected_command_name,
                                description=(
                                    request.form.get(
                                        "description",
                                        "",
                                    )
                                ),
                                enabled=parse_bool(
                                    request.form.get(
                                        "enabled"
                                    )
                                ),
                                required_level=(
                                    request.form.get(
                                        "required_level",
                                        LEVEL_PUBLIC,
                                    )
                                ),
                                cooldown_seconds=max(
                                    0,
                                    min(
                                        parse_int(
                                            request.form.get(
                                                "cooldown_seconds"
                                            )
                                        ),
                                        86400,
                                    ),
                                ),
                                delete_trigger=(
                                    parse_bool(
                                        request.form.get(
                                            "delete_trigger"
                                        )
                                    )
                                ),
                            )
                        )
                    )

                    if not updated:
                        raise RuntimeError(
                            "Custom command was not found."
                        )

                    message = (
                        f"Saved `{selected_command_name}`."
                    )

                elif action == "delete_command":
                    if not selected_command_name:
                        raise RuntimeError(
                            "No custom command selected."
                        )

                    confirmation = (
                        request.form.get(
                            "delete_confirm",
                            "",
                        )
                        .strip()
                        .upper()
                    )

                    if confirmation != "DELETE":
                        raise RuntimeError(
                            "Type DELETE to confirm command deletion."
                        )

                    deleted = (
                        run_coro_from_flask(
                            store.delete(
                                selected_guild.id,
                                selected_command_name,
                            )
                        )
                    )

                    if not deleted:
                        raise RuntimeError(
                            "Custom command was not found."
                        )

                    message = (
                        f"Deleted `{selected_command_name}`."
                    )

                    selected_command_name = ""

                elif action == "add_action":
                    if not selected_command_name:
                        raise RuntimeError(
                            "No custom command selected."
                        )

                    action_type = (
                        request.form.get(
                            "new_action_type",
                            "",
                        )
                    )

                    if (
                        action_type
                        not in ACTION_LABELS
                    ):
                        raise ValueError(
                            "Choose a valid action type."
                        )

                    action_number = (
                        run_coro_from_flask(
                            store.add_action(
                                selected_guild.id,
                                selected_command_name,
                                action_type,
                                build_default_action(
                                    action_type
                                ),
                            )
                        )
                    )

                    message = (
                        f"Added action #{action_number}."
                    )

                elif action == "save_action":
                    if not selected_command_name:
                        raise RuntimeError(
                            "No custom command selected."
                        )

                    action_number = parse_int(
                        request.form.get(
                            "action_number"
                        )
                    )

                    action_type = (
                        request.form.get(
                            "action_type",
                            "",
                        )
                    )

                    data = build_action_data(
                        action_type,
                        action_number,
                    )

                    updated = (
                        run_coro_from_flask(
                            store.update_action(
                                selected_guild.id,
                                selected_command_name,
                                action_number,
                                action_type,
                                data,
                            )
                        )
                    )

                    if not updated:
                        raise RuntimeError(
                            "Action was not found."
                        )

                    message = (
                        f"Saved action #{action_number}."
                    )

                elif action == "delete_action":
                    action_number = parse_int(
                        request.form.get(
                            "action_number"
                        )
                    )

                    deleted = (
                        run_coro_from_flask(
                            store.remove_action(
                                selected_guild.id,
                                selected_command_name,
                                action_number,
                            )
                        )
                    )

                    if not deleted:
                        raise RuntimeError(
                            "Action was not found."
                        )

                    message = (
                        f"Deleted action #{action_number}."
                    )

                elif action in {
                    "move_action_up",
                    "move_action_down",
                }:
                    action_number = parse_int(
                        request.form.get(
                            "action_number"
                        )
                    )

                    new_position = (
                        action_number - 1
                        if action
                        == "move_action_up"
                        else action_number + 1
                    )

                    command = (
                        run_coro_from_flask(
                            store.get(
                                selected_guild.id,
                                selected_command_name,
                            )
                        )
                    )

                    if command is None:
                        raise RuntimeError(
                            "Custom command was not found."
                        )

                    if (
                        new_position < 1
                        or new_position
                        > len(
                            command.actions
                        )
                    ):
                        raise RuntimeError(
                            "Action is already at the end."
                            if action
                            == "move_action_down"
                            else "Action is already first."
                        )

                    moved = (
                        run_coro_from_flask(
                            store.move_action(
                                selected_guild.id,
                                selected_command_name,
                                action_number,
                                new_position,
                            )
                        )
                    )

                    if not moved:
                        raise RuntimeError(
                            "Could not move action."
                        )

                    message = "Action moved."

                elif action == "clear_actions":
                    confirmation = (
                        request.form.get(
                            "clear_confirm",
                            "",
                        )
                        .strip()
                        .upper()
                    )

                    if confirmation != "CLEAR":
                        raise RuntimeError(
                            "Type CLEAR to remove every action."
                        )

                    removed = (
                        run_coro_from_flask(
                            store.clear_actions(
                                selected_guild.id,
                                selected_command_name,
                            )
                        )
                    )

                    message = (
                        f"Removed {removed} action(s)."
                    )

                else:
                    raise RuntimeError(
                        "Unknown WebUI action."
                    )

        except Exception as caught_error:
            error = str(
                caught_error
            )

        return render_page(
            selected_guild=selected_guild,
            selected_command_name=(
                selected_command_name
            ),
            message=message,
            error=error,
        )