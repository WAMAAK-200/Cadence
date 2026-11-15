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


def email_format(email):
    """Validate a conventional ASCII email address and its DNS-style domain."""
    if not isinstance(email, str) or len(email) > 254 or email != email.strip():
        return False
    if not email.isascii() or email.count("@") != 1:
        return False
    local, domain = email.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
    ):
        return False
    labels = domain.split(".")
    if len(labels) < 2:
        return False
    return all(
        1 <= len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )

