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
    owner_error = require_owner()

    if owner_error is not None:
        return owner_error

    context = webui_context()

    message: str | None = None
    error: str | None = None
    selected_folder = ""

    try:
        if request.method == "POST":
            action = request.form.get(
                "action",
                "",
            )

            if action == "create_folder":
                folder = (
                    context.uploads
                    .create_folder(
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
                    context.uploads
                    .save_upload(
                        request.files.get(
                            "image"
                        ),
                        selected_folder,
                    )
                )

                selected_folder = (
                    context.uploads
                    .validate_folder(
                        selected_folder
                    )
                )

                message = (
                    f"Uploaded "
                    f"{reference}."
                )

            elif action == "delete_file":
                reference = (
                    context.uploads
                    .delete_file(
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
                    context.uploads
                    .delete_folder(
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
            title="TFSBot Uploads",
            active_page="uploads",
            folders=(
                context.uploads
                .list_folders()
            ),
            uploaded_images=(
                context.uploads
                .list_images()
            ),
            selected_folder=(
                selected_folder
            ),
            message=message,
            error=error,
        ),
    )


@blueprint.route(
    "/uploads/<path:filename>"
)
def file(
    filename: str,
):
    context = webui_context()

    login_error = (
        require_login()
    )

    if login_error is not None:
        return login_error

    try:
        path = (
            context.uploads
            .image_path(
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