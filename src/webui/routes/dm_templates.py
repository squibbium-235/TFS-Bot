from __future__ import annotations

from flask import (
    Blueprint,
    render_template,
    request,
)

from src.services.dm_template_store import (
    DEFAULT_DM_TEMPLATES,
    DM_TEMPLATE_LABELS,
    DM_TEMPLATE_ORDER,
)
from src.webui.helpers import (
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "dm_templates",
    __name__,
)


def build_templates(
    guild_id: int,
) -> list[dict[str, object]]:
    context = webui_context()

    template_store = (
        context.template_store()
    )

    stored_templates = (
        context.run_coro(
            template_store.get_all_templates(
                guild_id
            )
        )
    )

    templates: list[
        dict[str, object]
    ] = []

    for stored_template in stored_templates:
        template_key = (
            stored_template.template_key
        )

        templates.append(
            {
                "key": template_key,
                "label": (
                    DM_TEMPLATE_LABELS.get(
                        template_key,
                        template_key.replace(
                            "_",
                            " ",
                        ).title(),
                    )
                ),
                "text": (
                    stored_template.template_text
                ),
                "default": (
                    DEFAULT_DM_TEMPLATES.get(
                        template_key,
                        "",
                    )
                ),
                "is_custom": (
                    stored_template.is_custom
                ),
            }
        )

    return templates


@blueprint.route(
    "/dm-templates",
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

    templates: list[
        dict[str, object]
    ] = []

    try:
        template_store = (
            context.template_store()
        )

        if request.method == "POST":
            if selected_guild is None:
                raise RuntimeError(
                    "No server selected."
                )

            for template_key in (
                DM_TEMPLATE_ORDER
            ):
                template_text = (
                    request.form.get(
                        f"template_{template_key}",
                        "",
                    )
                    .strip()
                )

                default_text = (
                    DEFAULT_DM_TEMPLATES[
                        template_key
                    ]
                )

                if (
                    template_text
                    == default_text
                ):
                    context.run_coro(
                        template_store
                        .reset_template(
                            guild_id=(
                                selected_guild.id
                            ),
                            template_key=(
                                template_key
                            ),
                        )
                    )

                else:
                    context.run_coro(
                        template_store
                        .set_template(
                            guild_id=(
                                selected_guild.id
                            ),
                            template_key=(
                                template_key
                            ),
                            template_text=(
                                template_text
                            ),
                        )
                    )

            message = (
                "DM templates saved."
            )

        if selected_guild is not None:
            templates = build_templates(
                selected_guild.id
            )

    except Exception as caught_error:
        error = str(
            caught_error
        )

        templates = []

    return render_template(
        "dm_templates/index.html",
        **context.template_context(
            title="TFSBot DM Templates",
            active_page="dm_templates",
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
            templates=templates,
            message=message,
            error=error,
        ),
    )