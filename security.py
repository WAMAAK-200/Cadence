import json
import secrets
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from input_validation import password_format as password_format_check
from input_validation import username_format as username_format_check


class AccountHandler(BaseHTTPRequestHandler):
    """Small validation endpoint for the static account page."""

    sessions = {}
    allowed_origins = {"http://127.0.0.1:8000", "http://localhost:8000"}

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, maximum=4096):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > maximum:
            raise OverflowError
        return json.loads(self.rfile.read(length))

    def _authenticated_account_id(self):
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return None
        token = authorization[7:]
        session = self.sessions.get(token)
        if session is None:
            return None
        account_id, expires_at = session
        if time.monotonic() >= expires_at:
            self.sessions.pop(token, None)
            return None
        return account_id

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            self._send_json(200, {"entries": self.server.account_store.list_entries(account_id)})
            return

        files = {
            "/": "user_interface.html",
            "/user_interface.html": "user_interface.html",
            "/entries.html": "entries.html",
            "/calendar.html": "calendar.html",
            "/insights.html": "insights.html",
            "/account.html": "account.html",
            "/sign_up.html": "sign_up.html",
            "/user_style.css": "user_style.css",
            "/entry_storage.js": "entry_storage.js",
        }
        filename = files.get(self.path)
        if filename is None:
            self.send_error(404)
            return
        try:
            body = (Path(__file__).parent / "Update_3" / filename).read_bytes()
        except OSError:
            self.send_error(404)
            return
        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".html": "text/html; charset=utf-8",
        }
        content_type = content_types[Path(filename).suffix]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/logout":
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            self.sessions.pop(token, None)
            self._send_json(200, {"message": "Logged out."})
            return

        if self.path == "/entries/import":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json(6 * 1024 * 1024)
                entries = data.get("entries") if isinstance(data, dict) else None
                imported = self.server.account_store.import_entries(account_id, entries)
            except OverflowError:
                self._send_json(413, {"message": "Guest entries are too large to import in one request."})
                return
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid guest entry data."})
                return
            self._send_json(200, {"imported": imported})
            return

        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json(50000)
                entry = self.server.account_store.create_entry(account_id, data)
            except OverflowError:
                self._send_json(413, {"message": "Entry is too large."})
                return
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid JSON."})
                return
            self._send_json(201, {"entry": entry})
            return

        if self.path not in ("/validate-account", "/signup-account", "/login-account"):
            self.send_error(404)
            return

        try:
            data = self._read_json()
        except OverflowError:
            self._send_json(413, {"message": "Request is too large."})
            return
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
                self.server.account_store.create_account(username, password)
                message = "Account created successfully. You can now log in."
                created = True
            except ValueError as error:
                message = str(error)
        elif self.path == "/login-account":
            account_id = self.server.account_store.authenticated_account_id(username, password) if valid else None
            authenticated = account_id is not None
            session_token = None
            if authenticated:
                session_token = secrets.token_urlsafe(32)
                self.sessions[session_token] = (account_id, time.monotonic() + 8 * 60 * 60)
            message = "Login successful." if authenticated else "Username or password is incorrect."
        elif not valid:
            message = "Use a 3–32 character username (letters, numbers, underscores) and a password longer than 8 characters with uppercase, lowercase, a number, and punctuation."
        else:
            message = "Username and password formats are valid."
        response = {
            "valid": valid,
            "created": created,
            "authenticated": authenticated,
            "message": message,
        }
        if self.path == "/login-account" and authenticated:
            response["session_token"] = session_token
        self._send_json(200, response)

    def do_PUT(self):
        if not self.path.startswith("/entries/"):
            self.send_error(404)
            return
        account_id = self._authenticated_account_id()
        if account_id is None:
            self._send_json(401, {"message": "Please log in again."})
            return
        try:
            entry_id = int(self.path.removeprefix("/entries/"))
            data = self._read_json(50000)
            updated = self.server.account_store.update_entry(
                account_id, entry_id, data.get("title"), data.get("text")
            )
        except OverflowError:
            self._send_json(413, {"message": "Entry is too large."})
            return
        except (ValueError, json.JSONDecodeError, AttributeError):
            self._send_json(400, {"message": "Invalid entry data."})
            return
        if not updated:
            self._send_json(404, {"message": "Entry not found."})
            return
        self._send_json(200, {"message": "Entry updated."})

    def do_DELETE(self):
        if not self.path.startswith("/entries/"):
            self.send_error(404)
            return
        account_id = self._authenticated_account_id()
        if account_id is None:
            self._send_json(401, {"message": "Please log in again."})
            return
        try:
            entry_id = int(self.path.removeprefix("/entries/"))
        except ValueError:
            self._send_json(400, {"message": "Invalid entry id."})
            return
        deleted = self.server.account_store.delete_entry(account_id, entry_id)
        if not deleted:
            self._send_json(404, {"message": "Entry not found."})
            return
        self._send_json(200, {"message": "Entry deleted."})


def create_server(host="127.0.0.1", port=8000, database_path=None):
    """Create the HTTP server and initialize its shared account database."""
    from account_store import AccountStore

    try:
        server = HTTPServer((host, port), AccountHandler)
    except OSError as error:
        if port == 8000:
            raise RuntimeError(
                "Port 8000 is unavailable; stop the process using it before starting Smart Diary."
            ) from error
        raise

    try:
        server.account_store = AccountStore(database_path) if database_path else AccountStore()
    except Exception:
        server.server_close()
        raise
    return server


def main():
    """Initialize the backend and run the Smart Diary web server."""
    server = create_server()
    print(f"Smart Diary account and entry server listening at http://{server.server_address[0]}:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSmart Diary server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

