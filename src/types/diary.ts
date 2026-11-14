// src/types/diary.ts
// THE CONTRACT between lanes. Owned by Lane D (Khaliq & Warith).
// Do not edit from another lane: propose changes in the group chat first.
//
// Conventions:
// - Scores are integers 1–10 (1 = lowest, 10 = highest). null = the user did not say.
//   The AI must return null rather than guess.
// - Dates are ISO strings "YYYY-MM-DD".
// - Every AI call returns JSON only, matching one of the *Response types below.

// ---------- Users ----------

export type UserMode = 'student' | 'employed' | 'unemployed';

export interface UserProfile {
  id: string;
  displayName: string; // fictional in demo data
  mode: UserMode;
  university?: string; // used for the wellbeing-service signpost
  exams?: ExamDate[]; // student mode only
}

export interface ExamDate {
  subject: string;
  date: string; // YYYY-MM-DD
}

// ---------- Call 1: check-in extraction (voice/text -> structured entry) ----------

export type SafetyLevel = 'none' | 'concern' | 'crisis';

export interface SafetyFlag {
  level: SafetyLevel;
  // Short neutral reason, e.g. "mentions not wanting to be here". Never a diagnosis.
  reason: string | null;
}

export interface DialectTerm {
  heard: string; // e.g. "proper knackered"
  meaning: string; // e.g. "very tired"
}

export interface CheckinExtraction {
  mood: number | null; // 1–10
  sleepHours: number | null; // hours, may be decimal e.g. 5.5
  sleepQuality: 'poor' | 'ok' | 'good' | null;
  stress: number | null; // 1–10
  fatigue: number | null; // 1–10, physical pain / tiredness
  studyHours: number | null;
  workHours: number | null;
  tags: string[]; // short lowercase tags e.g. ["exam", "gym", "social"]
  summary: string; // one neutral sentence in plain English, no diagnosis
  dialectTerms: DialectTerm[]; // NE / informal phrases the model normalised (shown in demo)
  safety: SafetyFlag;
}

export type CheckinResponse = CheckinExtraction;

// A stored diary entry = extraction + metadata. The raw transcript is NOT stored here
// and must never be sent to the music generator.
export interface DiaryEntry extends CheckinExtraction {
  id: string;
  userId: string;
  date: string; // YYYY-MM-DD
  source: 'voice' | 'text' | 'sliders';
}

// ---------- Call 2: insight explanation (calculated patterns -> plain English) ----------

// Patterns are calculated IN CODE (src/insights/, Lane B), never by the AI.
export interface Pattern {
  id: string; // e.g. "sleep-mood"
  x: keyof Pick<CheckinExtraction, 'sleepHours' | 'studyHours' | 'workHours' | 'stress' | 'fatigue' | 'mood'>;
  y: keyof Pick<CheckinExtraction, 'sleepHours' | 'studyHours' | 'workHours' | 'stress' | 'fatigue' | 'mood'>;
  correlation: number; // Pearson r, -1..1
  sampleSize: number; // number of days used
  // Optional threshold finding, e.g. "after nights under 6h, mood averaged 4.1 vs 6.8"
  threshold?: { condition: string; avgWhenTrue: number; avgWhenFalse: number };
}

export type ExamPhase = 'early_term' | 'pre_exam' | 'exam_period' | 'post_exam' | 'none';

export interface InsightsRequest {
  mode: UserMode;
  patterns: Pattern[];
  examPhase: ExamPhase;
  daysToNextExam: number | null;
  nextExamSubject: string | null;
  last7: WeeklyFeatures;
}

export interface Insight {
  patternId: string; // must match a Pattern.id that was provided
  title: string; // max ~8 words
  body: string; // 1–2 sentences, cites the actual numbers given
}

export interface Advice {
  text: string; // one small, practical action
  why: string; // links to a pattern or the exam phase
}

export interface InsightsResponse {
  insights: Insight[]; // 0–3
  advice: Advice[]; // 1–3
}

// ---------- Call 3: spoken reply ----------

export interface SpokenReplyResponse {
  text: string; // 1–2 warm sentences, max ~35 words, read aloud (ElevenLabs optional)
}

// ---------- Weekly composition input (Lane C, Tone.js) ----------

// Numbers only. No transcript or summary text ever goes to the music generator.
export interface WeeklyFeatures {
  weekStart: string; // YYYY-MM-DD
  days: number; // days with an entry
  avgMood: number | null; // -> key / scale
  avgSleepHours: number | null; // -> tempo
  avgStress: number | null; // -> tension / timbre
  totalStudyOrWorkHours: number | null; // -> rhythm complexity
}

// ---------- Cost logging ----------

export type AiCallName = 'checkin' | 'insights' | 'reply';

export interface AiUsageLog {
  call: AiCallName;
  model: string;
  inputTokens: number;
  outputTokens: number;
  ms: number;
  ok: boolean; // false if we fell back to demo data
}
