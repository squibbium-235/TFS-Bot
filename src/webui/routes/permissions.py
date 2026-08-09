from __future__ import annotations

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.services.permission_store import (
    LEVEL_ADMIN,
    LEVEL_OWNER,
    LEVEL_PUBLIC,
    LEVEL_STAFF,
)
from src.webui.helpers import (
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "permissions",
    __name__,
)


def make_safe_command_key(
    command_key: str,
) -> str:
    return (
        command_key
        .replace(".", "__dot__")
        .replace("-", "__dash__")
        .replace(" ", "__space__")
    )


def level_choices(
) -> list[dict[str, str]]:
    return [
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


def role_ids_from_form(
    field_name: str,
) -> list[int]:
    role_ids: list[int] = []

    for raw_role_id in (
        request.form.getlist(
            field_name
        )
    ):
        raw_role_id = (
            raw_role_id.strip()
        )

        if not raw_role_id:
            continue

        role_ids.append(
            int(raw_role_id)
        )

    return sorted(
        set(role_ids)
    )


@blueprint.route(
    "/permissions",
    methods=[
        "GET",
        "POST",
    ],
)
def index():
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    message: str | None = None
    error: str | None = None

    selected_guild = (
        context.selected_guild(
            request.form.get(
                "guild_id"
            )
            if request.method == "POST"
            else request.args.get(
                "guild_id"
            )
        )
    )

    permission_store = (
        context.permission_store()
    )

    try:
        if request.method == "POST":
            if selected_guild is None:
                raise RuntimeError(
                    "No server selected."
                )

            owner_role_ids = (
                role_ids_from_form(
                    "webui_owner_role_ids"
                )
            )

            viewer_role_ids = (
                role_ids_from_form(
                    "webui_viewer_role_ids"
                )
            )

            if (
                not owner_role_ids
                and not context.access
                .env_owner_role_ids()
            ):
                raise RuntimeError(
                    "Choose at least one WebUI "
                    "owner role, or configure "
                    "WEBUI_DISCORD_OWNER_ROLE_IDS "
                    "in .env before clearing this."
                )

            context.access.set_stored_role_ids(
                guild_id=selected_guild.id,
                access_level="owner",
                role_ids=owner_role_ids,
            )

            context.access.set_stored_role_ids(
                guild_id=selected_guild.id,
                access_level="viewer",
                role_ids=viewer_role_ids,
            )

            for level in [
                LEVEL_STAFF,
                LEVEL_ADMIN,
                LEVEL_OWNER,
            ]:
                role_id_text = (
                    request.form.get(
                        f"role_{level}",
                        "",
                    )
                    .strip()
                )

                if role_id_text:
                    context.run_coro(
                        permission_store.set_role(
                            guild_id=(
                                selected_guild.id
                            ),
                            level=level,
                            role_id=int(
                                role_id_text
                            ),
                        )
                    )

                else:
                    context.run_coro(
                        permission_store.clear_role(
                            guild_id=(
                                selected_guild.id
                            ),
                            level=level,
                        )
                    )

            for command_key in (
                request.form.getlist(
                    "command_key[]"
                )
            ):
                safe_key = (
                    make_safe_command_key(
                        command_key
                    )
                )

                level = request.form.get(
                    (
                        "command_level_"
                        f"{safe_key}"
                    ),
                    LEVEL_PUBLIC,
                )

                context.run_coro(
                    permission_store
                    .set_command_level(
                        guild_id=(
                            selected_guild.id
                        ),
                        command_key=(
                            command_key
                        ),
                        level=level,
                    )
                )

            message = (
                "Permissions and WebUI "
                "access saved."
            )

        roles: list[
            dict[str, str]
        ] = []

        role_settings: list[
            dict[str, str]
        ] = []

        commands: list[
            dict[str, str]
        ] = []

        if selected_guild is not None:
            roles = context.guild_roles(
                selected_guild
            )

            role_ids = context.run_coro(
                permission_store.get_role_ids(
                    selected_guild.id
                )
            )

            role_settings = [
                {
                    "level": LEVEL_STAFF,
                    "label": "Staff role",
                    "role_id": str(
                        role_ids.get(
                            LEVEL_STAFF
                        )
                        or ""
                    ),
                },
                {
                    "level": LEVEL_ADMIN,
                    "label": "Admin role",
                    "role_id": str(
                        role_ids.get(
                            LEVEL_ADMIN
                        )
                        or ""
                    ),
                },
                {
                    "level": LEVEL_OWNER,
                    "label": "Owner role",
                    "role_id": str(
                        role_ids.get(
                            LEVEL_OWNER
                        )
                        or ""
                    ),
                },
            ]

            command_levels = (
                context.run_coro(
                    permission_store
                    .get_all_command_levels(
                        selected_guild.id
                    )
                )
            )

            commands = [
                {
                    "key": command_key,
                    "safe_key": (
                        make_safe_command_key(
                            command_key
                        )
                    ),
                    "level": level,
                }
                for (
                    command_key,
                    level,
                )
                in sorted(
                    command_levels.items()
                )
            ]

    except Exception as caught_error:
        error = str(
            caught_error
        )

        roles = []
        role_settings = []
        commands = []

    return render_template(
        "permissions/index.html",
        **context.template_context(
            title="TFSBot Permissions",
            active_page="permissions",
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
            roles=roles,
            role_settings=role_settings,
            commands=commands,
            levels=level_choices(),
            webui_access=(
                context.access.build_context(
                    selected_guild
                )
            ),
            message=message,
            error=error,
        ),
    )