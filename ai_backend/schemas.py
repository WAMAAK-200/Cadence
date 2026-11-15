"""Pydantic mirror of src/types/diary.ts (the Lane D contract).

Owned by Lane D. Keep field names identical to diary.ts so the frontend and
backend agree. Change both files together and announce it in the group chat.

Scores are 1-10 integers, None = not mentioned. Range limits are applied in
code (claude_client.clamp_*) rather than in the schema, because structured
outputs ignores numeric min/max constraints.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel

UserMode = Literal["student", "employed", "unemployed"]
SafetyLevel = Literal["none", "concern", "crisis"]
ExamPhase = Literal["early_term", "pre_exam", "exam_period", "post_exam", "none"]
Metric = Literal["sleepHours", "studyHours", "workHours", "stress", "fatigue", "mood"]


# ---------- Call 1: check-in extraction ----------

class SafetyFlag(BaseModel):
    level: SafetyLevel
    reason: Optional[str]


class DialectTerm(BaseModel):
    heard: str
    meaning: str


class CheckinExtraction(BaseModel):
    mood: Optional[int]
    sleepHours: Optional[float]
    sleepQuality: Optional[Literal["poor", "ok", "good"]]
    stress: Optional[int]
    fatigue: Optional[int]
    studyHours: Optional[float]
    workHours: Optional[float]
    tags: List[str]
    summary: str
    dialectTerms: List[DialectTerm]
    safety: SafetyFlag


# ---------- Call 2: insights ----------

class Threshold(BaseModel):
    condition: str
    avgWhenTrue: float
    avgWhenFalse: float


class Pattern(BaseModel):
    """Calculated in code (Lane B), never by the AI."""
    id: str
    x: Metric
    y: Metric
    correlation: float
    sampleSize: int
    threshold: Optional[Threshold] = None


class WeeklyFeatures(BaseModel):
    """Numbers only: this is all the music generator ever sees."""
    weekStart: str
    days: int
    avgMood: Optional[float]
    avgSleepHours: Optional[float]
    avgStress: Optional[float]
    totalStudyOrWorkHours: Optional[float]


class InsightsRequest(BaseModel):
    mode: UserMode
    patterns: List[Pattern]
    examPhase: ExamPhase
    daysToNextExam: Optional[int]
    nextExamSubject: Optional[str]
    last7: WeeklyFeatures


class Insight(BaseModel):
    patternId: str
    title: str
    body: str


class Advice(BaseModel):
    text: str
    why: str


class InsightsResponse(BaseModel):
    insights: List[Insight]
    advice: List[Advice]


# ---------- Call 3: spoken reply ----------

class SpokenReplyResponse(BaseModel):
    text: str


# ---------- Shared input for calls 4 and 5 ----------

class EntrySnapshot(BaseModel):
    """One past entry as the AI sees it: the extracted summary and numbers, never the raw text."""
    date: str
    mood: Optional[int] = None
    stress: Optional[int] = None
    sleepHours: Optional[float] = None
    studyHours: Optional[float] = None
    workHours: Optional[float] = None
    tags: List[str] = []
    summary: str = ""
    safetyLevel: SafetyLevel = "none"


# ---------- Call 4: weekly summary (Insights page) ----------

class WeeklySummaryRequest(BaseModel):
    mode: UserMode
    entries: List[EntrySnapshot]  # this week's entries, oldest first


class WeeklySummaryResponse(BaseModel):
    summary: str  # 2-3 sentences
    recurringTopics: List[str]  # 0-3, each appears in 2+ entries
    highlight: Optional[str]  # one good moment from the week, or None


# ---------- Call 5: daily writing prompt (Smart Assistant drawer) ----------

class DailyPromptRequest(BaseModel):
    mode: UserMode
    examPhase: ExamPhase
    daysToNextExam: Optional[int]
    nextExamSubject: Optional[str]
    recent: List[EntrySnapshot]  # last 3 entries, oldest first (may be empty for new users)


class DailyPromptResponse(BaseModel):
    prompt: str  # one question, max ~25 words
