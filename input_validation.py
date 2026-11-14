import re
import string


def password_format(password):
    """Require at least 8 chars with upper, lower, digit, and punctuation."""
    return (
        isinstance(password, str)
        and len(password) >= 8
        and any(char.isupper() for char in password)
        and any(char.islower() for char in password)
        and any(char.isdigit() for char in password)
        and any(char in string.punctuation for char in password)
    )


def username_format(username):
    """Allow 3–32 ASCII letters, digits, or underscores."""
    return isinstance(username, str) and bool(
        re.fullmatch(r"[A-Za-z0-9_]{3,32}", username)
    )

