import json
import secrets
import time
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from input_validation import password_format as password_format_check
from input_validation import username_format as username_format_check

# Make sure ai_backend can be imported
PROJECT_ROOT = Path(__file__).parent.resolve()
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
    """Unified HTTP server handling all Smart Diary static files and API endpoints."""

    sessions = {}
    allowed_origins = {"http://127.0.0.1:8000", "http://localhost:8000"}

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
        # 1. API Status
        if self.path == "/api/status":
            ai_mode = core.ai_mode() if core else "offline"
            self._send_json(200, {
                "status": "ok",
                "app": "Smart Diary (Cadence)",
                "aiMode": ai_mode,
                "offline": ai_mode == "offline",
                "version": "1.0.0"
            })
            return

        # 2. User Profile
        if self.path == "/user-profile":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            from account_store import AccountStore
            profile = AccountStore().get_user_profile(account_id)
            if not profile:
                self._send_json(404, {"message": "Profile not found."})
                return
            self._send_json(200, {"profile": profile})
            return

        # 3. Diary Entries
        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            from account_store import AccountStore
            self._send_json(200, {"entries": AccountStore().list_entries(account_id)})
            return

        # 4. Exams
        if self.path == "/exams":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            from account_store import AccountStore
            self._send_json(200, {"exams": AccountStore().list_exams(account_id)})
            return

        # 5. Static Files Serving
        clean_path = self.path.split("?")[0].lstrip("/")
        if clean_path in ("", "index.html"):
            clean_path = "user_interface.html"

        # Check in root first, then frontend
        target_file = PROJECT_ROOT / clean_path
        if not target_file.is_file():
            target_file = PROJECT_ROOT / "frontend" / clean_path

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
        # 1. Logout
        if self.path == "/logout":
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            self.sessions.pop(token, None)
            self._send_json(200, {"message": "Logged out."})
            return

        # 2. User Profile Update
        if self.path == "/user-profile":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json()
                from account_store import AccountStore
                profile = AccountStore().update_user_profile(
                    account_id,
                    mode=data.get("mode"),
                    settings=data.get("settings")
                )
                self._send_json(200, {"profile": profile})
            except Exception as e:
                self._send_json(400, {"message": str(e)})
            return

        # 3. Create Diary Entry
        if self.path == "/entries":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json(65536)
                from account_store import AccountStore
                entry = AccountStore().create_entry(account_id, data)
                self._send_json(201, {"entry": entry})
            except OverflowError:
                self._send_json(413, {"message": "Entry is too large."})
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error) or "Invalid JSON."})
            return

        # 4. Save/Update Exam
        if self.path == "/exams":
            account_id = self._authenticated_account_id()
            if account_id is None:
                self._send_json(401, {"message": "Please log in again."})
                return
            try:
                data = self._read_json()
                from account_store import AccountStore
                exam = AccountStore().save_exam(account_id, data)
                self._send_json(200, {"exam": exam})
            except (ValueError, json.JSONDecodeError) as error:
                self._send_json(400, {"message": str(error)})
            return

        # 5. AI Endpoints: Check-in Extract & Dialect Normalization
        if self.path == "/api/checkin/extract":
            try:
                data = self._read_json()
                transcript = data.get("transcript", "")
                mode = data.get("mode", "student")
                today = data.get("today")
                if not transcript or not transcript.strip():
                    self._send_json(400, {"message": "Transcript cannot be empty."})
                    return

                if core:
                    extraction = core.extract_checkin(transcript, mode=mode, today=today)
                    reply = core.spoken_reply(extraction)
                    ext_dict = extraction.model_dump() if hasattr(extraction, "model_dump") else extraction.dict()
                    ext_dict["spokenReply"] = reply.text
                    self._send_json(200, {"extraction": ext_dict})
                else:
                    self._send_json(500, {"message": "AI backend unavailable."})
            except Exception as e:
                self._send_json(500, {"message": str(e)})
            return

        # 6. AI Endpoints: Pattern & Insight Explanation
        if self.path == "/api/insights":
            try:
                data = self._read_json()
                mode = data.get("mode", "student")
                entries = data.get("entries", [])
                exam_phase = data.get("examPhase", "early_term")
                days_to_next_exam = data.get("daysToNextExam")
                next_exam_subject = data.get("nextExamSubject")

                # Compute weekly features
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
                    avgMood=round(avg_mood, 1) if avg_mood else None,
                    avgSleepHours=round(avg_sleep, 1) if avg_sleep else None,
                    avgStress=round(avg_stress, 1) if avg_stress else None,
                    totalStudyOrWorkHours=round(total_hours, 1) if total_hours else None,
                )

                req = InsightsRequest(
                    mode=mode,
                    patterns=[],
                    examPhase=exam_phase,
                    daysToNextExam=days_to_next_exam,
                    nextExamSubject=next_exam_subject,
                    last7=last7,
                )

                if core:
                    logs = []
                    for e in entries:
                        logs.append({
                            "sleepHours": e.get("sleepHours"),
                            "stress": e.get("stress"),
                            "fatigue": e.get("fatigue"),
                            "mood": e.get("mood"),
                            "studyHours": e.get("studyHours"),
                            "workHours": e.get("workHours"),
                        })
                    insights_res = core.explain_recorded_patterns(logs, req)
                    res_dict = insights_res.model_dump() if hasattr(insights_res, "model_dump") else insights_res.dict()
                    self._send_json(200, res_dict)
                else:
                    self._send_json(500, {"message": "AI backend unavailable."})
            except Exception as e:
                self._send_json(500, {"message": str(e)})
            return

        # 7. AI Endpoints: Daily Writing Prompt
        if self.path == "/api/daily-prompt":
            try:
                data = self._read_json()
                mode = data.get("mode", "student")
                exam_phase = data.get("examPhase", "early_term")
                days_to_next_exam = data.get("daysToNextExam")
                next_exam_subject = data.get("nextExamSubject")
                recent_raw = data.get("recent", [])
                recent = []
                for r in recent_raw[:3]:
                    recent.append(EntrySnapshot(
                        date=str(r.get("date", "")),
                        mood=r.get("mood"),
                        stress=r.get("stress"),
                        sleepHours=r.get("sleepHours"),
                        studyHours=r.get("studyHours"),
                        workHours=r.get("workHours"),
                        tags=r.get("tags", []),
                        summary=str(r.get("summary", r.get("title", ""))),
                        safetyLevel=r.get("safetyLevel", "none"),
                    ))

                if core:
                    prompt_res = core.daily_prompt(DailyPromptRequest(
                        mode=mode,
                        examPhase=exam_phase,
                        daysToNextExam=days_to_next_exam,
                        nextExamSubject=next_exam_subject,
                        recent=recent,
                    ))
                    self._send_json(200, {"prompt": prompt_res.prompt})
                else:
                    self._send_json(200, {"prompt": "What is one small win from today that you want to remember next month?"})
            except Exception as e:
                self._send_json(200, {"prompt": "What is one thing that brought you peace or relief today?"})
            return

        # 8. AI Endpoints: Weekly Summary
        if self.path == "/api/weekly-summary":
            try:
                data = self._read_json()
                mode = data.get("mode", "student")
                entries_raw = data.get("entries", [])
                entries = []
                for r in entries_raw:
                    entries.append(EntrySnapshot(
                        date=str(r.get("date", "")),
                        mood=r.get("mood"),
                        stress=r.get("stress"),
                        sleepHours=r.get("sleepHours"),
                        studyHours=r.get("studyHours"),
                        workHours=r.get("workHours"),
                        tags=r.get("tags", []),
                        summary=str(r.get("summary", r.get("text", "")))[:200],
                        safetyLevel=r.get("safetyLevel", "none"),
                    ))

                if core:
                    summary_res = core.weekly_summary(WeeklySummaryRequest(mode=mode, entries=entries))
                    res_dict = summary_res.model_dump() if hasattr(summary_res, "model_dump") else summary_res.dict()
                    self._send_json(200, res_dict)
                else:
                    self._send_json(500, {"message": "AI backend unavailable."})
            except Exception as e:
                self._send_json(500, {"message": str(e)})
            return

        # 9. Access-to-Work / Wellbeing Passport Generator
        if self.path == "/api/report/passport":
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
                        "Designated academic mentor for revision workload pacing."
                    ])
                elif mode == "employed":
                    adjustments.extend([
                        "Ergonomic workstation review and assistive hardware/software provision.",
                        "Phased return-to-work or flexible shift-pacing rota.",
                        "Quiet breakout zone for sensory and cognitive reset."
                    ])
                else: # unemployed / health recovery
                    adjustments.extend([
                        "Graduated routine building: 2-3 hour micro-volunteering or study goals.",
                        "Respite Energy Passport: pacing activities within personal energy envelope.",
                        "Social prescribing referral to local North East community wellbeing groups."
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
                    "identifiedBarriers": barriers or ["Consistent baseline capacity with minor periodic load fatigue."],
                    "recommendedAdjustments": adjustments,
                    "declaration": (
                        "This report provides evidence-based wellbeing telemetry to support Equality Act 2010 "
                        "Reasonable Adjustments and DWP Access to Work grant applications. It does not replace clinical diagnosis."
                    )
                }
                self._send_json(200, {"report": report})
            except Exception as e:
                self._send_json(500, {"message": str(e)})
            return

        # 10. Account Sign Up & Login Endpoints
        if self.path in ("/validate-account", "/signup-account", "/login-account"):
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
            mode = data.get("mode", "student") if isinstance(data, dict) else "student"
            username_valid = isinstance(username, str) and username_format_check(username)
            password_valid = password_format_check(password)
            valid = username_valid and password_valid
            created = False
            authenticated = False
            user_profile = None

            if self.path == "/signup-account" and valid:
                try:
                    from account_store import AccountStore
                    account_id = AccountStore().create_account(username, password, mode=mode)
                    user_profile = AccountStore().get_user_profile(account_id)
                    message = "Account created successfully. You can now log in."
                    created = True
                except ValueError as error:
                    message = str(error)
            elif self.path == "/login-account":
                from account_store import AccountStore
                account_id = AccountStore().authenticated_account_id(username, password) if valid else None
                authenticated = account_id is not None
                session_token = None
                if authenticated:
                    session_token = secrets.token_urlsafe(32)
                    self.sessions[session_token] = (account_id, time.monotonic() + 8 * 60 * 60)
                    user_profile = AccountStore().get_user_profile(account_id)
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
                response["user"] = user_profile
            self._send_json(200, response)
            return

        self.send_error(404)

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
            data = self._read_json(65536)
            from account_store import AccountStore
            updated = AccountStore().update_entry(account_id, entry_id, data.get("title"), data.get("text"))
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
        account_id = self._authenticated_account_id()
        if account_id is None:
            self._send_json(401, {"message": "Please log in again."})
            return

        if self.path.startswith("/entries/"):
            try:
                entry_id = int(self.path.removeprefix("/entries/"))
            except ValueError:
                self._send_json(400, {"message": "Invalid entry id."})
                return
            from account_store import AccountStore
            deleted = AccountStore().delete_entry(account_id, entry_id)
            if not deleted:
                self._send_json(404, {"message": "Entry not found."})
                return
            self._send_json(200, {"message": "Entry deleted."})
            return

        if self.path.startswith("/exams/"):
            try:
                exam_id = int(self.path.removeprefix("/exams/"))
            except ValueError:
                self._send_json(400, {"message": "Invalid exam id."})
                return
            from account_store import AccountStore
            deleted = AccountStore().delete_exam(account_id, exam_id)
            if not deleted:
                self._send_json(404, {"message": "Exam not found."})
                return
            self._send_json(200, {"message": "Exam deleted."})
            return

        self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    try:
        server = HTTPServer(("127.0.0.1", port), AccountHandler)
    except OSError as error:
        raise RuntimeError(f"Port {port} is unavailable; stop the process using it before starting Smart Diary.") from error

    print(f"Smart Diary unified server listening at http://127.0.0.1:{port}")
    server.serve_forever()

