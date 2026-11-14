import json
import re
import string
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

def username_format_check(username):
    """Return True when a username is 3–32 letters, digits, or underscores."""
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,32}", username))

def password_format_check(password):
    """Require 8+ characters with upper, lower, digit, and punctuation."""
    return (
        isinstance(password, str)
        and len(password) > 8
        and any(char.isupper() for char in password)
        and any(char.islower() for char in password)
        and any(char.isdigit() for char in password)
        and any(char in string.punctuation for char in password)
    )


class AccountHandler(BaseHTTPRequestHandler):
    """Small validation endpoint for the static account page."""

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        files = {
            "/": "account.html",
            "/account.html": "account.html",
            "/sign_up.html": "sign_up.html",
            "/user_style.css": "user_style.css",
        }
        filename = files.get(self.path)
        if filename is None:
            self.send_error(404)
            return
        try:
            body = (Path(__file__).parent / "Update_2" / filename).read_bytes()
        except OSError:
            self.send_error(404)
            return
        content_type = "text/css; charset=utf-8" if filename.endswith(".css") else "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/validate-account", "/signup-account", "/login-account"):
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 4096:
                self.send_error(413)
                return
            data = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return

        username = data.get("username") if isinstance(data, dict) else None
        password = data.get("password") if isinstance(data, dict) else None
        username_valid = isinstance(username, str) and username_format_check(username)
        password_valid = password_format_check(password)
        valid = username_valid and password_valid
        created = False
        authenticated = False

        if self.path == "/signup-account" and valid:
            try:
                from account_store import AccountStore

                AccountStore().create_account(username, password)
                message = "Account created successfully. You can now log in."
                created = True
            except ValueError as error:
                message = str(error)
        elif self.path == "/login-account":
            from account_store import AccountStore

            authenticated = AccountStore().verify_account(username, password)
            message = "Login successful." if authenticated else "Username or password is incorrect."
        elif not valid:
            message = "Use a 3–32 character username (letters, numbers, underscores) and a password longer than 8 characters with uppercase, lowercase, a number, and punctuation."
        else:
            message = "Username and password formats are valid."
        body = json.dumps({
            "valid": valid,
            "created": created,
            "authenticated": authenticated,
            "message": message,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    for port in range(8000, 8011):
        try:
            server = HTTPServer(("127.0.0.1", port), AccountHandler)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No available local port between 8000 and 8010.")

    print(f"Account validation server listening at http://127.0.0.1:{port}")
    server.serve_forever()

