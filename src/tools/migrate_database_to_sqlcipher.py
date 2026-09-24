"""
Copy a plaintext Sanctuary Servo SQLite file into
a new SQLCipher database.

The source is left unchanged. The target
must not already exist. The key is
TFSBOT_DATABASE_KEY (64 hex characters),
and user_version is copied across.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlcipher3 import dbapi2 as sqlcipher


KEY_PATTERN = re.compile(
    r"^[0-9a-fA-F]{64}$"
)


def get_database_key() -> str:
    """
    Load TFSBOT_DATABASE_KEY from the
    environment, including a local .env.

    The key must be exactly 64 hexadecimal
    characters, matching the bot's opener.
    """
    load_dotenv()

    key = os.getenv(
        "TFSBOT_DATABASE_KEY",
        "",
    ).strip()

    if not KEY_PATTERN.fullmatch(key):
        raise RuntimeError(
            "TFSBOT_DATABASE_KEY must be exactly "
            "64 hexadecimal characters."
        )

    return key


def quote_identifier(
    value: str,
) -> str:
    """
    Quote a SQLite identifier, doubling any
    embedded double quotes.
    """
    return (
        '"'
        + value.replace('"', '""')
        + '"'
    )


def get_tables(
    database: sqlcipher.Connection,
    schema: str = "main",
) -> list[str]:
    """
    List user tables in name order.

    sqlite_ internal tables are excluded so
    they are not part of the row-count check.
    """
    rows = database.execute(
        f"""
        SELECT name
        FROM {schema}.sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()

    return [
        str(row[0])
        for row in rows
    ]


def get_row_counts(
    database: sqlcipher.Connection,
    tables: list[str],
    schema: str = "main",
) -> dict[str, int]:
    """
    Count rows per table, using quoted
    identifiers so odd names stay valid SQL.
    """
    counts: dict[str, int] = {}

    for table in tables:
        identifier = quote_identifier(
            table
        )

        row = database.execute(
            f"""
            SELECT COUNT(*)
            FROM {schema}.{identifier}
            """
        ).fetchone()

        counts[table] = int(
            row[0]
        )

    return counts


def verify_integrity(
    database: sqlcipher.Connection,
) -> None:
    """
    Require PRAGMA integrity_check to return
    a single ok row.
    """
    result = database.execute(
        "PRAGMA integrity_check;"
    ).fetchone()

    if (
        result is None
        or result[0] != "ok"
    ):
        raise RuntimeError(
            "Database integrity check failed: "
            f"{result!r}"
        )


def migrate_database(
    source_path: Path,
    target_path: Path,
    key: str,
) -> None:
    """
    Export source into a new encrypted file
    and check the copy.

    sqlcipher_export runs through an ATTACH
    on the plaintext connection. user_version
    is applied on the encrypted schema after
    that export, then checked again when the
    file is reopened, along with integrity,
    the table list, and the row counts. The
    plaintext file is not deleted.
    """
    if not source_path.exists():
        raise FileNotFoundError(
            f"Source database does not exist: "
            f"{source_path}"
        )

    if target_path.exists():
        raise FileExistsError(
            f"Target database already exists: "
            f"{target_path}"
        )

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Source: {source_path}"
    )

    print(
        f"Target: {target_path}"
    )

    print()
    print(
        "Opening plaintext source database..."
    )

    source = sqlcipher.connect(
        str(source_path)
    )

    try:
        verify_integrity(
            source
        )

        tables = get_tables(
            source
        )

        source_counts = get_row_counts(
            source,
            tables,
        )

        user_version_row = source.execute(
            "PRAGMA user_version;"
        ).fetchone()

        user_version = int(
            user_version_row[0]
        )

        print(
            f"Found {len(tables)} tables."
        )

        print(
            "Source integrity check: PASS"
        )

        escaped_target = str(
            target_path
        ).replace(
            "'",
            "''",
        )

        print()
        print(
            "Creating encrypted database..."
        )

        source.execute(
            f"""
            ATTACH DATABASE
                '{escaped_target}'
            AS encrypted
            KEY "x'{key}'";
            """
        )

        try:
            source.execute(
                """
                SELECT
                    sqlcipher_export(
                        'encrypted'
                    );
                """
            ).fetchone()

            source.execute(
                f"""
                PRAGMA
                    encrypted.user_version
                    = {user_version};
                """
            )

        finally:
            source.execute(
                """
                DETACH DATABASE encrypted;
                """
            )

    finally:
        source.close()

    print(
        "Export complete."
    )

    print()
    print(
        "Opening encrypted database "
        "with SQLCipher..."
    )

    encrypted = sqlcipher.connect(
        str(target_path)
    )

    try:
        encrypted.execute(
            f"""
            PRAGMA key =
                "x'{key}'";
            """
        )

        # Force SQLCipher to actually read
        # the encrypted database immediately.
        encrypted.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master;
            """
        ).fetchone()

        verify_integrity(
            encrypted
        )

        encrypted_tables = get_tables(
            encrypted
        )

        encrypted_counts = get_row_counts(
            encrypted,
            encrypted_tables,
        )

        if tables != encrypted_tables:
            raise RuntimeError(
                "Table list differs between "
                "plaintext and encrypted databases."
            )

        if source_counts != encrypted_counts:
            raise RuntimeError(
                "Row counts differ between "
                "plaintext and encrypted databases."
            )

        encrypted_user_version = int(
            encrypted.execute(
                "PRAGMA user_version;"
            ).fetchone()[0]
        )

        if (
            encrypted_user_version
            != user_version
        ):
            raise RuntimeError(
                "user_version was not preserved."
            )

        cipher_version = encrypted.execute(
            "PRAGMA cipher_version;"
        ).fetchone()

        print(
            "Encrypted integrity check: PASS"
        )

        print(
            "Table verification: PASS"
        )

        print(
            "Row-count verification: PASS"
        )

        print(
            "user_version verification: PASS"
        )

        print(
            "SQLCipher:",
            cipher_version,
        )

    finally:
        encrypted.close()

    print()
    print(
        "Migration successful."
    )

    print()
    print(
        "IMPORTANT: the original plaintext "
        "database has NOT been deleted or changed."
    )


def main() -> None:
    """
    Parse source and target paths, refuse
    identical paths, and run the export.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Create an encrypted SQLCipher copy "
            "of a plaintext Sanctuary Servo database."
        )
    )

    parser.add_argument(
        "source",
        type=Path,
        help=(
            "Path to the existing plaintext "
            "SQLite database."
        ),
    )

    parser.add_argument(
        "target",
        type=Path,
        help=(
            "Path for the new encrypted "
            "SQLCipher database."
        ),
    )

    arguments = parser.parse_args()

    source_path = (
        arguments.source.resolve()
    )

    target_path = (
        arguments.target.resolve()
    )

    if source_path == target_path:
        raise RuntimeError(
            "Source and target paths "
            "must be different."
        )

    key = get_database_key()

    migrate_database(
        source_path,
        target_path,
        key,
    )


if __name__ == "__main__":
    main()