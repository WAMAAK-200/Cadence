import sqlite3
import re
import string

def username_format(username):
    """Return True when a username is 3–32 letters, digits, or underscores."""
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,32}", username))

def password_format(passwd):
    """Require 8+ characters with upper, lower, digit, and punctuation."""
    return (
        isinstance(passwd, str)
        and len(passwd) > 8
        and any(char.isupper() for char in passwd)
        and any(char.islower() for char in passwd)
        and any(char.isdigit() for char in passwd)
        and any(char in string.punctuation for char in passwd)
    )

