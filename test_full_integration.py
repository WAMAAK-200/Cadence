import json
import unittest
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path
import os
import tempfile

from account_store import AccountStore
from security import AccountHandler
from ai_backend import core
from ai_backend.schemas import (
    DailyPromptRequest,
    EntrySnapshot,
    InsightsRequest,
    WeeklyFeatures,
    WeeklySummaryRequest,
)


class TestFullIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.db_fd)
        cls.store = AccountStore(database_path=cls.db_path)

        # Patch DEFAULT_DATABASE for server tests
        from account_store import DEFAULT_DATABASE
        cls.orig_db = DEFAULT_DATABASE

        # Start background HTTP server
        cls.server_port = 8899
        cls.server = HTTPServer(("127.0.0.1", cls.server_port), AccountHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def _api_request(self, path, method="GET", data=None, token=None):
        url = f"http://127.0.0.1:{self.server_port}{path}"
        headers = {}
        body = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(data).encode("utf-8")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                resp_body = response.read().decode("utf-8")
                return response.status, json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as error:
            resp_body = error.read().decode("utf-8")
            return error.code, json.loads(resp_body) if resp_body else {}

    def test_01_static_pages_serve_successfully(self):
        pages = [
            "/",
            "/user_interface.html",
            "/calendar.html",
            "/insights.html",
            "/entries.html",
            "/account.html",
            "/sign_up.html",
            "/user_style.css",
            "/entry_storage.js",
            "/music_synth.js",
        ]
        for p in pages:
            url = f"http://127.0.0.1:{self.server_port}{p}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req) as resp:
                self.assertEqual(resp.status, 200, f"Failed serving {p}")
                self.assertGreater(len(resp.read()), 50, f"Empty page {p}")

    def test_02_status_endpoint(self):
        status, data = self._api_request("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertIn("aiMode", data)

    def test_03_auth_flow_and_mode_persistence(self):
        username = f"user_{int(time.time())}"
        password = "SecurePassword123!"

        # Sign up
        status, res = self._api_request("/signup-account", method="POST", data={
            "username": username,
            "password": password,
            "mode": "student"
        })
        self.assertEqual(status, 200)
        self.assertTrue(res["created"])

        # Login
        status, res = self._api_request("/login-account", method="POST", data={
            "username": username,
            "password": password
        })
        self.assertEqual(status, 200)
        self.assertTrue(res["authenticated"])
        token = res["session_token"]
        self.assertIsNotNone(token)
        self.assertEqual(res["user"]["mode"], "student")

        # Get profile
        status, res = self._api_request("/user-profile", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(res["profile"]["username"], username)
        self.assertEqual(res["profile"]["mode"], "student")

        # Switch mode to employed
        status, res = self._api_request("/user-profile", method="POST", data={"mode": "employed"}, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(res["profile"]["mode"], "employed")

    def test_04_entries_full_telemetry_crud(self):
        username = f"telemetry_{int(time.time())}"
        password = "SecurePassword123!"
        self._api_request("/signup-account", method="POST", data={"username": username, "password": password})
        _, login_res = self._api_request("/login-account", method="POST", data={"username": username, "password": password})
        token = login_res["session_token"]

        # Create entry with full telemetry
        entry_payload = {
            "date": "2026-11-14",
            "title": "Study in Durham",
            "mood": "happy",
            "text": "Had a canny good day revising Algorithms at the library.",
            "tags": ["#revision", "#durham"],
            "sleepHours": 8.0,
            "sleepQuality": "good",
            "stress": 3,
            "fatigue": 2,
            "studyHours": 5.0,
            "workHours": 0.0,
            "summary": "Revised algorithms with low stress."
        }
        status, res = self._api_request("/entries", method="POST", data=entry_payload, token=token)
        self.assertEqual(status, 201)
        entry_id = res["entry"]["id"]
        self.assertEqual(res["entry"]["sleepHours"], 8.0)
        self.assertEqual(res["entry"]["stress"], 3)
        self.assertEqual(res["entry"]["studyHours"], 5.0)

        # List entries
        status, res = self._api_request("/entries", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(res["entries"]), 1)
        self.assertEqual(res["entries"][0]["id"], entry_id)

        # Update entry
        status, res = self._api_request(f"/entries/{entry_id}", method="PUT", data={"title": "Updated Study Title", "text": "Updated text"}, token=token)
        self.assertEqual(status, 200)

        # Delete entry
        status, res = self._api_request(f"/entries/{entry_id}", method="DELETE", token=token)
        self.assertEqual(status, 200)

        status, res = self._api_request("/entries", token=token)
        self.assertEqual(len(res["entries"]), 0)

    def test_05_exams_crud(self):
        username = f"examuser_{int(time.time())}"
        password = "SecurePassword123!"
        self._api_request("/signup-account", method="POST", data={"username": username, "password": password})
        _, login_res = self._api_request("/login-account", method="POST", data={"username": username, "password": password})
        token = login_res["session_token"]

        # Save exam
        exam_data = {
            "subject": "Distributed Systems",
            "date": "2026-12-01",
            "targetHours": 25.0,
            "completedHours": 8.5,
            "notes": "Raft consensus algorithm"
        }
        status, res = self._api_request("/exams", method="POST", data=exam_data, token=token)
        self.assertEqual(status, 200)
        exam_id = res["exam"]["id"]

        # List exams
        status, res = self._api_request("/exams", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(len(res["exams"]), 1)
        self.assertEqual(res["exams"][0]["subject"], "Distributed Systems")

        # Delete exam
        status, res = self._api_request(f"/exams/{exam_id}", method="DELETE", token=token)
        self.assertEqual(status, 200)

    def test_06_ai_checkin_extraction_and_dialect(self):
        status, res = self._api_request("/api/checkin/extract", method="POST", data={
            "transcript": "Proper knackered after revision today, feeling canny sound otherwise",
            "mode": "student"
        })
        self.assertEqual(status, 200)
        ext = res["extraction"]
        self.assertIn("fatigue", ext)
        self.assertGreaterEqual(ext["fatigue"], 7)
        self.assertEqual(ext["safety"]["level"], "none")
        self.assertIn("spokenReply", ext)
        self.assertTrue(len(ext["spokenReply"]) > 0)

    def test_07_ai_crisis_safety_screening(self):
        status, res = self._api_request("/api/checkin/extract", method="POST", data={
            "transcript": "I want to kill myself, feeling overwhelmed",
            "mode": "student"
        })
        self.assertEqual(status, 200)
        ext = res["extraction"]
        self.assertEqual(ext["safety"]["level"], "crisis")
        self.assertIn("Samaritans", ext["spokenReply"])

    def test_08_ai_insights_calculation(self):
        entries = [
            {"date": "2026-11-10", "sleepHours": 5.0, "stress": 8, "mood": 4, "studyHours": 6.0},
            {"date": "2026-11-11", "sleepHours": 5.5, "stress": 9, "mood": 4, "studyHours": 7.0},
            {"date": "2026-11-12", "sleepHours": 6.0, "stress": 7, "mood": 5, "studyHours": 5.0},
            {"date": "2026-11-13", "sleepHours": 8.0, "stress": 3, "mood": 8, "studyHours": 4.0},
            {"date": "2026-11-14", "sleepHours": 8.5, "stress": 2, "mood": 8, "studyHours": 3.0},
        ]
        status, res = self._api_request("/api/insights", method="POST", data={
            "mode": "student",
            "entries": entries,
            "examPhase": "pre_exam",
            "daysToNextExam": 5,
            "nextExamSubject": "Computer Science"
        })
        self.assertEqual(status, 200)
        self.assertIn("insights", res)
        self.assertIn("advice", res)

    def test_09_access_to_work_report(self):
        entries = [
            {"date": "2026-11-10", "sleepHours": 5.5, "stress": 8, "fatigue": 7, "studyHours": 6.0, "workHours": 0},
            {"date": "2026-11-12", "sleepHours": 6.0, "stress": 7, "fatigue": 6, "studyHours": 5.0, "workHours": 0},
        ]
        status, res = self._api_request("/api/report/passport", method="POST", data={
            "mode": "student",
            "entries": entries,
            "periodDays": 14
        })
        self.assertEqual(status, 200)
        report = res["report"]
        self.assertEqual(report["mode"], "student")
        self.assertIn("telemetryAverages", report)
        self.assertIn("recommendedAdjustments", report)


if __name__ == "__main__":
    unittest.main()
