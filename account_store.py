"""SQLite storage for validated Smart Diary accounts."""

import sqlite3
import json
import hashlib
import hmac
import secrets
from contextlib import contextmanager
from pathlib import Path

try:
    import bcrypt
except ImportError:
    bcrypt = None

from security import password_format_check, username_format_check


DEFAULT_DATABASE = Path(__file__).with_name("accounts.db")


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
                    password_hash BLOB NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'student',
                    settings_json TEXT NOT NULL DEFAULT '{}'
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
                    sleep_hours REAL,
                    sleep_quality TEXT,
                    stress INTEGER,
                    fatigue INTEGER,
                    study_hours REAL,
                    work_hours REAL,
                    extra_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
                )
                """
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
            self._ensure_columns(connection)

    def _ensure_columns(self, connection):
        """Ensure all columns exist on older databases."""
        account_cols = {row[1] for row in connection.execute("PRAGMA table_info(accounts)").fetchall()}
        if "mode" not in account_cols:
            connection.execute("ALTER TABLE accounts ADD COLUMN mode TEXT NOT NULL DEFAULT 'student'")
        if "settings_json" not in account_cols:
            connection.execute("ALTER TABLE accounts ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'")

        entry_cols = {row[1] for row in connection.execute("PRAGMA table_info(diary_entries)").fetchall()}
        if "sleep_hours" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN sleep_hours REAL")
        if "sleep_quality" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN sleep_quality TEXT")
        if "stress" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN stress INTEGER")
        if "fatigue" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN fatigue INTEGER")
        if "study_hours" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN study_hours REAL")
        if "work_hours" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN work_hours REAL")
        if "extra_json" not in entry_cols:
            connection.execute("ALTER TABLE diary_entries ADD COLUMN extra_json TEXT NOT NULL DEFAULT '{}'")

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

    def create_account(self, username, password, mode="student"):
        """Validate credentials and save a bcrypt hash; return the new account id."""
        if not username_format_check(username):
            raise ValueError("Username must be 3–32 letters, numbers, or underscores.")
        if not password_format_check(password):
            raise ValueError(
                "Password must be longer than 8 characters and contain uppercase, "
                "lowercase, a number, and punctuation."
            )
        if mode not in ("student", "employed", "unemployed"):
            mode = "student"

        password_hash = _hash_password(password)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "INSERT INTO accounts (username, password_hash, mode) VALUES (?, ?, ?)",
                    (username, password_hash, mode),
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

        if row is None or not _check_password(password, row["password_hash"]):
            return None
        return row["id"]

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
            if mode and mode in ("student", "employed", "unemployed"):
                connection.execute("UPDATE accounts SET mode = ? WHERE id = ?", (mode, account_id))
            if settings is not None:
                connection.execute(
                    "UPDATE accounts SET settings_json = ? WHERE id = ?",
                    (json.dumps(settings), account_id),
                )
        return self.get_user_profile(account_id)

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

        # Optional telemetry
        sleep_hours = entry.get("sleepHours")
        if sleep_hours is not None:
            try:
                sleep_hours = float(sleep_hours)
                sleep_hours = max(0.0, min(24.0, sleep_hours))
            except (ValueError, TypeError):
                sleep_hours = None

        sleep_quality = entry.get("sleepQuality")
        if sleep_quality not in ("poor", "ok", "good"):
            sleep_quality = None

        stress = entry.get("stress")
        if stress is not None:
            try:
                stress = int(stress)
                stress = max(1, min(10, stress))
            except (ValueError, TypeError):
                stress = None

        fatigue = entry.get("fatigue")
        if fatigue is not None:
            try:
                fatigue = int(fatigue)
                fatigue = max(1, min(10, fatigue))
            except (ValueError, TypeError):
                fatigue = None

        study_hours = entry.get("studyHours")
        if study_hours is not None:
            try:
                study_hours = float(study_hours)
                study_hours = max(0.0, min(24.0, study_hours))
            except (ValueError, TypeError):
                study_hours = None

        work_hours = entry.get("workHours")
        if work_hours is not None:
            try:
                work_hours = float(work_hours)
                work_hours = max(0.0, min(24.0, work_hours))
            except (ValueError, TypeError):
                work_hours = None

        extra = {}
        for key in ("summary", "dialectTerms", "safety", "spokenReply", "mode"):
            if key in entry:
                extra[key] = entry[key]

        return (
            date,
            title.strip(),
            mood,
            body.strip(),
            tags,
            sleep_hours,
            sleep_quality,
            stress,
            fatigue,
            study_hours,
            work_hours,
            extra,
        )

    def list_entries(self, account_id):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, date, title, mood, body, tags_json,
                       sleep_hours, sleep_quality, stress, fatigue,
                       study_hours, work_hours, extra_json
                FROM diary_entries
                WHERE account_id = ? ORDER BY id DESC
                """,
                (account_id,),
            ).fetchall()
        entries = []
        for row in rows:
            try:
                tags = json.loads(row["tags_json"])
            except Exception:
                tags = []
            try:
                extra = json.loads(row["extra_json"])
            except Exception:
                extra = {}
            entry = {
                "id": row["id"],
                "date": row["date"],
                "title": row["title"],
                "mood": row["mood"],
                "text": row["body"],
                "tags": tags,
                "sleepHours": row["sleep_hours"],
                "sleepQuality": row["sleep_quality"],
                "stress": row["stress"],
                "fatigue": row["fatigue"],
                "studyHours": row["study_hours"],
                "workHours": row["work_hours"],
            }
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if k not in entry:
                        entry[k] = v
            entries.append(entry)
        return entries

    def create_entry(self, account_id, entry):
        (
            date,
            title,
            mood,
            body,
            tags,
            sleep_hours,
            sleep_quality,
            stress,
            fatigue,
            study_hours,
            work_hours,
            extra,
        ) = self._validated_entry(entry)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO diary_entries (
                    account_id, date, title, mood, body, tags_json,
                    sleep_hours, sleep_quality, stress, fatigue,
                    study_hours, work_hours, extra_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    date,
                    title,
                    mood,
                    body,
                    json.dumps(tags),
                    sleep_hours,
                    sleep_quality,
                    stress,
                    fatigue,
                    study_hours,
                    work_hours,
                    json.dumps(extra),
                ),
            )
            entry_id = cursor.lastrowid
        return next(item for item in self.list_entries(account_id) if item["id"] == entry_id)

    def update_entry(self, account_id, entry_id, title=None, body=None, **kwargs):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM diary_entries WHERE id = ? AND account_id = ?",
                (entry_id, account_id),
            ).fetchone()
            if not row:
                return False

            new_title = title.strip() if isinstance(title, str) and title.strip() else row["title"]
            new_body = body.strip() if isinstance(body, str) else row["body"]

            if len(new_title) > 120 or len(new_body) > 10000:
                raise ValueError("Title or text exceeds allowed length.")

            cursor = connection.execute(
                "UPDATE diary_entries SET title = ?, body = ? WHERE id = ? AND account_id = ?",
                (new_title, new_body, entry_id, account_id),
            )
            return cursor.rowcount > 0

    def delete_entry(self, account_id, entry_id):
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM diary_entries WHERE id = ? AND account_id = ?",
                (entry_id, account_id),
            )
            return cursor.rowcount > 0

    # ---------- Exam Calendar & Revision Tracker Methods ----------

    def list_exams(self, account_id):
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, subject, date, target_hours, completed_hours, notes FROM exams WHERE account_id = ? ORDER BY date ASC",
                (account_id,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "subject": r["subject"],
                "date": r["date"],
                "targetHours": r["target_hours"],
                "completedHours": r["completed_hours"],
                "notes": r["notes"],
            }
            for r in rows
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
                    UPDATE exams SET subject = ?, date = ?, target_hours = ?, completed_hours = ?, notes = ?
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
