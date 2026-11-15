"""SQLite storage for validated Smart Diary accounts.

Sensitive account and diary data is encrypted at rest (see data_encryption.py).
The plaintext diary columns are kept only for compatibility with older
databases; new rows store "[encrypted]" placeholders and the real data in
``encrypted_payload``.
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

try:
    import bcrypt
except ImportError:  # pragma: no cover - requirements.txt installs bcrypt
    bcrypt = None

from data_encryption import email_lookup_digest, encrypt_text, decrypt_text
from input_validation import email_format as email_format_check
from input_validation import password_format as password_format_check
from input_validation import username_format as username_format_check


DEFAULT_DATABASE = Path(__file__).with_name("accounts.db")
VALID_MODES = ("student", "employed", "unemployed")
# Fields that are not part of the core account/diary contract but are useful to
# the UI and the AI layer. They travel inside the encrypted entry payload.
EXTRA_ENTRY_FIELDS = ("summary", "dialectTerms", "safety", "spokenReply", "mode")


def _hash_password(password: str) -> bytes:
    if bcrypt is not None:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return b"pbkdf2$" + salt.hex().encode("ascii") + b"$" + key.hex().encode("ascii")


def _check_password(password: str, stored_hash: bytes) -> bool:
    if isinstance(stored_hash, str):
        stored_hash = stored_hash.encode("utf-8")
    if stored_hash.startswith(b"pbkdf2$"):
        parts = stored_hash.split(b"$")
        if len(parts) == 3:
            salt = bytes.fromhex(parts[1].decode("ascii"))
            expected_key = bytes.fromhex(parts[2].decode("ascii"))
            computed_key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
            return hmac.compare_digest(computed_key, expected_key)
    if bcrypt is not None:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), stored_hash)
        except Exception:
            return False
    return False


def _number(value, cast, low, high):
    if value is None or value == "":
        return None
    try:
        return max(low, min(high, cast(value)))
    except (ValueError, TypeError):
        return None


class AccountStore:
    """Create accounts and verify credentials without storing plaintext secrets."""

    def __init__(self, database_path=DEFAULT_DATABASE):
        self.database_path = str(database_path)
        migrated_sensitive_data = False
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash BLOB NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'student',
                    settings_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            self._ensure_account_columns(connection)
            connection.execute("DROP INDEX IF EXISTS accounts_email_unique")
            legacy_accounts = connection.execute(
                "SELECT id, email FROM accounts WHERE email IS NOT NULL"
            ).fetchall()
            migrated_sensitive_data = migrated_sensitive_data or bool(legacy_accounts)
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
                    sleep_hours REAL,
                    sleep_quality TEXT,
                    stress INTEGER,
                    fatigue INTEGER,
                    study_hours REAL,
                    work_hours REAL,
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    source_id TEXT,
                    encrypted_payload BLOB,
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_entry_columns(connection)
            legacy_entries = connection.execute(
                "SELECT * FROM diary_entries WHERE encrypted_payload IS NULL"
            ).fetchall()
            migrated_sensitive_data = migrated_sensitive_data or bool(legacy_entries)
            for entry in legacy_entries:
                # Leave rows that were half-migrated by an older build alone: the
                # original data no longer exists and re-encrypting placeholders
                # would make the loss look like a successful migration.
                if entry["body"] == "[encrypted]":
                    continue
                payload = self._entry_from_legacy_row(entry)
                connection.execute(
                    "UPDATE diary_entries SET date = '[encrypted]', title = '[encrypted]', "
                    "mood = '[encrypted]', body = '[encrypted]', tags_json = '[]', "
                    "sleep_hours = NULL, sleep_quality = NULL, stress = NULL, "
                    "fatigue = NULL, study_hours = NULL, work_hours = NULL, "
                    "extra_json = '{}', encrypted_payload = ? WHERE id = ?",
                    (encrypt_text(json.dumps(payload)), entry["id"]),
                )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS diary_entries_account_source "
                "ON diary_entries(account_id, source_id) WHERE source_id IS NOT NULL"
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    date TEXT NOT NULL,
                    target_hours REAL NOT NULL DEFAULT 10,
                    completed_hours REAL NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
            )

        if migrated_sensitive_data:
            # Rebuild the database file so freed plaintext pages are overwritten.
            with self._connect() as connection:
                connection.execute("VACUUM")

    @staticmethod
    def _ensure_account_columns(connection):
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)")}
        additions = (
            ("mode", "mode TEXT NOT NULL DEFAULT 'student'"),
            ("settings_json", "settings_json TEXT NOT NULL DEFAULT '{}'"),
            ("email", "email TEXT"),
            ("email_encrypted", "email_encrypted BLOB"),
            ("email_lookup_hash", "email_lookup_hash TEXT"),
        )
        for name, definition in additions:
            if name not in columns:
                connection.execute(f"ALTER TABLE accounts ADD COLUMN {definition}")

    @staticmethod
    def _ensure_entry_columns(connection):
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(diary_entries)")}
        additions = (
            ("sleep_hours", "sleep_hours REAL"),
            ("sleep_quality", "sleep_quality TEXT"),
            ("stress", "stress INTEGER"),
            ("fatigue", "fatigue INTEGER"),
            ("study_hours", "study_hours REAL"),
            ("work_hours", "work_hours REAL"),
            ("extra_json", "extra_json TEXT NOT NULL DEFAULT '{}'"),
            ("source_id", "source_id TEXT"),
            ("encrypted_payload", "encrypted_payload BLOB"),
        )
        for name, definition in additions:
            if name not in columns:
                connection.execute(f"ALTER TABLE diary_entries ADD COLUMN {definition}")

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

    # ---------- Account methods ----------

    def create_account(self, username, password, email=None, mode="student"):
        """Validate account details and save the encrypted email and password hash.

        Email is optional so older clients (and the integration tests) that only
        send a username and password keep working; if present it must be valid.
        """
        if not username_format_check(username):
            raise ValueError("Username must be 3–32 letters, numbers, or underscores.")
        if not password_format_check(password):
            raise ValueError(
                "Password must be longer than 8 characters and contain uppercase, "
                "lowercase, a number, and punctuation."
            )
        if email not in (None, ""):
            if not email_format_check(email):
                raise ValueError("Enter a valid email address.")
        else:
            email = None
        if mode not in VALID_MODES:
            mode = "student"

        password_hash = _hash_password(password)
        encrypted_email = encrypt_text(email) if email else None
        lookup_hash = email_lookup_digest(email) if email else None
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO accounts "
                    "(username, email, email_encrypted, email_lookup_hash, password_hash, mode) "
                    "VALUES (?, NULL, ?, ?, ?, ?)",
                    (username, encrypted_email, lookup_hash, password_hash, mode),
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

        if row is None or not _check_password(password, row["password_hash"]):
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
            if not _check_password(current_password, row["password_hash"]):
                return False
            if current_password == new_password:
                raise ValueError("New password must be different from your current password.")
            connection.execute(
                "UPDATE accounts SET password_hash = ? WHERE id = ?",
                (_hash_password(new_password), account_id),
            )
        return True

    def get_user_profile(self, account_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, username, mode, settings_json FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return None
        try:
            settings = json.loads(row["settings_json"])
        except Exception:
            settings = {}
        return {
            "id": row["id"],
            "username": row["username"],
            "mode": row["mode"] or "student",
            "settings": settings,
        }

    def update_user_profile(self, account_id, mode=None, settings=None):
        with self._connect() as connection:
            if mode and mode in VALID_MODES:
                connection.execute("UPDATE accounts SET mode = ? WHERE id = ?", (mode, account_id))
            if settings is not None:
                connection.execute(
                    "UPDATE accounts SET settings_json = ? WHERE id = ?",
                    (json.dumps(settings), account_id),
                )
        return self.get_user_profile(account_id)

    # ---------- Diary entry methods ----------

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

        sleep_quality = entry.get("sleepQuality")
        if sleep_quality not in ("poor", "ok", "good"):
            sleep_quality = None

        payload = {
            "date": date,
            "title": title.strip(),
            "mood": mood,
            "text": body.strip(),
            "tags": tags,
            "sleepHours": _number(entry.get("sleepHours"), float, 0.0, 24.0),
            "sleepQuality": sleep_quality,
            "stress": _number(entry.get("stress"), int, 1, 10),
            "fatigue": _number(entry.get("fatigue"), int, 1, 10),
            "studyHours": _number(entry.get("studyHours"), float, 0.0, 24.0),
            "workHours": _number(entry.get("workHours"), float, 0.0, 24.0),
        }
        for key in EXTRA_ENTRY_FIELDS:
            if key in entry and entry[key] is not None:
                payload[key] = entry[key]
        return payload

    @staticmethod
    def _entry_from_legacy_row(row):
        """Build the encrypted payload from the pre-encryption plaintext columns."""
        try:
            tags = json.loads(row["tags_json"])
        except Exception:
            tags = []
        try:
            extra = json.loads(row["extra_json"])
        except Exception:
            extra = {}
        payload = {
            "date": row["date"],
            "title": row["title"],
            "mood": row["mood"],
            "text": row["body"],
            "tags": tags if isinstance(tags, list) else [],
            "sleepHours": row["sleep_hours"],
            "sleepQuality": row["sleep_quality"],
            "stress": row["stress"],
            "fatigue": row["fatigue"],
            "studyHours": row["study_hours"],
            "workHours": row["work_hours"],
        }
        if isinstance(extra, dict):
            for key in EXTRA_ENTRY_FIELDS:
                if key in extra:
                    payload[key] = extra[key]
        return payload

    @staticmethod
    def _entry_from_row(row):
        """Return an entry from either the encrypted payload or the legacy columns."""
        raw_payload = row["encrypted_payload"]
        if raw_payload:
            try:
                payload = json.loads(decrypt_text(raw_payload))
            except Exception as error:
                raise RuntimeError(
                    "An encrypted diary entry could not be read. Restore the matching "
                    ".smartdiary.key file before starting the app."
                ) from error
        else:
            payload = AccountStore._entry_from_legacy_row(row)
        if not isinstance(payload, dict):
            raise RuntimeError("A stored diary entry has an unexpected format.")

        entry = {"id": row["id"]}
        entry.update(payload)
        entry.setdefault("tags", [])
        for key in ("sleepHours", "sleepQuality", "stress", "fatigue", "studyHours", "workHours"):
            entry.setdefault(key, None)
        return entry

    def list_entries(self, account_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM diary_entries WHERE account_id = ? ORDER BY id DESC",
                (account_id,),
            ).fetchall()
        return [self._entry_from_row(row) for row in rows]

    def create_entry(self, account_id, entry):
        payload = self._validated_entry(entry)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO diary_entries "
                "(account_id, date, title, mood, body, tags_json, extra_json, encrypted_payload) "
                "VALUES (?, '[encrypted]', '[encrypted]', '[encrypted]', '[encrypted]', '[]', '{}', ?)",
                (account_id, encrypt_text(json.dumps(payload))),
            )
            entry_id = cursor.lastrowid
            row = connection.execute(
                "SELECT * FROM diary_entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._entry_from_row(row)

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
            payload = self._validated_entry(entry)
            source_value = entry.get("id")
            if (
                isinstance(source_value, bool)
                or not isinstance(source_value, (str, int))
                or len(str(source_value)) > 80
            ):
                raise ValueError("A guest entry is missing its import id.")
            source_id = f"{start_index + index}:{source_value}"
            validated_entries.append((encrypt_text(json.dumps(payload)), source_id))

        imported = 0
        with self._connect() as connection:
            for encrypted_payload, source_id in validated_entries:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO diary_entries "
                    "(account_id, date, title, mood, body, tags_json, extra_json, "
                    "source_id, encrypted_payload) "
                    "VALUES (?, '[encrypted]', '[encrypted]', '[encrypted]', "
                    "'[encrypted]', '[]', '{}', ?, ?)",
                    (account_id, source_id, encrypted_payload),
                )
                imported += cursor.rowcount
        return imported

    def update_entry(self, account_id, entry_id, title=None, body=None):
        if title is not None and (
            not isinstance(title, str) or not title.strip() or len(title) > 120
        ):
            raise ValueError("Entry title must be 1–120 characters.")
        if body is not None and (not isinstance(body, str) or len(body) > 10000):
            raise ValueError("Entry text must be 10,000 characters or fewer.")
        if title is None and body is None:
            raise ValueError("No changes were supplied.")

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM diary_entries WHERE id = ? AND account_id = ?",
                (entry_id, account_id),
            ).fetchone()
            if row is None:
                return False
            payload = self._entry_from_row(row)
            payload.pop("id", None)
            if title is not None:
                payload["title"] = title.strip()
            if body is not None:
                payload["text"] = body.strip()
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

    # ---------- Exam calendar & revision tracker ----------

    def list_exams(self, account_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, subject, date, target_hours, completed_hours, notes "
                "FROM exams WHERE account_id = ? ORDER BY date ASC",
                (account_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "subject": row["subject"],
                "date": row["date"],
                "targetHours": row["target_hours"],
                "completedHours": row["completed_hours"],
                "notes": row["notes"],
            }
            for row in rows
        ]

    def save_exam(self, account_id, exam):
        if not isinstance(exam, dict):
            raise ValueError("Invalid exam data.")
        subject = str(exam.get("subject", "")).strip()[:100]
        date_str = str(exam.get("date", "")).strip()[:40]
        if not subject or not date_str:
            raise ValueError("Subject and date are required.")
        target_hours = float(exam.get("targetHours", 10.0))
        completed_hours = float(exam.get("completedHours", 0.0))
        notes = str(exam.get("notes", ""))[:500]

        exam_id = exam.get("id")
        with self._connect() as connection:
            if exam_id:
                connection.execute(
                    """
                    UPDATE exams SET subject = ?, date = ?, target_hours = ?,
                        completed_hours = ?, notes = ?
                    WHERE id = ? AND account_id = ?
                    """,
                    (subject, date_str, target_hours, completed_hours, notes, exam_id, account_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO exams (account_id, subject, date, target_hours, completed_hours, notes)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (account_id, subject, date_str, target_hours, completed_hours, notes),
                )
                exam_id = cursor.lastrowid
        return next((e for e in self.list_exams(account_id) if e["id"] == exam_id), None)

    def delete_exam(self, account_id, exam_id):
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM exams WHERE id = ? AND account_id = ?",
                (exam_id, account_id),
            )
            return cursor.rowcount > 0


if __name__ == "__main__":
    store = AccountStore()
    print(f"Account database is ready at {store.database_path}")
