"""Lane D: offline engine. Same inputs and outputs as the Claude calls in core.py, no API key.

Used when ANTHROPIC_API_KEY is missing, AI_MODE=offline, or a Claude call fails,
so the live demo always works. It is rule-based (dialect lexicon + regex +
templates), NOT an AI: say "offline mode" in the demo, don't call it Claude.

Same guarantees as the AI path: never diagnoses, only quotes numbers it was
given or found, crisis handling is decided in core.py before this runs.
"""

import csv
import re
from collections import Counter
from pathlib import Path

try:
    from .schemas import (
        Advice, CheckinExtraction, DailyPromptRequest, DailyPromptResponse, DialectTerm, Insight,
        InsightsRequest, InsightsResponse, SafetyFlag, SpokenReplyResponse, WeeklySummaryRequest,
        WeeklySummaryResponse,
    )
except ImportError:
    from schemas import (
        Advice, CheckinExtraction, DailyPromptRequest, DailyPromptResponse, DialectTerm, Insight,
        InsightsRequest, InsightsResponse, SafetyFlag, SpokenReplyResponse, WeeklySummaryRequest,
        WeeklySummaryResponse,
    )

HERE = Path(__file__).resolve().parent

# ---------- Lexicon ----------
# Weights are rough: +1/-1 per word, intensifiers add 1 more. Dialect first, then standard English.

MOOD_UP = ["canny day", "canny good", "feeling canny", "felt canny", "was canny", "canny weekend", "chuffed", "mint", "champion", "lush",
           "buzzing", "sound", "great", "good day", "happy", "lovely", "fun", "brilliant", "nice", "relaxed",
           "calm", "proud", "excited", "cracking"]
MOOD_DOWN = ["gutted", "minging", "out of sorts", "down in the dumps", "fed up", "awful", "terrible", "rubbish",
             "bad day", "sad", "down", "miserable", "low", "lonely", "upset", "crying", "rough", "grim", "hopeless"]
STRESS_WORDS = ["stressed", "stress", "anxious", "worried", "worrying", "nervous", "bricking it", "panicking",
                "panic", "overwhelmed", "radge", "radgie", "head's melted", "heads melted", "under pressure",
                "deadline", "cramming", "burnout", "stressed to the nines"]
CALM_WORDS = ["relaxed", "calm", "chilled", "chill", "easy day", "no stress", "stress free"]
FATIGUE_WORDS = ["knackered", "shattered", "wrecked", "done in", "exhausted", "tired", "drained", "dog-tired",
                 "on my last legs", "heavy legs", "no energy", "badly", "poorly", "swimming head", "all-nighter"]
INTENSIFIERS = ["proper", "dead", "geet", "really", "so", "very", "well", "totally", "completely", "canny"]
CONCERN_WORDS = ["hopeless", "worthless", "can't cope", "cannot cope", "can't do this", "no one to talk to",
                 "nobody to talk to", "no one cares", "nobody cares", "pointless", "falling apart"]

TAGS = {
    "exam": ["exam", "revision", "revise", "revising", "cramming", "test"],
    "study": ["library", "lecture", "seminar", "essay", "assignment", "coursework", "study", "studied", "uni"],
    "work": ["shift", "work", "boss", "job"],
    "social": ["marra", "marras", "mates", "friends", "pub", "party", "night out", "wor lass"],
    "family": ["bairn", "mam", "dad", "family", "nana", "grandma"],
    "exercise": ["gym", "run", "football", "swim", "walk", "training"],
    "outdoors": ["coast", "beach", "park", "walk", "quayside"],
    "money": ["skint", "rent", "money", "bills"],
    "alcohol": ["mortal", "bladdered", "smashed", "drunk", "hungover", "hanging"],
    "sleep": ["lie-in", "nap", "insomnia", "couldn't sleep"],
}

NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "a couple of": 2, "couple of": 2,
                "a couple": 2}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, NUMBER_WORDS), key=len, reverse=True)) + r")"
_HALF = r"(?:\s*(?:and a half|½))?"

SLEEP_CUES = ["sleep", "slept", "kip", "bed", "lie-in", "night"]
STUDY_CUES = ["library", "revis", "study", "studied", "lecture", "essay", "assignment", "coursework", "reading", "cramming"]
WORK_CUES = ["shift", "work", "worked", "job"]


def _has(text: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z'])" + re.escape(phrase) + r"(?![a-z])", text) is not None


def _count(text: str, words) -> int:
    return sum(1 for w in words if _has(text, w))


def _to_num(raw: str, half: bool) -> float:
    n = float(raw) if raw[0].isdigit() else float(NUMBER_WORDS[raw])
    return n + 0.5 if half else n


def _clauses(text: str):
    return [c.strip() for c in re.split(r"[,.;!?]|\bthen\b|\bbut\b|\band then\b", text) if c.strip()]


def _hours(text: str):
    """Find sleep / study / work hours clause by clause. Returns (sleep, study, work)."""
    sleep = study = work = None
    if _has(text, "all-nighter") or _has(text, "all nighter") or _has(text, "no sleep") or _has(text, "didn't sleep"):
        sleep = 0.0
    prev_cue = None  # "did three hours" after "...my revision" belongs to the previous clause's topic
    for clause in _clauses(text):
        cue = ("study" if any(c in clause for c in STUDY_CUES) else
               "work" if any(c in clause for c in WORK_CUES) else
               "sleep" if any(c in clause for c in SLEEP_CUES) else None)
        m = re.search(_NUM + _HALF + r"\s*(?:hours?|hrs?|h)\b", clause) or \
            re.search(r"\bfor (?:about |around |like )?" + _NUM + _HALF + r"\b", clause)
        if m:
            value = _to_num(m.group(1), "half" in m.group(0) or "½" in m.group(0))
        elif re.search(r"\bhalf an hour\b", clause):
            value = 0.5
        elif re.search(r"\b(an|a single) hour\b", clause):
            value = 1.0
        else:
            prev_cue = cue or prev_cue
            continue
        topic = cue or prev_cue
        if topic is None and re.search(r"\b(got|had|only)\b", clause):
            topic = "sleep"  # "only got about four hours" with no other cue almost always means sleep
        if topic == "study":
            study = value if study is None else study
        elif topic == "work":
            work = value if work is None else work
        elif topic == "sleep":
            sleep = value if sleep is None else sleep
        prev_cue = cue or prev_cue
    return sleep, study, work


def _score(base_hits: int, intensity: int, sign: int = 1):
    """Turn word hits into a 1-10 score around 5. None when there were no hits."""
    if base_hits == 0:
        return None
    return max(1, min(10, 5 + sign * (2 * base_hits + intensity)))


def _intensity(text: str, words) -> int:
    """+1 for each intensifier directly before one of the given words."""
    hits = 0
    for w in words:
        for i in INTENSIFIERS:
            if _has(text, f"{i} {w}"):
                hits += 1
    return hits


_GLOSSARY = None


def glossary_pairs():
    """(phrase, meaning) pairs from colloquialisms_dataset.csv + prompts/ne-dialect-glossary.md."""
    global _GLOSSARY
    if _GLOSSARY is not None:
        return _GLOSSARY
    pairs = []
    csv_path = HERE / "colloquialisms_dataset.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                pairs.append((row["term"].lower(), row["standard_meaning"].split(",")[0].strip().lower()))
    md = HERE.parent / "prompts" / "ne-dialect-glossary.md"
    if md.exists():
        for line in md.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] not in ("Phrase", "") and not set(cells[0]) <= {"-"}:
                for phrase in cells[0].split(","):
                    phrase = phrase.split("(")[0].strip().lower()
                    if phrase:
                        pairs.append((phrase, cells[1].lower()))
    # Longest first so "proper knackered" wins over "knackered".
    _GLOSSARY = sorted(set(pairs), key=lambda p: -len(p[0]))
    return _GLOSSARY


_CANNY_NOUNS = {"day", "time", "night", "lass", "lad", "bit", "one", "weekend", "week", "walk"}


def _dialect_terms(text: str):
    """Dialect phrases found in the text, as (heard, meaning). Each stretch of text is used once."""
    found, spans, seen = [], [], set()
    for phrase, meaning in glossary_pairs():
        if phrase in seen:
            continue
        # allow an intensifier in front ("proper knackered") and a plural s ("marras")
        pattern = r"(?<![a-z'])((?:proper|dead|geet|canny|really) )?" + re.escape(phrase) + r"s?(?![a-z])"
        m = re.search(pattern, text)
        if not m or any(m.start() < e and s < m.end() for s, e in spans):
            continue
        if phrase == "canny":
            # "canny stressed" = very stressed; "canny day" / "feeling canny" = nice
            nxt = re.match(r"\s+([a-z']+)", text[m.end():])
            meaning = "very" if nxt and nxt.group(1) not in _CANNY_NOUNS else "nice, good"
        elif m.group(1) and not meaning.startswith(("very", "extremely", "completely")):
            meaning = "very " + meaning
        found.append(DialectTerm(heard=m.group(0), meaning=meaning))
        spans.append((m.start(), m.end()))
        seen.add(phrase)
        if len(found) >= 6:
            break
    # "canny stressed" should read as one phrase: merge "canny" with the word after it
    for t in found:
        if t.heard == "canny" and t.meaning == "very":
            nxt = re.search(r"canny\s+([a-z']+)", text)
            if nxt:
                t.heard, t.meaning = f"canny {nxt.group(1)}", f"very {nxt.group(1)}"
    return found


def _fmt(h: float) -> str:
    return str(int(h)) if float(h).is_integer() else f"{h:g}"


# ---------- Call 1 ----------

def extract_checkin(transcript: str, mode: str = "student", crisis: bool = False) -> CheckinExtraction:
    text = transcript.lower().replace("’", "'")
    sleep, study, work = _hours(text)

    up, down = _count(text, MOOD_UP), _count(text, MOOD_DOWN)
    stress_hits, calm_hits = _count(text, STRESS_WORDS), _count(text, CALM_WORDS)
    fatigue_hits = _count(text, FATIGUE_WORDS)

    mood = None
    if up or down:
        mood = max(1, min(10, 5 + 2 * (up - down) + _intensity(text, MOOD_UP) - _intensity(text, MOOD_DOWN)))
    stress = _score(stress_hits, _intensity(text, STRESS_WORDS)) if stress_hits else (_score(calm_hits, 1, -1) if calm_hits else None)
    fatigue = _score(fatigue_hits, _intensity(text, FATIGUE_WORDS))
    # Very short sleep with no mood words: a tired day, not a neutral one.
    if mood is None and sleep is not None and sleep < 5 and (fatigue or stress):
        mood = 4

    sleep_quality = None
    if sleep is not None:
        sleep_quality = "poor" if sleep < 6 else ("good" if sleep >= 7.5 else "ok")
    if _has(text, "lie-in") or _has(text, "slept well") or _has(text, "great sleep"):
        sleep_quality = "good"
    if _has(text, "couldn't sleep") or _has(text, "slept badly") or _has(text, "rubbish sleep"):
        sleep_quality = "poor"

    tags = [tag for tag, words in TAGS.items() if any(_has(text, w) for w in words)][:5]

    concern = _count(text, CONCERN_WORDS) > 0
    if crisis:
        safety = SafetyFlag(level="crisis", reason="crisis keywords detected")
    elif concern:
        safety = SafetyFlag(level="concern", reason="mentions feeling unable to cope")
    else:
        safety = SafetyFlag(level="none", reason=None)

    # One neutral sentence built only from what was found.
    parts = []
    if sleep is not None:
        parts.append("did not sleep" if sleep == 0 else f"slept about {_fmt(sleep)} hours")
    if study is not None:
        parts.append(f"studied for {_fmt(study)} hours")
    if work is not None:
        parts.append(f"worked for {_fmt(work)} hours")
    feelings = []
    if fatigue and fatigue >= 7:
        feelings.append("very tired")
    if stress and stress >= 7:
        feelings.append("stressed")
    if mood and mood >= 7:
        feelings.append("in a good mood")
    if mood and mood <= 3:
        feelings.append("low")
    if feelings:
        parts.append("felt " + " and ".join(feelings))
    if _has(text, "lie-in"):
        parts.append("had a lie-in")
    if "social" in tags:
        parts.append("spent time with friends")
    if "exercise" in tags:
        parts.append("did some exercise")
    if "exam" in tags:
        parts.append("mentioned an exam")
    if crisis:
        summary = "Said things that suggest they may not be safe."
    elif parts:
        summary = (", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]).capitalize() + "."
    else:
        summary = "Shared a short check-in."

    return CheckinExtraction(
        mood=mood, sleepHours=sleep, sleepQuality=sleep_quality, stress=stress, fatigue=fatigue,
        studyHours=study if mode == "student" or study is not None else None, workHours=work,
        tags=tags, summary=summary, dialectTerms=_dialect_terms(text), safety=safety,
    )


# ---------- Call 2 ----------

_LABELS = {"sleepHours": "sleep", "studyHours": "study time", "workHours": "work hours",
           "stress": "stress", "fatigue": "tiredness", "mood": "mood"}

_PHASE_ADVICE = {
    "early_term": ("Pick a regular bedtime and keep it for the next five nights.", "Early term is the easiest time to set a sleep baseline."),
    "pre_exam": ("Plan tomorrow's revision in 50-minute blocks with a proper break between each.", "Your exams are close, and short blocks are easier to keep up than long sessions."),
    "exam_period": ("Keep tonight simple: food, a short walk, and bed at your usual time.", "Rest between exams protects your next one."),
    "post_exam": ("Do one thing this week just because you enjoy it.", "Exams are done, so this is recovery time."),
    "none": ("Try one 10-minute walk outside today.", "A small, easy step is enough."),
}


def explain_insights(request: InsightsRequest) -> InsightsResponse:
    insights = []
    for p in request.patterns:
        if p.sampleSize < 5 or abs(p.correlation) < 0.3:
            continue
        x, y = _LABELS.get(p.x, p.x), _LABELS.get(p.y, p.y)
        direction = "lower" if p.correlation < 0 else "higher"
        strength = "strong" if abs(p.correlation) >= 0.6 else "moderate"
        body = (f"Across {p.sampleSize} days, on days with more {x} your {y} was usually {direction} "
                f"(a {strength} link, r = {p.correlation:.2f}). This is a pattern, not proof of cause.")
        if p.threshold:
            body = (f"{p.threshold.condition}: your {y} averaged {p.threshold.avgWhenTrue:g}, "
                    f"compared with {p.threshold.avgWhenFalse:g} otherwise, across {p.sampleSize} days.")
        insights.append(Insight(patternId=p.id, title=f"More {x}, {direction} {y}".capitalize(), body=body))
    insights = insights[:3]

    advice = []
    text, why = _PHASE_ADVICE.get(request.examPhase, _PHASE_ADVICE["none"])
    if request.examPhase in ("pre_exam", "exam_period") and request.nextExamSubject and request.daysToNextExam is not None:
        why = f"{request.nextExamSubject} is in {request.daysToNextExam} days. " + why
    advice.append(Advice(text=text, why=why))
    if any(p.x == "sleepHours" or p.y == "sleepHours" for p in request.patterns if abs(p.correlation) >= 0.3):
        advice.append(Advice(text="Aim for at least 7 hours tonight, even if it means stopping revision earlier.",
                             why="Your own data links sleep with how you feel."))
    if request.last7.avgStress is not None and request.last7.avgStress >= 8:
        advice.append(Advice(text="Talk to someone you trust, or your university wellbeing service, this week.",
                             why=f"Your stress has averaged {request.last7.avgStress:g} out of 10 this week."))
    return InsightsResponse(insights=insights, advice=advice[:3])


# ---------- Call 3 ----------

def spoken_reply(entry: CheckinExtraction) -> SpokenReplyResponse:
    if entry.safety.level == "concern":
        text = "That sounds like a lot to carry, pet. It might help to talk to someone you trust or your uni wellbeing service."
    elif entry.sleepHours == 0:
        text = "No sleep at all, that's rough. Keep today as gentle as you can and get to bed early tonight."
    elif entry.sleepHours is not None and entry.sleepHours < 5:
        text = f"Only {_fmt(entry.sleepHours)} hours, that's rough. Go easy on yourself today and try for an earlier night."
    elif entry.stress and entry.stress >= 7:
        text = "Sounds like a stressful one. You checked in anyway, and that counts. Take a proper break when you can."
    elif entry.mood and entry.mood >= 7:
        text = "Sounds like a canny day, nice one. Hope you can have a few more like that this week."
    elif entry.fatigue and entry.fatigue >= 7:
        text = "You sound worn out. Rest is part of the work, so be kind to yourself tonight."
    else:
        text = "Thanks for checking in. Every entry helps your week take shape."
    return SpokenReplyResponse(text=text)


# ---------- Call 4 ----------

def weekly_summary(request: WeeklySummaryRequest, helpline_line: str) -> WeeklySummaryResponse:
    entries = request.entries
    n = len(entries)
    sentences = [f"You checked in {n} time{'s' if n != 1 else ''} this week."]

    stressed = [e for e in entries if e.stress is not None]
    if stressed:
        worst = max(stressed, key=lambda e: e.stress)
        avg = sum(e.stress for e in stressed) / len(stressed)
        sentences.append(f"Stress averaged {avg:.1f} out of 10, highest on {worst.date} at {worst.stress}.")
    slept = [e.sleepHours for e in entries if e.sleepHours is not None]
    if slept:
        sentences.append(f"You slept {sum(slept) / len(slept):.1f} hours a night on average.")
    summary = " ".join(sentences[:3])
    if any(e.safetyLevel != "none" for e in entries):
        summary = f"{summary} {helpline_line}"

    counts = Counter(t.lower() for e in entries for t in set(e.tags))
    topics = [t for t, c in counts.most_common() if c >= 2][:3]

    happy = [e for e in entries if e.mood is not None and e.mood >= 7 and e.summary and e.safetyLevel == "none"]
    highlight = max(happy, key=lambda e: e.mood).summary if happy else None
    return WeeklySummaryResponse(summary=summary, recurringTopics=topics, highlight=highlight)


# ---------- Call 5 ----------

def daily_prompt(request: DailyPromptRequest, default_prompt: str) -> DailyPromptResponse:
    last = request.recent[-1] if request.recent else None
    if last and last.safetyLevel == "concern":
        return DailyPromptResponse(prompt="What is one kind thing you could do for yourself this evening?")
    if request.examPhase in ("pre_exam", "exam_period") and request.nextExamSubject and request.daysToNextExam is not None:
        days = request.daysToNextExam
        when = "tomorrow" if days == 1 else ("today" if days == 0 else f"in {days} days")
        return DailyPromptResponse(prompt=f"With {request.nextExamSubject} {when}, what does a realistic, kind revision day look like for you?")
    if request.examPhase == "post_exam":
        return DailyPromptResponse(prompt="Exams are done. What is something you've been putting off that you'd actually enjoy?")
    if last and last.stress is not None and last.stress >= 7:
        return DailyPromptResponse(prompt="Yesterday sounded intense. What is one thing that helped, even a little?")
    if last and last.sleepHours is not None and last.sleepHours < 6:
        return DailyPromptResponse(prompt="How did you feel today after a short night, and what would help you sleep better tonight?")
    if last and last.mood is not None and last.mood >= 7:
        return DailyPromptResponse(prompt="Yesterday sounded like a good one. What made it work, and can you do a bit of that again?")
    return DailyPromptResponse(prompt=default_prompt)
