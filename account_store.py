"""SQLite storage for validated Smart Diary accounts."""

import sqlite3
import json
from contextlib import contextmanager
from pathlib import Path

import bcrypt

from input_validation import password_format as password_format_check
from input_validation import username_format as username_format_check
from input_validation import email_format as email_format_check
from data_encryption import decrypt_text, email_lookup_digest, encrypt_text


DEFAULT_DATABASE = Path(__file__).with_name("accounts.db")


class AccountStore:
    """Create accounts and verify credentials without storing plaintext passwords."""

    def __init__(self, database_path=DEFAULT_DATABASE):
        self.database_path = str(database_path)
        migrated_sensitive_data = False
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT,
                    email_encrypted BLOB,
                    email_lookup_hash TEXT,
                    password_hash BLOB NOT NULL
                )
                """
            )
            account_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
            }
            if "email" not in account_columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN email TEXT")
            if "email_encrypted" not in account_columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN email_encrypted BLOB")
            if "email_lookup_hash" not in account_columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN email_lookup_hash TEXT")
            connection.execute("DROP INDEX IF EXISTS accounts_email_unique")
            legacy_accounts = connection.execute(
                "SELECT id, email FROM accounts WHERE email IS NOT NULL"
            ).fetchall()
            migrated_sensitive_data = bool(legacy_accounts)
            for account in legacy_accounts:
                plain_email = account["email"]
                connection.execute(
                    "UPDATE accounts SET email_encrypted = ?, email_lookup_hash = ?, email = NULL "
                    "WHERE id = ?",
                    (encrypt_text(plain_email), email_lookup_digest(plain_email), account["id"]),
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS accounts_email_lookup_unique "
                "ON accounts(email_lookup_hash) WHERE email_lookup_hash IS NOT NULL"
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
                    source_id TEXT,
                    encrypted_payload BLOB,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )
            entry_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(diary_entries)")
            }
            if "source_id" not in entry_columns:
                connection.execute("ALTER TABLE diary_entries ADD COLUMN source_id TEXT")
            if "encrypted_payload" not in entry_columns:
                connection.execute("ALTER TABLE diary_entries ADD COLUMN encrypted_payload BLOB")
            connection.execute("PRAGMA secure_delete = ON")
            legacy_entries = connection.execute(
                "SELECT id, date, title, mood, body, tags_json FROM diary_entries "
                "WHERE encrypted_payload IS NULL"
            ).fetchall()
            migrated_sensitive_data = migrated_sensitive_data or bool(legacy_entries)
            for entry in legacy_entries:
                payload = json.dumps({
                    "date": entry["date"],
                    "title": entry["title"],
                    "mood": entry["mood"],
                    "text": entry["body"],
                    "tags": json.loads(entry["tags_json"]),
                })
                connection.execute(
                    "UPDATE diary_entries SET date = '[encrypted]', title = '[encrypted]', "
                    "mood = '[encrypted]', body = '[encrypted]', tags_json = '[]', "
                    "encrypted_payload = ? WHERE id = ?",
                    (encrypt_text(payload), entry["id"]),
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS diary_entries_account_source "
                "ON diary_entries(account_id, source_id) WHERE source_id IS NOT NULL"
            )
        if migrated_sensitive_data:
            with self._connect() as connection:
                connection.execute("VACUUM")

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA secure_delete = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_account(self, username, password, email):
        """Validate account details and save the email and bcrypt password hash."""
        if not username_format_check(username):
            raise ValueError("Username must be 3–32 letters, numbers, or underscores.")
        if not password_format_check(password):
            raise ValueError(
                "Password must be longer than 8 characters and contain uppercase, "
                "lowercase, a number, and punctuation."
            )
        if not email_format_check(email):
            raise ValueError("Enter a valid email address.")

        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO accounts (username, email, email_encrypted, email_lookup_hash, password_hash) "
                    "VALUES (?, NULL, ?, ?, ?)",
                    (username, encrypt_text(email), email_lookup_digest(email), password_hash),
                )
                return cursor.lastrowid
        except sqlite3.IntegrityError as error:
            raise ValueError("That username or email is already registered.") from error

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

    def change_password(self, account_id, current_password, new_password):
        """Replace an account password after verifying the current password."""
        if not password_format_check(new_password):
            raise ValueError(
                "New password must be longer than 8 characters and contain uppercase, "
                "lowercase, a number, and punctuation."
            )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            if row is None or not password_format_check(current_password):
                return False
            if not bcrypt.checkpw(current_password.encode("utf-8"), row["password_hash"]):
                return False
            if current_password == new_password:
                raise ValueError("New password must be different from your current password.")
            new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
            connection.execute(
                "UPDATE accounts SET password_hash = ? WHERE id = ?",
                (new_hash, account_id),
            )
        return True

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
                "SELECT id, date, title, mood, body, tags_json, encrypted_payload FROM diary_entries "
                "WHERE account_id = ? ORDER BY id DESC",
                (account_id,),
            ).fetchall()
        entries = []
        for row in rows:
            payload = json.loads(decrypt_text(row["encrypted_payload"]))
            entries.append({"id": row["id"], **payload})
        return entries

    def create_entry(self, account_id, entry):
        date, title, mood, body, tags = self._validated_entry(entry)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO diary_entries "
                "(account_id, date, title, mood, body, tags_json, encrypted_payload) "
                "VALUES (?, '[encrypted]', '[encrypted]', '[encrypted]', '[encrypted]', '[]', ?)",
                (account_id, encrypt_text(json.dumps({
                    "date": date, "title": title, "mood": mood, "text": body, "tags": tags
                }))),
            )
            entry_id = cursor.lastrowid
        return next(item for item in self.list_entries(account_id) if item["id"] == entry_id)

    def import_entries(self, account_id, entries, start_index=0):
        """Import browser entries atomically and ignore retries of the same import."""
        if (
            not isinstance(entries, list)
            or len(entries) > 10000
            or isinstance(start_index, bool)
            or not isinstance(start_index, int)
            or start_index < 0
        ):
            raise ValueError("Guest entry data is invalid or too large to import.")

        validated_entries = []
        for index, entry in enumerate(entries):
            date, title, mood, body, tags = self._validated_entry(entry)
            source_value = entry.get("id")
            if not isinstance(source_value, (str, int)) or len(str(source_value)) > 80:
                raise ValueError("A guest entry is missing its import id.")
            source_id = f"{start_index + index}:{source_value}"
            payload = encrypt_text(json.dumps({
                "date": date, "title": title, "mood": mood, "text": body, "tags": tags
            }))
            validated_entries.append((payload, source_id))

        imported = 0
        with self._connect() as connection:
            for payload, source_id in validated_entries:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO diary_entries "
                    "(account_id, date, title, mood, body, tags_json, source_id, encrypted_payload) "
                    "VALUES (?, '[encrypted]', '[encrypted]', '[encrypted]', '[encrypted]', '[]', ?, ?)",
                    (account_id, source_id, payload),
                )
                imported += cursor.rowcount
        return imported

    def update_entry(self, account_id, entry_id, title, body):
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError("Entry title must be 1–120 characters.")
        if not isinstance(body, str) or len(body) > 10000:
            raise ValueError("Entry text must be 10,000 characters or fewer.")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT encrypted_payload FROM diary_entries WHERE id = ? AND account_id = ?",
                (entry_id, account_id),
            ).fetchone()
            if row is None:
                return False
            payload = json.loads(decrypt_text(row["encrypted_payload"]))
            payload.update({"title": title.strip(), "text": body.strip()})
            cursor = connection.execute(
                "UPDATE diary_entries SET encrypted_payload = ? WHERE id = ? AND account_id = ?",
                (encrypt_text(json.dumps(payload)), entry_id, account_id),
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
