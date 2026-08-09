from __future__ import annotations

import base64
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


BACKUP_MAGIC = b"TFSBOT_BACKUP_V1\n"
BACKUP_EXTENSION = ".tfsbackup"


class BackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupResult:
    filename: str
    data: bytes


@dataclass(frozen=True)
class RestoreResult:
    restored_database: bool
    restored_uploads: bool
    restored_env: bool
    safety_backup_directory: Path


class BackupService:
    def __init__(
        self,
        project_root: str | Path = ".",
        database_path: str | Path = "data/tfsbot.sqlite3",
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.database_path = Path(database_path)

        if not self.database_path.is_absolute():
            self.database_path = self.project_root / self.database_path

    def create_encrypted_backup(
        self,
        password: str,
        include_env: bool = False,
    ) -> BackupResult:
        password = password.strip()

        if len(password) < 10:
            raise BackupError("Backup password must be at least 10 characters long.")

        archive_bytes = self._create_plain_archive(include_env=include_env)
        encrypted_bytes = self._encrypt_bytes(
            data=archive_bytes,
            password=password,
        )

        created_at = datetime.now(timezone.utc)

        filename = (
            f"TFSBot_Backup_"
            f"{created_at.strftime('%Y-%m-%d_%H%M%S')}"
            f"{BACKUP_EXTENSION}"
        )

        return BackupResult(
            filename=filename,
            data=encrypted_bytes,
        )

    def restore_encrypted_backup(
        self,
        encrypted_data: bytes,
        password: str,
        restore_uploads: bool = True,
        restore_env: bool = False,
    ) -> RestoreResult:
        plain_archive = self.decrypt_backup(
            encrypted_data=encrypted_data,
            password=password,
        )

        restore_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        safety_backup_directory = (
            self.project_root / "data" / "restore_safety" / restore_timestamp
        )

        safety_backup_directory.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(BytesIO(plain_archive), mode="r") as archive:
            self._validate_archive(archive)
            members = set(archive.namelist())

            if "data/tfsbot.sqlite3" not in members:
                raise BackupError("Backup does not contain data/tfsbot.sqlite3.")

            restored_database = False
            restored_uploads = False
            restored_env = False

            database_target = self.database_path
            database_target.parent.mkdir(parents=True, exist_ok=True)

            if database_target.exists():
                database_safety_path = (
                    safety_backup_directory / "data" / "tfsbot.sqlite3"
                )
                database_safety_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy2(
                    database_target,
                    database_safety_path,
                )

            database_temp_path = database_target.with_suffix(".sqlite3.restore_tmp")

            with archive.open("data/tfsbot.sqlite3", mode="r") as source:
                with database_temp_path.open("wb") as target:
                    shutil.copyfileobj(source, target)

            database_temp_path.replace(database_target)
            restored_database = True

            uploads_target = self.project_root / "data" / "uploads"
            upload_members = [
                member
                for member in members
                if member.startswith("data/uploads/") and not member.endswith("/")
            ]

            if restore_uploads and upload_members:
                uploads_safety_path = safety_backup_directory / "data" / "uploads"

                if uploads_target.exists():
                    uploads_safety_path.parent.mkdir(parents=True, exist_ok=True)

                    shutil.copytree(
                        uploads_target,
                        uploads_safety_path,
                        dirs_exist_ok=True,
                    )

                    shutil.rmtree(uploads_target)

                uploads_target.mkdir(parents=True, exist_ok=True)

                for member in upload_members:
                    relative_path = Path(member).relative_to("data/uploads")
                    target_path = uploads_target / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    with archive.open(member, mode="r") as source:
                        with target_path.open("wb") as target:
                            shutil.copyfileobj(source, target)

                restored_uploads = True

            if restore_env:
                if ".env" not in members:
                    raise BackupError(
                        "Restore .env was requested, but this backup does not contain .env."
                    )

                env_target = self.project_root / ".env"

                if env_target.exists():
                    env_safety_path = safety_backup_directory / ".env"
                    shutil.copy2(
                        env_target,
                        env_safety_path,
                    )

                with archive.open(".env", mode="r") as source:
                    with env_target.open("wb") as target:
                        shutil.copyfileobj(source, target)

                restored_env = True

        return RestoreResult(
            restored_database=restored_database,
            restored_uploads=restored_uploads,
            restored_env=restored_env,
            safety_backup_directory=safety_backup_directory,
        )

    def decrypt_backup(
        self,
        encrypted_data: bytes,
        password: str,
    ) -> bytes:
        password = password.strip()

        if not encrypted_data.startswith(BACKUP_MAGIC):
            raise BackupError("This is not a valid TFSBot backup file.")

        remaining = encrypted_data[len(BACKUP_MAGIC):]

        try:
            salt_b64, token = remaining.split(b"\n", 1)
            salt = base64.urlsafe_b64decode(salt_b64)

        except ValueError as error:
            raise BackupError("Backup file header is damaged.") from error

        key = self._derive_key(
            password=password,
            salt=salt,
        )

        fernet = Fernet(key)

        try:
            return fernet.decrypt(token)

        except InvalidToken as error:
            raise BackupError("Incorrect password or damaged backup file.") from error

    def _create_plain_archive(
        self,
        include_env: bool,
    ) -> bytes:
        if not self.database_path.exists():
            raise BackupError(f"Database not found: {self.database_path}")

        created_at = datetime.now(timezone.utc)

        manifest = {
            "format": "tfsbot-backup",
            "version": 1,
            "created_at": created_at.isoformat(),
            "database": "data/tfsbot.sqlite3",
            "includes_uploads": True,
            "includes_env": include_env,
            "notes": (
                "This archive is encrypted as a .tfsbackup file. "
                "Keep the password safe. Without it, the backup cannot be restored."
            ),
        }

        archive_buffer = BytesIO()

        with zipfile.ZipFile(
            archive_buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=4),
            )

            archive.writestr(
                "README_RESTORE.txt",
                self._build_restore_readme(include_env=include_env),
            )

            archive.write(
                self.database_path,
                "data/tfsbot.sqlite3",
            )

            uploads_path = self.project_root / "data" / "uploads"

            if uploads_path.exists():
                self._write_directory_to_archive(
                    archive=archive,
                    source_directory=uploads_path,
                    archive_prefix="data/uploads",
                )

            if include_env:
                env_path = self.project_root / ".env"

                if env_path.exists():
                    archive.write(
                        env_path,
                        ".env",
                    )

        return archive_buffer.getvalue()

    def _write_directory_to_archive(
        self,
        archive: zipfile.ZipFile,
        source_directory: Path,
        archive_prefix: str,
    ) -> None:
        for path in source_directory.rglob("*"):
            if not path.is_file():
                continue

            relative_path = path.relative_to(source_directory)
            archive_path = Path(archive_prefix) / relative_path

            archive.write(
                path,
                archive_path.as_posix(),
            )

    def _validate_archive(
        self,
        archive: zipfile.ZipFile,
    ) -> None:
        for member in archive.namelist():
            member_path = Path(member)

            if member_path.is_absolute():
                raise BackupError(f"Unsafe backup path: {member}")

            if ".." in member_path.parts:
                raise BackupError(f"Unsafe backup path: {member}")

        if "manifest.json" not in archive.namelist():
            raise BackupError("Backup is missing manifest.json.")

        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except Exception as error:
            raise BackupError("Backup manifest is damaged.") from error

        if manifest.get("format") != "tfsbot-backup":
            raise BackupError("Backup manifest has an invalid format.")

        if int(manifest.get("version", 0)) != 1:
            raise BackupError("Backup version is not supported.")

    def _encrypt_bytes(
        self,
        data: bytes,
        password: str,
    ) -> bytes:
        salt = os.urandom(16)

        key = self._derive_key(
            password=password,
            salt=salt,
        )

        fernet = Fernet(key)
        token = fernet.encrypt(data)

        return BACKUP_MAGIC + base64.urlsafe_b64encode(salt) + b"\n" + token

    def _derive_key(
        self,
        password: str,
        salt: bytes,
    ) -> bytes:
        kdf = Scrypt(
            salt=salt,
            length=32,
            n=2**14,
            r=8,
            p=1,
        )

        return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

    def _build_restore_readme(
        self,
        include_env: bool,
    ) -> str:
        if include_env:
            env_note = (
                "This backup includes .env.\n"
                "That means it may include the Discord bot token.\n"
            )
        else:
            env_note = (
                "This backup does not include .env.\n"
                "You will need to recreate .env manually or copy it from the VPS.\n"
            )

        return f"""TFSBot Backup

This .tfsbackup file is encrypted.
You need the backup password to decrypt it.

Contents:
- data/tfsbot.sqlite3
- data/uploads/
- manifest.json
- README_RESTORE.txt

{env_note}
Basic restore idea:
1. Stop the bot.
2. Decrypt the backup using the WebUI restore tool or restore script.
3. Replace data/tfsbot.sqlite3.
4. Replace data/uploads/ if included.
5. Restore .env if included, or recreate it manually.
6. Start the bot again.

Do not delete the database unless you have a confirmed working backup.
Computers already cause enough suffering.
"""
