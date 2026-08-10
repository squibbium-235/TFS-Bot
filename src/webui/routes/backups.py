from __future__ import annotations

from io import BytesIO
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    request,
    send_file,
)

from src.services.backup_service import (
    BackupError,
    BackupService,
)
from src.webui.helpers import (
    has_fresh_authentication,
    require_owner,
    webui_context,
)


blueprint = Blueprint(
    "backups",
    __name__,
)


def get_database_path() -> Path:
    context = webui_context()

    application_store = getattr(
        context.bot,
        "application_store",
        None,
    )

    if application_store is not None:
        raw_path = getattr(
            application_store,
            "database_path",
            None,
        )

        if raw_path is not None:
            return Path(
                raw_path
            )

    return Path(
        getattr(
            context.bot.config,
            "application_db_path",
            "data/tfsbot.sqlite3",
        )
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
                f"{size:.1f} "
                f"{suffix}"
            )

    return (
        f"{size:.1f} PB"
    )


@blueprint.route(
    "/backups",
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

    restore_completed = False

    database_path = (
        get_database_path()
    )

    uploads_path = Path(
        "data/uploads"
    )

    backup_service = BackupService(
        project_root=Path("."),
        database_path=database_path,
    )

    if request.method == "POST":
        try:
            action = request.form.get(
                "action",
                "",
            )

            if action == "create_backup":
                password = request.form.get(
                    "password",
                    "",
                )

                confirm_password = (
                    request.form.get(
                        "confirm_password",
                        "",
                    )
                )

                if (
                    password
                    != confirm_password
                ):
                    raise RuntimeError(
                        "Backup passwords "
                        "do not match."
                    )

                include_env = (
                    request.form.get(
                        "include_env"
                    )
                    == "1"
                )

                backup = (
                    backup_service
                    .create_encrypted_backup(
                        password=password,
                        include_env=(
                            include_env
                        ),
                    )
                )

                return send_file(
                    BytesIO(
                        backup.data
                    ),
                    as_attachment=True,
                    download_name=(
                        backup.filename
                    ),
                    mimetype=(
                        "application/"
                        "octet-stream"
                    ),
                )

            if action == "restore_backup":
                restore_confirm = (
                    request.form.get(
                        "restore_confirm",
                        "",
                    ).strip()
                )
                
                if not (
                    has_fresh_authentication()
                ):
                    raise RuntimeError(
                        "Backup restore requires "
                        "a fresh login. Log out, "
                        "sign back in, and retry "
                        "within 10 minutes."
                    )

                if (
                    restore_confirm
                    != "RESTORE"
                ):
                    raise RuntimeError(
                        "Type RESTORE to "
                        "confirm backup "
                        "restoration."
                    )

                uploaded_file = (
                    request.files.get(
                        "backup_file"
                    )
                )

                if (
                    uploaded_file is None
                    or not uploaded_file.filename
                ):
                    raise RuntimeError(
                        "No backup file "
                        "was uploaded."
                    )

                if not (
                    uploaded_file.filename
                    .lower()
                    .endswith(
                        ".tfsbackup"
                    )
                ):
                    raise RuntimeError(
                        "Backup file must "
                        "use the .tfsbackup "
                        "extension."
                    )

                restore_password = (
                    request.form.get(
                        "restore_password",
                        "",
                    )
                )

                restore_result = (
                    backup_service
                    .restore_encrypted_backup(
                        encrypted_data=(
                            uploaded_file.read()
                        ),
                        password=(
                            restore_password
                        ),
                        restore_uploads=(
                            request.form.get(
                                "restore_uploads"
                            )
                            == "1"
                        ),
                        restore_env=(
                            request.form.get(
                                "restore_env"
                            )
                            == "1"
                        ),
                    )
                )

                restored_bits: list[str] = []

                if (
                    restore_result
                    .restored_database
                ):
                    restored_bits.append(
                        "database"
                    )

                if (
                    restore_result
                    .restored_uploads
                ):
                    restored_bits.append(
                        "uploads"
                    )

                if (
                    restore_result
                    .restored_env
                ):
                    restored_bits.append(
                        ".env"
                    )

                restored_text = (
                    ", ".join(
                        restored_bits
                    )
                    or "nothing"
                )

                restore_completed = True

                message = (
                    f"Restored "
                    f"{restored_text}. "
                    "Safety copy created at "
                    f"{restore_result.safety_backup_directory}. "
                    "Restart the bot now. "
                    "Do not keep using the "
                    "WebUI until the bot "
                    "has restarted."
                )

            else:
                raise RuntimeError(
                    "Unknown backup action."
                )

        except BackupError as caught_error:
            error = str(
                caught_error
            )

        except Exception as caught_error:
            error = str(
                caught_error
            )

    database_size = (
        format_file_size(
            database_path
            .stat()
            .st_size
        )
        if database_path.exists()
        else "Missing"
    )

    uploads_state = (
        "Present"
        if uploads_path.exists()
        else "Not created yet"
    )

    return render_template(
        "backups/index.html",
        **context.template_context(
            title="TFSBot Backups",
            active_page="backups",
            database_path=str(
                database_path
            ),
            database_size=(
                database_size
            ),
            uploads_state=(
                uploads_state
            ),
            restore_completed=(
                restore_completed
            ),
            message=message,
            error=error,
        ),
    )