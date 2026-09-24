"""
Smoke test that SQLCipher encryption is on.

Writes a throwaway database under data/,
checks that stdlib sqlite3 cannot read it,
then reads it back with SQLCipher and the
hardcoded test key. That key is not the
production database key.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlcipher3 import dbapi2 as sqlcipher


DATABASE_PATH = Path(
    "data/sqlcipher-smoke-test.db"
)

TEST_KEY_HEX = (
    "0123456789abcdef"
    "0123456789abcdef"
    "0123456789abcdef"
    "0123456789abcdef"
)


def apply_key(
    database: sqlcipher.Connection,
) -> None:
    """
    Set the smoke-test key. SQLCipher must
    see it before the first read, or the
    file looks corrupt.
    """
    database.execute(
        f'PRAGMA key = "x\'{TEST_KEY_HEX}\'";'
    )


def main() -> None:
    """
    Create the smoke-test file, prove
    ordinary SQLite cannot query it, then
    prove SQLCipher can.

    Any previous file at the same path is
    removed first.
    """
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    DATABASE_PATH.unlink(
        missing_ok=True,
    )

    print("Creating encrypted database...")

    database = sqlcipher.connect(
        str(DATABASE_PATH)
    )

    apply_key(database)

    cipher_version = database.execute(
        "PRAGMA cipher_version;"
    ).fetchone()

    print(
        "SQLCipher version:",
        cipher_version,
    )

    database.execute(
        """
        CREATE TABLE smoke_test (
            value TEXT NOT NULL
        )
        """
    )

    database.execute(
        """
        INSERT INTO smoke_test (
            value
        )
        VALUES (?)
        """,
        ("TFSBot encryption works",),
    )

    database.commit()
    database.close()

    print(
        "Encrypted database created."
    )

    print(
        "Trying standard sqlite3..."
    )

    # A successful read here means the file was not encrypted.
    try:
        plain_database = sqlite3.connect(
            str(DATABASE_PATH)
        )

        plain_database.execute(
            "SELECT * FROM smoke_test"
        ).fetchall()

    except sqlite3.DatabaseError as error:
        print(
            "PASS: ordinary SQLite cannot read it:"
        )
        print(
            f"  {error}"
        )

    else:
        plain_database.close()

        raise RuntimeError(
            "FAIL: ordinary SQLite could read "
            "the supposedly encrypted database."
        )

    print(
        "Trying SQLCipher with correct key..."
    )

    encrypted_database = sqlcipher.connect(
        str(DATABASE_PATH)
    )

    apply_key(
        encrypted_database
    )

    row = encrypted_database.execute(
        """
        SELECT value
        FROM smoke_test
        """
    ).fetchone()

    encrypted_database.close()

    if row != (
        "TFSBot encryption works",
    ):
        raise RuntimeError(
            "FAIL: encrypted database returned "
            "unexpected data."
        )

    print(
        "PASS: SQLCipher read the database."
    )

    print()
    print(
        "SQLCipher smoke test successful."
    )


if __name__ == "__main__":
    main()