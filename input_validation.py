import re
import string


def password_format(password):
    """Require 9–72 UTF-8 bytes with upper, lower, digit, and punctuation."""
    if not isinstance(password, str) or len(password) <= 8:
        return False
    try:
        if len(password.encode("utf-8")) > 72:
            return False
    except UnicodeEncodeError:
        return False
    return (
        any(char.isupper() for char in password)
        and any(char.islower() for char in password)
        and any(char.isdigit() for char in password)
        and any(char in string.punctuation for char in password)
    )


def username_format(username):
    """Allow 3–32 ASCII letters, digits, or underscores."""
    return isinstance(username, str) and bool(
        re.fullmatch(r"[A-Za-z0-9_]{3,32}", username)
    )

