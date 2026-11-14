"""SQLite storage for validated Smart Diary accounts."""

import sqlite3
import json
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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS diary_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    mood TEXT NOT NULL,
                    body TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
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
        return self.authenticated_account_id(username, password) is not None

    def authenticated_account_id(self, username, password):
        """Return the account id after verifying credentials, or None."""
        if not username_format_check(username) or not password_format_check(password):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, password_hash FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()

        if row is None or not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"]):
            return None
        return row["id"]

    @staticmethod
    def _validated_entry(entry):
        if not isinstance(entry, dict):
            raise ValueError("Entry data is invalid.")
        date = entry.get("date")
        title = entry.get("title")
        mood = entry.get("mood")
        body = entry.get("text")
        tags = entry.get("tags", [])
        if not isinstance(date, str) or not date or len(date) > 40:
            raise ValueError("Entry date is invalid.")
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("Entry title must be 1–120 characters.")
        if not isinstance(mood, str) or len(mood) > 40:
            raise ValueError("Entry mood is invalid.")
        if not isinstance(body, str) or not body.strip() or len(body) > 10000:
            raise ValueError("Entry text must be 1–10,000 characters.")
        if not isinstance(tags, list) or len(tags) > 20 or any(
            not isinstance(tag, str) or len(tag) > 30 for tag in tags
        ):
            raise ValueError("Entries can have up to 20 tags of 30 characters each.")
        return date, title.strip(), mood, body.strip(), tags

    def list_entries(self, account_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, date, title, mood, body, tags_json FROM diary_entries "
                "WHERE account_id = ? ORDER BY id DESC",
                (account_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "date": row["date"],
                "title": row["title"],
                "mood": row["mood"],
                "text": row["body"],
                "tags": json.loads(row["tags_json"]),
            }
            for row in rows
        ]

    def create_entry(self, account_id, entry):
        date, title, mood, body, tags = self._validated_entry(entry)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO diary_entries (account_id, date, title, mood, body, tags_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (account_id, date, title, mood, body, json.dumps(tags)),
            )
            entry_id = cursor.lastrowid
        return next(item for item in self.list_entries(account_id) if item["id"] == entry_id)

    def update_entry(self, account_id, entry_id, title, body):
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("Entry title must be 1–120 characters.")
        if not isinstance(body, str) or len(body) > 10000:
            raise ValueError("Entry text must be 10,000 characters or fewer.")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE diary_entries SET title = ?, body = ? WHERE id = ? AND account_id = ?",
                (title.strip(), body.strip(), entry_id, account_id),
            )
            return cursor.rowcount > 0

    def delete_entry(self, account_id, entry_id):
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM diary_entries WHERE id = ? AND account_id = ?",
                (entry_id, account_id),
            )
            return cursor.rowcount > 0


if __name__ == "__main__":
    store = AccountStore()
    print(f"Account database is ready at {store.database_path}")
