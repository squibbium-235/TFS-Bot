"""Owner upload manager, plus a login-gated file route for any role.

Mutations require an owner. Fetching a stored image only requires a
logged-in session, after the reference has been checked for traversal.
"""

from __future__ import annotations

from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.webui.helpers import (
    require_owner,
    webui_context,
    require_login,
)


blueprint = Blueprint(
    "uploads",
    __name__,
)


@blueprint.route(
    "/uploads-manager",
    methods=[
        "GET",
        "POST",
    ],
)

def index():
    """
    Manage uploads belonging only to the
    selected Discord guild.
    """
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    selected_guild = context.selected_guild(
        request.form.get(
            "guild_id"
        )
        if request.method == "POST"
        else request.args.get(
            "guild_id"
        )
    )

    message: str | None = None
    error: str | None = None
    selected_folder = ""

    if selected_guild is None:
        return render_template(
            "uploads/index.html",
            **context.template_context(
                title="Sanctuary Servo Uploads",
                active_page="uploads",
                guilds=(
                    context.available_guilds()
                ),
                selected_guild_id=None,
                folders=[],
                uploaded_images=[],
                selected_folder="",
                message=None,
                error=(
                    "No server selected."
                ),
            ),
        )

    uploads = (
        context.uploads
        .for_guild(
            selected_guild.id
        )
    )

    try:
        if request.method == "POST":
            action = request.form.get(
                "action",
                "",
            )

            if action == "create_folder":
                folder = (
                    uploads.create_folder(
                        request.form.get(
                            "folder",
                            "",
                        )
                    )
                )

                message = (
                    f"Created folder "
                    f"{folder}."
                )

            elif action == "upload_file":
                selected_folder = (
                    request.form.get(
                        "new_folder"
                    )
                    or request.form.get(
                        "folder"
                    )
                    or ""
                )

                reference = (
                    uploads.save_upload(
                        request.files.get(
                            "image"
                        ),
                        selected_folder,
                    )
                )

                selected_folder = (
                    uploads.validate_folder(
                        selected_folder
                    )
                )

                message = (
                    f"Uploaded "
                    f"{reference}."
                )

            elif action == "delete_file":
                reference = (
                    uploads.delete_file(
                        request.form.get(
                            "file_reference",
                            "",
                        )
                    )
                )

                message = (
                    f"Deleted "
                    f"{reference}."
                )

            elif action == "delete_folder":
                if (
                    request.form.get(
                        "confirm",
                        "",
                    ).strip()
                    != "DELETE"
                ):
                    raise RuntimeError(
                        "Type DELETE to "
                        "confirm folder "
                        "deletion."
                    )

                folder = (
                    uploads.delete_folder(
                        request.form.get(
                            "folder",
                            "",
                        )
                    )
                )

                message = (
                    f"Deleted folder "
                    f"{folder}."
                )

            else:
                raise RuntimeError(
                    "Unknown uploads action."
                )

    except Exception as caught_error:
        error = str(
            caught_error
        )

    return render_template(
        "uploads/index.html",
        **context.template_context(
            title="Sanctuary Servo Uploads",
            active_page="uploads",
            guilds=(
                context.available_guilds()
            ),
            selected_guild_id=(
                str(
                    selected_guild.id
                )
            ),
            folders=(
                uploads.list_folders()
            ),
            uploaded_images=(
                uploads.list_images()
            ),
            selected_folder=(
                selected_folder
            ),
            message=message,
            error=error,
        ),
    )

@blueprint.route(
    "/uploads/<int:guild_id>/<path:filename>"
)
def file(
    guild_id: int,
    filename: str,
):
    """
    Serve a file only when the current WebUI
    session can access its guild.
    """
    context = webui_context()

    login_error = (
        require_login()
    )

    if login_error is not None:
        return login_error

    if not context.guild_is_accessible(
        guild_id
    ):
        return (
            "File not found.",
            404,
        )

    uploads = (
        context.uploads
        .for_guild(
            guild_id
        )
    )

    try:
        path = (
            uploads.image_path(
                filename
            )
        )

    except ValueError:
        return (
            "Invalid upload path.",
            400,
        )

    if (
        not path.exists()
        or not path.is_file()
    ):
        return (
            "File not found.",
            404,
        )

    return send_file(
        path
    )