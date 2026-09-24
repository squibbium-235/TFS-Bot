"""
Shared SQLCipher database used by every Sanctuary Servo store.

TFSBOT_DATABASE_KEY must be 64 hexadecimal characters.
Async stores call open_database, which runs aiosqlite
over a SQLCipher connector. Guild settings use the
synchronous helper. Snapshots are made with SQLCipher
backup(), then checked with both integrity_check and
cipher_integrity_check, because a copied file can look
fine while its cipher pages are wrong.
"""

from __future__ import annotations

import os
import re
from typing import TypeAlias

from collections.abc import (
    AsyncIterator,
    Iterator,
)
from contextlib import (
    asynccontextmanager,
    contextmanager,
)
from pathlib import Path

import aiosqlite

from dotenv import load_dotenv
from sqlcipher3 import dbapi2 as sqlcipher


DatabasePath: TypeAlias = str | Path

AsyncDatabaseConnection: TypeAlias = (
    aiosqlite.Connection
)

SyncDatabaseConnection: TypeAlias = (
    sqlcipher.Connection
)

DatabaseRow: TypeAlias = sqlcipher.Row

DatabaseError = sqlcipher.Error

DatabaseIntegrityError = (
    sqlcipher.IntegrityError
)


_DATABASE_KEY_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)

_PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

load_dotenv(
    _PROJECT_ROOT / ".env"
)


def _get_database_key() -> str:
    """
    Return the SQLCipher key from the environment.

    The value must be exactly 64 hexadecimal
    characters. The project .env file is loaded
    when this module is imported.
    """
    key = os.getenv(
        "TFSBOT_DATABASE_KEY",
        "",
    ).strip()

    if not _DATABASE_KEY_PATTERN.fullmatch(
        key
    ):
        raise RuntimeError(
            "TFSBOT_DATABASE_KEY must be "
            "exactly 64 hexadecimal characters. "
            "Generate one with: python -c "
            '"import secrets; print(secrets.token_hex(32))"'
        )

    return key


def _prepare_database_path(
    database_path: DatabasePath,
) -> Path:
    """
    Return the database path, creating any
    missing parent directories first.
    """
    path = Path(
        database_path
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def _open_sqlcipher_connection(
    database_path: Path,
) -> SyncDatabaseConnection:
    database = sqlcipher.connect(
        str(database_path)
    )

    try:
        key = _get_database_key()

        database.execute(
            f"""
            PRAGMA key =
                "x'{key}'";
            """
        )

        # PRAGMA key itself does not prove that
        # the key is correct. Force SQLCipher to
        # read the database immediately.
        database.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master;
            """
        ).fetchone()

        return database

    except Exception:
        database.close()
        raise


@asynccontextmanager
async def open_database(
    database_path: DatabasePath,
) -> AsyncIterator[
    AsyncDatabaseConnection
]:
    """
    Open an asynchronous encrypted Sanctuary Servo
    database connection.

    SQLCipher performs the actual database
    encryption. aiosqlite provides the async
    wrapper used by the bot's async stores.
    """
    path = _prepare_database_path(
        database_path
    )

    def connector() -> SyncDatabaseConnection:
        return _open_sqlcipher_connection(
            path
        )

    database = aiosqlite.Connection(
        connector,
        iter_chunk_size=64,
    )

    await database

    try:
        yield database
    finally:
        await database.close()

def create_database_snapshot(
    source_path: DatabasePath,
    snapshot_path: DatabasePath,
) -> None:
    """
    Write a consistent encrypted copy of the
    database to snapshot_path.

    SQLCipher backup() copies pages through
    open connections, rather than copying the
    file on disk. The destination is removed
    first so backup starts from an empty
    encrypted database. integrity_check must
    return ok, and cipher_integrity_check must
    return no rows. A failed check leaves the
    new snapshot file in place.
    """
    source = Path(source_path)
    snapshot = Path(snapshot_path)

    if source.resolve() == snapshot.resolve():
        raise ValueError(
            "Database snapshot path must be "
            "different from the source path."
        )

    snapshot.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if snapshot.exists():
        snapshot.unlink()

    source_database = (
        _open_sqlcipher_connection(
            source
        )
    )

    snapshot_database = (
        _open_sqlcipher_connection(
            snapshot
        )
    )

    try:
        source_database.backup(
            snapshot_database
        )

        integrity = (
            snapshot_database.execute(
                "PRAGMA integrity_check;"
            ).fetchone()
        )

        if (
            integrity is None
            or integrity[0] != "ok"
        ):
            raise DatabaseError(
                "Database snapshot failed "
                "integrity check."
            )

        # integrity_check can pass when cipher
        # pages are corrupt. An empty result
        # from this pragma means the snapshot
        # can be decrypted and read.
        cipher_errors = (
            snapshot_database.execute(
                """
                PRAGMA
                    cipher_integrity_check;
                """
            ).fetchall()
        )

        if cipher_errors:
            raise DatabaseError(
                "Database snapshot failed "
                "SQLCipher integrity check."
            )

    finally:
        snapshot_database.close()
        source_database.close()

@contextmanager
def open_sync_database(
    database_path: DatabasePath,
) -> Iterator[
    SyncDatabaseConnection
]:
    """
    Open a synchronous encrypted Sanctuary Servo
    database connection.

    Leaving the block without an error
    commits. An exception rolls the
    transaction back, then the connection
    is closed.
    """
    path = _prepare_database_path(
        database_path
    )

    database = _open_sqlcipher_connection(
        path
    )

    try:
        with database:
            yield database
    finally:
        database.close()