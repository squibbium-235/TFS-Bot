from __future__ import annotations

import base64

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

import discord

from werkzeug.utils import (
    secure_filename,
)


UPLOAD_DIR = Path(
    "data/uploads/images"
)

ALLOWED_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}


class WebUIUploadManager:
    def __init__(
        self,
        upload_dir: Path = UPLOAD_DIR,
    ) -> None:
        self.upload_dir = upload_dir

        self.upload_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def validate_filename(
        self,
        filename: str,
    ) -> str:
        safe_name = secure_filename(
            filename
        )

        if not safe_name:
            raise ValueError(
                "Invalid filename."
            )

        extension = Path(
            safe_name
        ).suffix.lower()

        if (
            extension
            not in ALLOWED_IMAGE_EXTENSIONS
        ):
            raise ValueError(
                "Unsupported image type. "
                "Use PNG, JPG, JPEG, GIF, or WEBP."
            )

        return safe_name

    def validate_folder(
        self,
        folder: str | None,
    ) -> str:
        folder = (
            folder
            or ""
        ).strip().replace(
            "\\",
            "/",
        )

        if folder in {
            "",
            ".",
        }:
            return ""

        parts: list[str] = []

        for raw_part in folder.split(
            "/"
        ):
            raw_part = raw_part.strip()

            if not raw_part:
                continue

            safe_part = secure_filename(
                raw_part
            )

            if not safe_part:
                raise ValueError(
                    "Invalid folder name."
                )

            if safe_part in {
                ".",
                "..",
            }:
                raise ValueError(
                    "Invalid folder name."
                )

            parts.append(
                safe_part
            )

        if not parts:
            return ""

        return "/".join(
            parts
        )

    def folder_path(
        self,
        folder: str | None,
    ) -> Path:
        safe_folder = (
            self.validate_folder(
                folder
            )
        )

        folder_path = (
            self.upload_dir
            / safe_folder
            if safe_folder
            else self.upload_dir
        )

        resolved_root = (
            self.upload_dir.resolve()
        )

        resolved_folder = (
            folder_path.resolve()
        )

        if (
            resolved_root
            not in [
                resolved_folder,
                *resolved_folder.parents,
            ]
        ):
            raise ValueError(
                "Invalid upload folder."
            )

        return folder_path

    def validate_reference(
        self,
        reference: str,
    ) -> str:
        reference = (
            reference
            .strip()
            .replace(
                "\\",
                "/",
            )
        )

        if not reference:
            raise ValueError(
                "Invalid uploaded image reference."
            )

        reference_path = Path(
            reference
        )

        folder = self.validate_folder(
            str(
                reference_path.parent
            )
        )

        filename = self.validate_filename(
            reference_path.name
        )

        if folder in {
            ".",
            "",
        }:
            return filename

        return (
            f"{folder}/{filename}"
        )

    def image_path(
        self,
        reference: str,
    ) -> Path:
        safe_reference = (
            self.validate_reference(
                reference
            )
        )

        return (
            self.upload_dir
            / safe_reference
        )

    def preview_url(
        self,
        path: Path,
    ) -> str:
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }

        mime_type = mime_types.get(
            path.suffix.lower()
        )

        if mime_type is None:
            raise ValueError(
                "Unsupported preview image "
                f"type: {path.suffix}"
            )

        encoded = base64.b64encode(
            path.read_bytes()
        ).decode(
            "ascii"
        )

        return (
            f"data:{mime_type};"
            f"base64,{encoded}"
        )

    @staticmethod
    def format_size(
        size_bytes: int,
    ) -> str:
        if size_bytes < 1024:
            return (
                f"{size_bytes} B"
            )

        if (
            size_bytes
            < 1024 * 1024
        ):
            return (
                f"{size_bytes / 1024:.1f} KB"
            )

        return (
            f"{size_bytes / (1024 * 1024):.1f} MB"
        )

    def attachment_filename(
        self,
        reference: str,
    ) -> str:
        safe_reference = (
            self.validate_reference(
                reference
            )
        )

        path = Path(
            safe_reference
        )

        if str(
            path.parent
        ) in {
            ".",
            "",
        }:
            return path.name

        folder_prefix = "__".join(
            path.parent.parts
        )

        return (
            f"{folder_prefix}__"
            f"{path.name}"
        )

    def list_folders(
        self,
    ) -> list[dict[str, str]]:
        folders: list[
            dict[str, str]
        ] = []

        if not self.upload_dir.exists():
            return folders

        paths = sorted(
            self.upload_dir.rglob("*"),
            key=lambda item: (
                item
                .as_posix()
                .lower()
            ),
        )

        for path in paths:
            if not path.is_dir():
                continue

            relative_path = (
                path
                .relative_to(
                    self.upload_dir
                )
                .as_posix()
            )

            if (
                not relative_path
                or relative_path == "."
            ):
                continue

            folders.append(
                {
                    "path": (
                        relative_path
                    ),
                    "label": (
                        relative_path
                    ),
                }
            )

        return folders

    def list_images(
        self,
    ) -> list[dict[str, str]]:
        images: list[
            dict[str, str]
        ] = []

        if not self.upload_dir.exists():
            return images

        image_paths = [
            path
            for path
            in self.upload_dir.rglob(
                "*"
            )
            if (
                path.is_file()
                and path.suffix.lower()
                in ALLOWED_IMAGE_EXTENSIONS
            )
        ]

        image_paths.sort(
            key=lambda item: (
                item.stat().st_mtime
            ),
            reverse=True,
        )

        for path in image_paths:
            relative_path = (
                path.relative_to(
                    self.upload_dir
                )
            )

            reference = (
                relative_path
                .as_posix()
            )

            folder = (
                relative_path
                .parent
                .as_posix()
            )

            if folder == ".":
                folder = ""

            stat = path.stat()

            images.append(
                {
                    "reference": (
                        reference
                    ),
                    "filename": (
                        path.name
                    ),
                    "label": (
                        reference
                    ),
                    "folder": (
                        folder
                    ),
                    "folder_label": (
                        folder
                        or "Root"
                    ),
                    "url": (
                        self.preview_url(
                            path
                        )
                    ),
                    "size": (
                        self.format_size(
                            stat.st_size
                        )
                    ),
                    "modified": (
                        datetime
                        .fromtimestamp(
                            stat.st_mtime,
                            timezone.utc,
                        )
                        .strftime(
                            "%Y-%m-%d "
                            "%H:%M UTC"
                        )
                    ),
                }
            )

        return images

    def build_attachment_files(
        self,
        *,
        image_reference: (
            str | None
        ) = None,
        thumbnail_reference: (
            str | None
        ) = None,
        author_icon_reference: (
            str | None
        ) = None,
    ) -> tuple[
        str | None,
        str | None,
        str | None,
        list[discord.File],
    ]:
        files: list[
            discord.File
        ] = []

        attached_references: set[
            str
        ] = set()

        image_url: str | None = None
        thumbnail_url: str | None = None
        author_icon_url: str | None = None

        selections = [
            (
                image_reference,
                "image",
            ),
            (
                thumbnail_reference,
                "thumbnail",
            ),
            (
                author_icon_reference,
                "author_icon",
            ),
        ]

        for (
            selected_reference,
            target,
        ) in selections:
            if not selected_reference:
                continue

            safe_reference = (
                self.validate_reference(
                    selected_reference
                )
            )

            path = self.image_path(
                safe_reference
            )

            if not path.exists():
                raise FileNotFoundError(
                    "Uploaded image not found: "
                    f"{selected_reference}"
                )

            attachment_filename = (
                self.attachment_filename(
                    safe_reference
                )
            )

            if (
                safe_reference
                not in attached_references
            ):
                files.append(
                    discord.File(
                        path,
                        filename=(
                            attachment_filename
                        ),
                    )
                )

                attached_references.add(
                    safe_reference
                )

            attachment_url = (
                "attachment://"
                f"{attachment_filename}"
            )

            if target == "image":
                image_url = (
                    attachment_url
                )

            elif target == "thumbnail":
                thumbnail_url = (
                    attachment_url
                )

            else:
                author_icon_url = (
                    attachment_url
                )

        return (
            image_url,
            thumbnail_url,
            author_icon_url,
            files,
        )
        
    def create_folder(
        self,
        folder: str,
    ) -> str:
        safe_folder = self.validate_folder(
            folder
        )

        if not safe_folder:
            raise ValueError(
                "Enter a folder name."
            )

        folder_path = self.folder_path(
            safe_folder
        )

        folder_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return safe_folder

    def save_upload(
        self,
        uploaded_file,
        folder: str | None = None,
    ) -> str:
        if (
            uploaded_file is None
            or not uploaded_file.filename
        ):
            raise ValueError(
                "No image selected."
            )

        safe_folder = self.validate_folder(
            folder
        )

        folder_path = self.folder_path(
            safe_folder
        )

        folder_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_name = self.validate_filename(
            uploaded_file.filename
        )

        destination = (
            folder_path
            / safe_name
        )

        if destination.exists():
            stem = destination.stem
            suffix = destination.suffix
            counter = 1

            while destination.exists():
                destination = (
                    folder_path
                    / f"{stem}_{counter}{suffix}"
                )

                counter += 1

        uploaded_file.save(
            destination
        )

        return (
            destination
            .relative_to(
                self.upload_dir
            )
            .as_posix()
        )

    def delete_file(
        self,
        reference: str,
    ) -> str:
        safe_reference = (
            self.validate_reference(
                reference
            )
        )

        path = self.image_path(
            safe_reference
        )

        if not path.exists():
            raise FileNotFoundError(
                "Uploaded image not found: "
                f"{safe_reference}"
            )

        if not path.is_file():
            raise ValueError(
                "Upload reference is not a file."
            )

        path.unlink()

        return safe_reference

    def delete_folder(
        self,
        folder: str,
    ) -> str:
        safe_folder = self.validate_folder(
            folder
        )

        if not safe_folder:
            raise RuntimeError(
                "Cannot delete the root "
                "uploads folder."
            )

        folder_path = self.folder_path(
            safe_folder
        )

        if not folder_path.exists():
            raise FileNotFoundError(
                f"Folder not found: "
                f"{safe_folder}"
            )

        if not folder_path.is_dir():
            raise RuntimeError(
                "That path is not a folder."
            )

        if any(
            folder_path.iterdir()
        ):
            raise RuntimeError(
                "Folder is not empty."
            )

        folder_path.rmdir()

        return safe_folder

    @staticmethod
    def close_files(
        files: list[discord.File],
    ) -> None:
        for file in files:
            try:
                file.close()

            except Exception:
                pass