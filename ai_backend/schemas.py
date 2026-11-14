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
