"""Lane D: the three Claude calls for Cadence.

    extract_checkin(transcript, mode)  -> CheckinExtraction   (call 1)
    explain_insights(InsightsRequest)  -> InsightsResponse    (call 2)
    spoken_reply(CheckinExtraction)    -> SpokenReplyResponse (call 3)
    weekly_summary(WeeklySummaryRequest) -> WeeklySummaryResponse (call 4, Insights page)
    daily_prompt(DailyPromptRequest)   -> DailyPromptResponse (call 5, Smart Assistant; never raises)

Two modes (see ai_mode()):
  - "claude": calls the Claude API. Needs ANTHROPIC_API_KEY.
  - "offline": rule-based engine in offline.py, same outputs, no key, no cost.
With no key the app runs offline automatically. In claude mode, any failed call
falls back to the offline engine, so the demo never breaks. The only AiError
left is an empty transcript.

Env (.env): ANTHROPIC_API_KEY, optional CLAUDE_MODEL (default claude-opus-5-5),
optional AI_MODE = auto (default) | claude | offline.
Privacy: we never log diary text, only call name, token counts and timings.
"""

import csv
import json
import re
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
import os

import anthropic
from dotenv import load_dotenv

try:  # works both as `ai_backend.core` and when run from inside ai_backend/
    from . import offline
    from .patterns import calculate_user_patterns
    from .schemas import (
        CheckinExtraction, DailyPromptRequest, DailyPromptResponse, InsightsRequest, InsightsResponse,
        SafetyFlag, SpokenReplyResponse, WeeklySummaryRequest, WeeklySummaryResponse,
    )
except ImportError:
    import offline
    from patterns import calculate_user_patterns
    from schemas import (
        CheckinExtraction, DailyPromptRequest, DailyPromptResponse, InsightsRequest, InsightsResponse,
        SafetyFlag, SpokenReplyResponse, WeeklySummaryRequest, WeeklySummaryResponse,
    )

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
HERE = Path(__file__).resolve().parent
PROMPTS_DIR = HERE.parent / "prompts"
DATASET_CSV = HERE / "colloquialisms_dataset.csv"

# Models that accept server-side refusal fallbacks. Other models skip the beta.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"}

# Fixed, human-written crisis message. Never AI-generated. Keep identical to prompts/spoken-reply.md.
CRISIS_MESSAGE = (
    "It sounds like things are really hard right now, and you don't have to deal with this on your own. "
    "You can call Samaritans free, any time, on 116 123, or contact your university wellbeing service. "
    "If you're in immediate danger, call 999."
)

# Fixed texts for calls 4 and 5 (no AI call needed in these cases).
HELPLINE_LINE = "If things still feel heavy, Samaritans are free on 116 123, any time."
DEFAULT_DAILY_PROMPT = "What is one small win from today that you want to remember next month?"
CRISIS_DAILY_PROMPT = "You don't have to write anything today. " + HELPLINE_LINE
EMPTY_WEEK_SUMMARY = "No check-ins yet this week. Even a 10-second one adds a note to this week's composition."


class AiError(Exception):
    """Any failure in a Claude call. Public functions catch it and use the offline engine."""


def ai_mode() -> str:
    """'claude' or 'offline'. The server can send this to the UI to show an "Offline mode" badge."""
    setting = os.getenv("AI_MODE", "auto").lower()
    if setting == "offline":
        return "offline"
    has_key = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    return "claude" if has_key else "offline"


# ---------- Prompt loading ----------

@lru_cache(maxsize=None)
def load_system_prompt(name: str) -> str:
    """Return the text between '## SYSTEM' and '## USER' in prompts/<name>.md."""
    text = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    start = text.index("## SYSTEM") + len("## SYSTEM")
    end = text.index("## USER", start)
    return text[start:end].strip()


@lru_cache(maxsize=None)
def build_glossary() -> str:
    """Merge Warith's CSV dataset with prompts/ne-dialect-glossary.md into one bullet list."""
    lines = []
    if DATASET_CSV.exists():
        with DATASET_CSV.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                # The clinical-mapping column is left out on purpose: we never show diagnosis-style labels.
                lines.append(f'- "{row["term"]}": {row["standard_meaning"]} (e.g. "{row["example_sentence"]}")')
    md = PROMPTS_DIR / "ne-dialect-glossary.md"
    if md.exists():
        for line in md.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # Table body rows only: skip the header row and the |---| separator.
            if len(cells) == 3 and cells[0] not in ("Phrase", "") and not set(cells[0]) <= {"-"}:
                lines.append(f"- {cells[0]}: {cells[1]} ({cells[2]})")
    return "\n".join(lines)


# ---------- Safety net (runs in code, before and regardless of the AI) ----------

# Deliberately broad: a false alarm shows a helpline; a miss is far worse.
_CRISIS_PATTERNS = [
    r"\bkill(ing)? my ?self\b", r"\bsuicid", r"\bend (it all|my life)\b", r"\bself[- ]?harm",
    r"\bhurt(ing)? my ?self\b", r"\bcut(ting)? my ?self\b", r"\bwant(s)? to die\b",
    r"\b(don'?t|do not|divvent|dinnet|divn'?t) want to (be here|live|wake up)\b",
    r"\bbetter off without (me|us)\b", r"\bno (point|reason) (in )?(living|being alive|going on)\b",
]
_CRISIS_RE = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)


def keyword_crisis(text: str) -> bool:
    return bool(_CRISIS_RE.search(text))


# ---------- Parsing helpers ----------

def strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers if the model added them."""
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return m.group(1) if m else text


def parse_json_safely(text: str, model_cls):
    try:
        return model_cls.model_validate(json.loads(strip_fences(text)))
    except Exception as e:  # JSONDecodeError or pydantic ValidationError
        raise AiError(f"could not parse {model_cls.__name__}: {type(e).__name__}") from e


def _clamp(value, lo, hi, as_int=False):
    if value is None:
        return None
    value = max(lo, min(hi, value))
    return int(round(value)) if as_int else value


def clamp_extraction(e: CheckinExtraction) -> CheckinExtraction:
    e.mood = _clamp(e.mood, 1, 10, as_int=True)
    e.stress = _clamp(e.stress, 1, 10, as_int=True)
    e.fatigue = _clamp(e.fatigue, 1, 10, as_int=True)
    e.sleepHours = _clamp(e.sleepHours, 0, 24)
    e.studyHours = _clamp(e.studyHours, 0, 24)
    e.workHours = _clamp(e.workHours, 0, 24)
    e.tags = [t.lower() for t in e.tags][:5]
    return e


# ---------- The API call ----------

_client = None


def get_client() -> anthropic.Anthropic:
    # Created lazily so importing this module never fails when the key is missing.
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _log_usage(call: str, ms: int, ok: bool, response=None) -> None:
    """Cost logging for the pitch. Counts and timings only, never diary text."""
    usage = getattr(response, "usage", None)
    print(json.dumps({
        "ai_call": call,
        "model": getattr(response, "model", MODEL),
        "inputTokens": getattr(usage, "input_tokens", 0),
        "outputTokens": getattr(usage, "output_tokens", 0),
        "ms": ms,
        "ok": ok,
    }))


def _call(call: str, system: str, user_text: str, model_cls, effort: str, fallback=None):
    """Run a call in the current mode. `fallback` is a no-argument function that returns the
    offline answer; it is used in offline mode and whenever the Claude call fails."""
    if ai_mode() == "offline" and fallback is not None:
        print(json.dumps({"ai_call": call, "mode": "offline"}))
        return fallback()
    try:
        return _claude_call(call, system, user_text, model_cls, effort)
    except AiError:
        if fallback is None:
            raise
        print(json.dumps({"ai_call": call, "mode": "offline-fallback"}))
        return fallback()


def _claude_call(call: str, system: str, user_text: str, model_cls, effort: str, max_tokens: int = 8000):
    started = time.monotonic()
    ms = lambda: int((time.monotonic() - started) * 1000)
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_text}],
        output_format=model_cls,  # structured outputs: response is guaranteed to match the schema
        output_config={"effort": effort},
    )
    try:
        if MODEL in FALLBACK_MODELS:
            # If a safety classifier declines, the API retries on a fallback model in the same call.
            response = get_client().beta.messages.parse(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            response = get_client().messages.parse(**kwargs)
    except anthropic.APIStatusError as e:
        _log_usage(call, ms(), False)
        raise AiError(f"{call}: API error {e.status_code}") from e
    except anthropic.APIConnectionError as e:
        _log_usage(call, ms(), False)
        raise AiError(f"{call}: network error") from e
    except Exception as e:  # e.g. structured output failed validation
        _log_usage(call, ms(), False)
        raise AiError(f"{call}: {type(e).__name__}") from e

    if response.stop_reason in ("refusal", "max_tokens"):
        _log_usage(call, ms(), False, response)
        raise AiError(f"{call}: stopped with {response.stop_reason}")

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:  # belt and braces: parse the text ourselves
        text = "".join(b.text for b in response.content if b.type == "text")
        parsed = parse_json_safely(text, model_cls)
    _log_usage(call, ms(), True, response)
    return parsed


# ---------- Public functions ----------

def transcribe_audio(audio_file) -> str:
    """Transcribe audio for review before passing the confirmed text to extract_checkin."""
    try:
        from .transcription import transcribe_audio as transcribe
    except ImportError:
        from transcription import transcribe_audio as transcribe
    return transcribe(audio_file)


def process_recording(audio_file, mode: str = "student", today: str | None = None):
    """Transcribe and process audio immediately; inspect entry.safety before storage."""
    entry = extract_checkin(transcribe_audio(audio_file), mode=mode, today=today)
    return entry, spoken_reply(entry)


def extract_checkin(transcript: str, mode: str = "student", today: str | None = None) -> CheckinExtraction:
    """Call 1: transcript -> structured entry. Always check result.safety.level before anything else."""
    if not transcript or not transcript.strip():
        raise AiError("checkin: empty transcript")

    keyword_hit = keyword_crisis(transcript)
    system = (
        load_system_prompt("checkin-extract")
        .replace("{{MODE}}", mode)
        .replace("{{TODAY}}", today or date.today().isoformat())
        .replace("{{GLOSSARY}}", build_glossary())
    )
    try:
        result = clamp_extraction(_call(
            "checkin", system, transcript, CheckinExtraction, effort="low",
            fallback=lambda: offline.extract_checkin(transcript, mode, crisis=keyword_hit),
        ))
    except AiError:
        if not keyword_hit:
            raise
        # The AI failed but the words look like a crisis: never let an outage hide that.
        return CheckinExtraction(
            mood=None, sleepHours=None, sleepQuality=None, stress=None, fatigue=None,
            studyHours=None, workHours=None, tags=[], summary="", dialectTerms=[],
            safety=SafetyFlag(level="crisis", reason="crisis keywords detected"),
        )

    # The code check can only raise the level, never lower what the AI decided.
    if keyword_hit and result.safety.level != "crisis":
        result.safety = SafetyFlag(level="crisis", reason=result.safety.reason or "crisis keywords detected")
    return result


def explain_insights(request: InsightsRequest) -> InsightsResponse:
    """Call 2: calculated patterns -> plain-English insights and advice."""
    system = load_system_prompt("insights-explain").replace("{{MODE}}", request.mode)
    result = _call("insights", system, request.model_dump_json(), InsightsResponse, effort="medium",
                   fallback=lambda: offline.explain_insights(request))
    # Drop any insight that doesn't point at a pattern we actually calculated (no invented findings).
    known = {p.id for p in request.patterns}
    result.insights = [i for i in result.insights if i.patternId in known][:3]
    result.advice = result.advice[:3]
    return result


def explain_recorded_patterns(daily_logs: list[dict], context: InsightsRequest) -> InsightsResponse:
    """Calculate patterns from stored entries and explain them with the supplied context.

    The caller supplies weekly and exam context and must route crisis entries to help
    rather than requesting insights. Raw entry text is not sent to the AI.
    """
    request = context.model_copy(update={"patterns": calculate_user_patterns(daily_logs)})
    return explain_insights(request)


def spoken_reply(entry: CheckinExtraction) -> SpokenReplyResponse:
    """Call 3: one short warm reply. Crisis entries get the fixed message, no AI call."""
    if entry.safety.level == "crisis":
        return SpokenReplyResponse(text=CRISIS_MESSAGE)
    return _call("reply", load_system_prompt("spoken-reply"), entry.model_dump_json(), SpokenReplyResponse, effort="low",
                 fallback=lambda: offline.spoken_reply(entry))


def weekly_summary(request: WeeklySummaryRequest) -> WeeklySummaryResponse:
    """Call 4: this week's entry snapshots -> short round-up for the Insights page."""
    if not request.entries:
        return WeeklySummaryResponse(summary=EMPTY_WEEK_SUMMARY, recurringTopics=[], highlight=None)

    system = (
        load_system_prompt("weekly-summary")
        .replace("{{MODE}}", request.mode)
        .replace("{{ENTRY_COUNT}}", str(len(request.entries)))  # counted in code, not by the AI
    )
    result = _call("weekly", system, request.model_dump_json(), WeeklySummaryResponse, effort="low",
                   fallback=lambda: offline.weekly_summary(request, HELPLINE_LINE))
    result.recurringTopics = [t.lower() for t in result.recurringTopics][:3]
    # A hard week always ends with the helpline, even if the model forgot it.
    if any(e.safetyLevel != "none" for e in request.entries) and "116 123" not in result.summary:
        result.summary = f"{result.summary.rstrip()} {HELPLINE_LINE}"
    return result


def daily_prompt(request: DailyPromptRequest, today: str | None = None) -> DailyPromptResponse:
    """Call 5: one journaling question for today. Never raises: falls back to a default prompt."""
    if request.recent and request.recent[-1].safetyLevel == "crisis":
        return DailyPromptResponse(prompt=CRISIS_DAILY_PROMPT)
    if not request.recent and request.examPhase == "none":
        return DailyPromptResponse(prompt=DEFAULT_DAILY_PROMPT)  # nothing to personalise yet: skip the call

    system = (
        load_system_prompt("daily-prompt")
        .replace("{{MODE}}", request.mode)
        .replace("{{TODAY}}", today or date.today().isoformat())
    )
    return _call("prompt", system, request.model_dump_json(), DailyPromptResponse, effort="low",
                 fallback=lambda: offline.daily_prompt(request, DEFAULT_DAILY_PROMPT))


if __name__ == "__main__":
    # Quick check: python ai_backend/core.py  (offline with no key; uses Claude if ANTHROPIC_API_KEY is set)
    print("AI mode:", ai_mode())
    samples = [
        "Proper knackered, only got about four hours, then sat in the library for five. Canny stressed about the stats exam Tuesday.",
        "Aye it was a canny day, had a lie-in, went to the coast with me marras.",
    ]
    for s in samples:
        entry = extract_checkin(s)
        print(entry.model_dump_json(indent=2))
        print(spoken_reply(entry).text)
