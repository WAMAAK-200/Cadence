"""Application-level encryption for sensitive fields stored in SQLite."""

import base64
import hashlib
import hmac
import os
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet


KEY_PATH = Path(__file__).with_name(".smartdiary.key")
DATABASE_PATH = Path(__file__).with_name("accounts.db")


def _database_has_encrypted_values():
    if not DATABASE_PATH.exists():
        return False
    try:
        connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            for table, column in (("accounts", "email_encrypted"), ("diary_entries", "encrypted_payload")):
                if table not in tables:
                    continue
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if column in columns and connection.execute(
                    f"SELECT 1 FROM {table} WHERE {column} IS NOT NULL LIMIT 1"
                ).fetchone():
                    return True
            return False
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def _load_or_create_key():
    configured_key = os.environ.get("SMARTDIARY_ENCRYPTION_KEY")
    if configured_key:
        try:
            Fernet(configured_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise RuntimeError("SMARTDIARY_ENCRYPTION_KEY is not a valid Fernet key.") from error
        return configured_key.encode("ascii")

    try:
        key = KEY_PATH.read_bytes().strip()
    except FileNotFoundError:
        if _database_has_encrypted_values():
            raise RuntimeError(
                f"The encryption key {KEY_PATH} is missing; restore it from backup to read the encrypted database."
            )
        key = Fernet.generate_key()
        try:
            descriptor = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            key = KEY_PATH.read_bytes().strip()
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(key + b"\n")

    try:
        Fernet(key)
    except (ValueError, TypeError) as error:
        raise RuntimeError(f"Encryption key in {KEY_PATH} is invalid.") from error
    if KEY_PATH.exists():
        os.chmod(KEY_PATH, 0o600)
    return key


_KEY = _load_or_create_key()
_FERNET = Fernet(_KEY)
_INDEX_KEY = hashlib.sha256(
    b"smartdiary-email-index\0" + base64.urlsafe_b64decode(_KEY)
).digest()


def encrypt_text(value):
    return _FERNET.encrypt(value.encode("utf-8"))


def decrypt_text(value):
    return _FERNET.decrypt(bytes(value)).decode("utf-8")


def email_lookup_digest(email):
    normalized = email.strip().casefold().encode("utf-8")
    return hmac.new(_INDEX_KEY, normalized, hashlib.sha256).hexdigest()
