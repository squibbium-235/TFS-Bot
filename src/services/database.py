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
    key = os.getenv(
        "TFSBOT_DATABASE_KEY",
        "",
    ).strip()

    if not _DATABASE_KEY_PATTERN.fullmatch(
        key
    ):
        raise RuntimeError(
            "TFSBOT_DATABASE_KEY must be "
            "exactly 64 hexadecimal characters."
        )

    return key


def _prepare_database_path(
    database_path: DatabasePath,
) -> Path:
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
    Open an asynchronous encrypted TFSBot
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


@contextmanager
def open_sync_database(
    database_path: DatabasePath,
) -> Iterator[
    SyncDatabaseConnection
]:
    """
    Open a synchronous encrypted TFSBot
    database connection.
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