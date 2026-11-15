import json
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

from input_validation import email_format as email_format_check
from input_validation import password_format as password_format_check
from input_validation import username_format as username_format_check

# Make sure ai_backend can be imported when this file is run directly.
PROJECT_ROOT = Path(__file__).parent.resolve()
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from ai_backend import core
    from ai_backend.schemas import (
        DailyPromptRequest,
        EntrySnapshot,
        InsightsRequest,
        WeeklyFeatures,
        WeeklySummaryRequest,
    )
except ImportError:
    core = None


class AccountHandler(BaseHTTPRequestHandler):
    """Unified HTTP server handling the Smart Diary UI and API endpoints."""

    sessions = {}
    allowed_origins = {"http://127.0.0.1:8000", "http://localhost:8000"}

    # ---------- Small helpers ----------

    def _cors_headers(self):
        origin = self.headers.get("Origin")
        if origin in self.allowed_origins or not origin:
            self.send_header("Access-Control-Allow-Origin", origin or "*")
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def _send_json(self, status, payload):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self, maximum=65536):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > maximum:
            raise OverflowError
        data = self.rfile.read(length)
        if not data:
            return {}
        return json.loads(data.decode("utf-8"))

    def _account_store(self):
        """Return the server's shared store, creating it for bare test servers."""
        store = getattr(self.server, "account_store", None)
        if store is None:
            from account_store import AccountStore

            store = AccountStore()
            self.server.account_store = store
        return store

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

    def _entry_id(self, prefix):
        try:
            return int(self.path.removeprefix(prefix))
        except ValueError:
            return None

    # ---------- HTTP verbs ----------

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"status": "ok"})
            return

        if self.path == "/api/status":
            ai_mode = core.ai_mode() if core else "offline"
            self._send_json(200, {
                "status": "ok",
                "app": "Smart Diary (Cadence)",
                "aiMode": ai_mode,
                "offline": ai_mode == "offline",
                "version": "1.0.0",
            })
            return

        if self.path == "/user-profile":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            profile = self._account_store().get_user_profile(account_id)
            if not profile:
                self._send_json(404, {"message": "Profile not found."})
                return
            self._send_json(200, {"profile": profile})
            return

        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            self._send_json(200, {"entries": self._account_store().list_entries(account_id)})
            return

        if self.path == "/exams":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            self._send_json(200, {"exams": self._account_store().list_exams(account_id)})
            return

        self._serve_static_file()

    def _serve_static_file(self):
        clean_path = unquote(self.path.split("?", 1)[0]).lstrip("/")
        if clean_path in ("", "index.html"):
            clean_path = "user_interface.html"
        if ".." in Path(clean_path).parts:
            self.send_error(404)
            return

        # Only the frontend directory is published. This keeps the database,
        # encryption key, and Python sources out of the static file route.
        target_file = FRONTEND_ROOT / clean_path
        if not target_file.is_file():
            self.send_error(404)
            return

        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".txt": "text/plain; charset=utf-8",
        }
        content_type = content_types.get(target_file.suffix, "application/octet-stream")

        try:
            body = target_file.read_bytes()
        except OSError:
            self.send_error(500)
            return

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
                offset = data.get("offset", 0) if isinstance(data, dict) else 0
                imported = self._account_store().import_entries(account_id, entries, offset)
            except OverflowError:
                self._send_json(413, {"message": "Guest entries are too large to import in one request."})
                return
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid guest entry data."})
                return
            self._send_json(200, {"imported": imported})
            return

        if self.path == "/user-profile":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json()
                profile = self._account_store().update_user_profile(
                    account_id,
                    mode=data.get("mode"),
                    settings=data.get("settings"),
                )
                self._send_json(200, {"profile": profile})
            except Exception as error:
                self._send_json(400, {"message": str(error)})
            return

        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json(65536)
                entry = self._account_store().create_entry(account_id, data)
                self._send_json(201, {"entry": entry})
            except OverflowError:
                self._send_json(413, {"message": "Entry is too large."})
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid JSON."})
            return

        if self.path == "/exams":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json()
                exam = self._account_store().save_exam(account_id, data)
                self._send_json(200, {"exam": exam})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid exam data."})
            return

        if self.path == "/api/checkin/extract":
            self._handle_checkin_extract()
            return

        if self.path == "/api/insights":
            self._handle_insights()
            return

        if self.path == "/api/daily-prompt":
            self._handle_daily_prompt()
            return

        if self.path == "/api/weekly-summary":
            self._handle_weekly_summary()
            return

        if self.path == "/api/report/passport":
            self._handle_passport()
            return

        if self.path in (
            "/validate-account",
            "/validate-email",
            "/signup-account",
            "/login-account",
        ):
            self._handle_account_action()
            return

        self.send_error(404)

    # ---------- Account endpoints ----------

    def _handle_account_action(self):
        try:
            data = self._read_json()
        except OverflowError:
            self._send_json(413, {"message": "Request is too large."})
            return
        except (ValueError, json.JSONDecodeError):
            self.send_error(400, "Invalid JSON")
            return

        if not isinstance(data, dict):
            data = {}
        username = data.get("username")
        password = data.get("password")
        email = data.get("email")
        mode = data.get("mode", "student")

        if self.path == "/validate-email":
            valid_email = email_format_check(email)
            self._send_json(200, {
                "valid": valid_email,
                "message": "Email format is valid." if valid_email else "Enter a valid email address.",
            })
            return

        username_valid = isinstance(username, str) and username_format_check(username)
        password_valid = password_format_check(password)
        email_valid = email_format_check(email) if email not in (None, "") else True
        valid = username_valid and password_valid and email_valid
        created = False
        authenticated = False
        user_profile = None
        session_token = None

        if self.path == "/signup-account" and valid:
            try:
                self._account_store().create_account(username, password, email, mode)
                message = "Account created successfully. You can now log in."
                created = True
            except ValueError as error:
                message = str(error)
        elif self.path == "/login-account":
            account_id = (
                self._account_store().authenticated_account_id(username, password)
                if valid else None
            )
            authenticated = account_id is not None
            if authenticated:
                session_token = secrets.token_urlsafe(32)
                self.sessions[session_token] = (account_id, time.monotonic() + 8 * 60 * 60)
                user_profile = self._account_store().get_user_profile(account_id)
                message = "Login successful."
            else:
                message = "Username or password is incorrect."
        elif not valid:
            if self.path == "/signup-account" and not email_valid:
                message = "Enter a valid email address."
            else:
                message = (
                    "Use a 3–32 character username (letters, numbers, underscores) and a "
                    "password longer than 8 characters with uppercase, lowercase, a number, "
                    "and punctuation."
                )
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
            response["user"] = user_profile
        self._send_json(200, response)

    # ---------- AI endpoints ----------

    def _handle_checkin_extract(self):
        try:
            data = self._read_json()
            transcript = data.get("transcript", "")
            mode = data.get("mode", "student")
            today = data.get("today")
            if not transcript or not transcript.strip():
                self._send_json(400, {"message": "Transcript cannot be empty."})
                return

            if core is None:
                self._send_json(500, {"message": "AI backend unavailable."})
                return
            extraction = core.extract_checkin(transcript, mode=mode, today=today)
            reply = core.spoken_reply(extraction)
            ext_dict = extraction.model_dump() if hasattr(extraction, "model_dump") else extraction.dict()
            ext_dict["spokenReply"] = reply.text
            self._send_json(200, {"extraction": ext_dict})
        except Exception as error:
            self._send_json(500, {"message": str(error)})

    def _handle_insights(self):
        try:
            data = self._read_json()
            mode = data.get("mode", "student")
            entries = data.get("entries", [])
            exam_phase = data.get("examPhase", "early_term")
            days_to_next_exam = data.get("daysToNextExam")
            next_exam_subject = data.get("nextExamSubject")

            now = time.strftime("%Y-%m-%d")
            moods = [e.get("mood") for e in entries if isinstance(e.get("mood"), (int, float))]
            sleeps = [e.get("sleepHours") for e in entries if isinstance(e.get("sleepHours"), (int, float))]
            stresses = [e.get("stress") for e in entries if isinstance(e.get("stress"), (int, float))]
            study_or_works = [
                (e.get("studyHours") or 0) + (e.get("workHours") or 0)
                for e in entries
                if e.get("studyHours") is not None or e.get("workHours") is not None
            ]

            avg_mood = sum(moods) / len(moods) if moods else None
            avg_sleep = sum(sleeps) / len(sleeps) if sleeps else None
            avg_stress = sum(stresses) / len(stresses) if stresses else None
            total_hours = sum(study_or_works) if study_or_works else None

            last7 = WeeklyFeatures(
                weekStart=now,
                days=len(entries),
                avgMood=round(avg_mood, 1) if avg_mood is not None else None,
                avgSleepHours=round(avg_sleep, 1) if avg_sleep is not None else None,
                avgStress=round(avg_stress, 1) if avg_stress is not None else None,
                totalStudyOrWorkHours=round(total_hours, 1) if total_hours is not None else None,
            )

            request = InsightsRequest(
                mode=mode,
                patterns=[],
                examPhase=exam_phase,
                daysToNextExam=days_to_next_exam,
                nextExamSubject=next_exam_subject,
                last7=last7,
            )

            if core is None:
                self._send_json(500, {"message": "AI backend unavailable."})
                return
            logs = [
                {
                    "sleepHours": e.get("sleepHours"),
                    "stress": e.get("stress"),
                    "fatigue": e.get("fatigue"),
                    "mood": e.get("mood"),
                    "studyHours": e.get("studyHours"),
                    "workHours": e.get("workHours"),
                }
                for e in entries
            ]
            insights_result = core.explain_recorded_patterns(logs, request)
            self._send_json(
                200,
                insights_result.model_dump()
                if hasattr(insights_result, "model_dump")
                else insights_result.dict(),
            )
        except Exception as error:
            self._send_json(500, {"message": str(error)})

    def _handle_daily_prompt(self):
        try:
            data = self._read_json()
            mode = data.get("mode", "student")
            exam_phase = data.get("examPhase", "early_term")
            days_to_next_exam = data.get("daysToNextExam")
            next_exam_subject = data.get("nextExamSubject")
            recent = []
            for item in data.get("recent", [])[:3]:
                recent.append(EntrySnapshot(
                    date=str(item.get("date", "")),
                    mood=item.get("mood"),
                    stress=item.get("stress"),
                    sleepHours=item.get("sleepHours"),
                    studyHours=item.get("studyHours"),
                    workHours=item.get("workHours"),
                    tags=item.get("tags", []),
                    summary=str(item.get("summary", item.get("title", ""))),
                    safetyLevel=item.get("safetyLevel", "none"),
                ))

            if core is None:
                self._send_json(200, {
                    "prompt": "What is one small win from today that you want to remember next month?"
                })
                return
            prompt_result = core.daily_prompt(DailyPromptRequest(
                mode=mode,
                examPhase=exam_phase,
                daysToNextExam=days_to_next_exam,
                nextExamSubject=next_exam_subject,
                recent=recent,
            ))
            self._send_json(200, {"prompt": prompt_result.prompt})
        except Exception:
            self._send_json(200, {
                "prompt": "What is one thing that brought you peace or relief today?"
            })

    def _handle_weekly_summary(self):
        try:
            data = self._read_json()
            mode = data.get("mode", "student")
            entries = [
                EntrySnapshot(
                    date=str(item.get("date", "")),
                    mood=item.get("mood"),
                    stress=item.get("stress"),
                    sleepHours=item.get("sleepHours"),
                    studyHours=item.get("studyHours"),
                    workHours=item.get("workHours"),
                    tags=item.get("tags", []),
                    summary=str(item.get("summary", item.get("text", "")))[:200],
                    safetyLevel=item.get("safetyLevel", "none"),
                )
                for item in data.get("entries", [])
            ]
            if core is None:
                self._send_json(500, {"message": "AI backend unavailable."})
                return
            summary_result = core.weekly_summary(WeeklySummaryRequest(mode=mode, entries=entries))
            self._send_json(
                200,
                summary_result.model_dump()
                if hasattr(summary_result, "model_dump")
                else summary_result.dict(),
            )
        except Exception as error:
            self._send_json(500, {"message": str(error)})

    def _handle_passport(self):
        try:
            data = self._read_json()
            mode = data.get("mode", "student")
            entries = data.get("entries", [])
            period_days = int(data.get("periodDays", 14))

            sleeps = [e["sleepHours"] for e in entries if isinstance(e.get("sleepHours"), (int, float))]
            stresses = [e["stress"] for e in entries if isinstance(e.get("stress"), (int, float))]
            fatigues = [e["fatigue"] for e in entries if isinstance(e.get("fatigue"), (int, float))]
            studies = [e["studyHours"] for e in entries if isinstance(e.get("studyHours"), (int, float))]
            works = [e["workHours"] for e in entries if isinstance(e.get("workHours"), (int, float))]

            avg_sleep = round(sum(sleeps) / len(sleeps), 1) if sleeps else 7.0
            avg_stress = round(sum(stresses) / len(stresses), 1) if stresses else 5.0
            avg_fatigue = round(sum(fatigues) / len(fatigues), 1) if fatigues else 4.0
            total_study = round(sum(studies), 1) if studies else 0.0
            total_work = round(sum(works), 1) if works else 0.0

            barriers = []
            adjustments = []

            if avg_sleep < 6.5:
                barriers.append("Sleep deficit (<6.5h avg) impacting daily stamina and focus recovery.")
                adjustments.append("Core hours flexibility / 10:00 AM start to allow natural circadian recovery.")
            if avg_fatigue >= 6.0:
                barriers.append("Elevated physical/cognitive fatigue scores during high load periods.")
                adjustments.append("Structured 10-minute micro-breaks every 50 minutes of continuous task time.")
            if avg_stress >= 6.5:
                barriers.append("Heightened stress markers near major deadlines or shift transitions.")
                adjustments.append("Staggered assessment/project deadlines and advance task scheduling.")

            if mode == "student":
                adjustments.extend([
                    "Exam room accommodation: quiet space with permission for rest breaks.",
                    "Access to lecture recordings and written summaries.",
                    "Designated academic mentor for revision workload pacing.",
                ])
            elif mode == "employed":
                adjustments.extend([
                    "Ergonomic workstation review and assistive hardware/software provision.",
                    "Phased return-to-work or flexible shift-pacing rota.",
                    "Quiet breakout zone for sensory and cognitive reset.",
                ])
            else:
                adjustments.extend([
                    "Graduated routine building: 2-3 hour micro-volunteering or study goals.",
                    "Respite Energy Passport: pacing activities within personal energy envelope.",
                    "Social prescribing referral to local North East community wellbeing groups.",
                ])

            report = {
                "mode": mode,
                "periodDays": period_days,
                "generatedAt": time.strftime("%Y-%m-%d %H:%M"),
                "sampleEntriesCount": len(entries),
                "telemetryAverages": {
                    "avgSleepHours": avg_sleep,
                    "avgStressScore": avg_stress,
                    "avgFatigueScore": avg_fatigue,
                    "totalStudyHours": total_study,
                    "totalWorkHours": total_work,
                },
                "identifiedBarriers": barriers or [
                    "Consistent baseline capacity with minor periodic load fatigue."
                ],
                "recommendedAdjustments": adjustments,
                "declaration": (
                    "This report provides evidence-based wellbeing telemetry to support "
                    "Equality Act 2010 Reasonable Adjustments and DWP Access to Work grant "
                    "applications. It does not replace clinical diagnosis."
                ),
            }
            self._send_json(200, {"report": report})
        except Exception as error:
            self._send_json(500, {"message": str(error)})

    # ---------- Update / delete ----------

    def do_PUT(self):
        if self.path == "/account/password":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json(4096)
                if not isinstance(data, dict):
                    raise ValueError("Invalid password change request.")
                changed = self._account_store().change_password(
                    account_id,
                    data.get("current_password"),
                    data.get("new_password"),
                )
            except OverflowError:
                self._send_json(413, {"message": "Password change request is too large."})
                return
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid password change request."})
                return
            if not changed:
                self._send_json(400, {"message": "Current password is incorrect."})
                return
            self._send_json(200, {"message": "Password updated."})
            return

        if not self.path.startswith("/entries/"):
            self.send_error(404)
            return
        account_id = self._authenticated_account_id()
        if account_id is None:
            self._send_json(401, {"message": "Please log in again."})
            return
        entry_id = self._entry_id("/entries/")
        if entry_id is None:
            self._send_json(400, {"message": "Invalid entry id."})
            return
        try:
            data = self._read_json(50000)
            if not isinstance(data, dict):
                raise ValueError("Invalid entry data.")
            updated = self._account_store().update_entry(
                account_id, entry_id, data.get("title"), data.get("text")
            )
        except OverflowError:
            self._send_json(413, {"message": "Entry is too large."})
            return
        except (ValueError, json.JSONDecodeError, AttributeError) as error:
            self._send_json(400, {"message": str(error) or "Invalid entry data."})
            return
        if not updated:
            self._send_json(404, {"message": "Entry not found."})
            return
        self._send_json(200, {"message": "Entry updated."})

    def do_DELETE(self):
        if self.path.startswith("/exams/"):
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            exam_id = self._entry_id("/exams/")
            if exam_id is None:
                self._send_json(400, {"message": "Invalid exam id."})
                return
            if not self._account_store().delete_exam(account_id, exam_id):
                self._send_json(404, {"message": "Exam not found."})
                return
            self._send_json(200, {"message": "Exam deleted."})
            return

        if not self.path.startswith("/entries/"):
            self.send_error(404)
            return
        account_id = self._authenticated_account_id()
        if account_id is None:
            self._send_json(401, {"message": "Please log in again."})
            return
        entry_id = self._entry_id("/entries/")
        if entry_id is None:
            self._send_json(400, {"message": "Invalid entry id."})
            return
        if not self._account_store().delete_entry(account_id, entry_id):
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
    print(
        "Smart Diary account and entry server listening at "
        f"http://{server.server_address[0]}:{server.server_address[1]}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSmart Diary server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
