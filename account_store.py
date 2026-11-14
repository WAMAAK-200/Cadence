"""SQLite storage for validated Smart Diary accounts."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import bcrypt

from security import password_format_check, username_format_check


DEFAULT_DATABASE = Path(__file__).with_name("accounts.db")


class AccountStore:
    """Create accounts and verify credentials without storing plaintext passwords."""

    def __init__(self, database_path=DEFAULT_DATABASE):
        self.database_path = str(database_path)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash BLOB NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_account(self, username, password):
        """Validate credentials and save a bcrypt hash; return the new account id."""
        if not username_format_check(username):
            raise ValueError("Username must be 3–32 letters, numbers, or underscores.")
        if not password_format_check(password):
            raise ValueError(
                "Password must be longer than 8 characters and contain uppercase, "
                "lowercase, a number, and punctuation."
            )

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise ValueError("That username is already registered.") from error

    def verify_account(self, username, password):
        """Return True when the username exists and its password matches."""
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()

        if row is None:
            return False
        return bcrypt.checkpw(password.encode("utf-8"), row["password_hash"])


if __name__ == "__main__":
    store = AccountStore()
    print(f"Account database is ready at {store.database_path}")
