# Project Brief

## Highest priorities
The Smart Diary app is aimed to do the following:
- Ask the user about their situation; are they a student? Are they currently employed? Are they currently unemployed?
- A structured entry: mood, sleep, study hours and stress, pulled out of what the user (which may be a student) said.
- Insights from real patterns in their data (for example, mood is lower after nights under 6 hours' sleep), calculated in code and explained in plain English by the AI.
- Exam-aware advice driven by the student's exam calendar: building habits early in term, protecting sleep and revision near exams, recovery afterwards.
- A weekly composition: each week becomes a short piece of music. Mood sets the key, sleep the tempo, stress the tension and study the rhythm, so calm weeks sound calm and exam weeks sound tense.
- A study tracker for students
- Using user data to make connections to negative trends and habits.

## A. Intelligent Onboarding & Demographic Routing

During initial setup, the app classifies the user into one of three primary operating modes:

  Student Mode: Activates the Exam Calendar, Revision Tracker, and Study-to-Rest ratio telemetry.
  
  Employment / Flexible Work Mode: Activates the Work-Pacing Engine, Ergonomic/Shift Fatigue monitor, and Access-to-Work adjustment log.

  Unemployed / Health Recovery Mode: Activates the Micro-Gig Task Matcher, Social Prescribing signposting, and Respite Energy Passport.

B. Structured Micro-Telemetry Entry

Users can complete check-ins via range sliders, multi-select tags, or a 30-second voice memo:

  Core Metrics: Mood (1–10), Sleep (Hours & Quality), Stress (1–10), Physical Pain / Fatigue (1–10), Study / Work Hours.

  Dialect-Aware Voice Ingestion: Voice entries are processed using speech recognition fine-tuned for North East dialects (Geordie, Mackem, Pitmatic) and broader UK informal phrasing ("proper knackered", "canny bad back"), normalizing colloquialisms into clinical/occupational data.

C. Pattern Analysis & Algorithmic Correlation

  Code-Driven Calculations: The backend calculates statistical relationships (e.g., rolling 7-day Pearson correlation between sleep duration and mood/pain thresholds).

  Plain-English AI Explanations: The AI converts computed trends into empathetic, actionable insights (e.g., "Your data shows that whenever your sleep drops below 6 hours for two consecutive nights, your recorded stress spikes by 40% during study sessions.").

D. Exam-Aware Student Guidance & Study Tracker

  Exam Calendar Integration: Students input key revision windows and exam dates.

  Phase-Based Advice Engine:

  Early Term: Encourages habit building, steady study pacing, and consistent sleep baselines.

  Pre-Exam (1–2 Weeks Out): Protects sleep hygiene, prompts stress-reduction breaks, and flags over-study burnout risk.

  Post-Exam Recovery: Prompts cognitive downtime and relaxation logging.

  Revision Tracker: Tracks cumulative study hours against target subjects, showing visual progress bars and recommended rest breaks.

E. Algorithmic Weekly Music Composition

Each week, the backend converts the user's weekly numerical telemetry into a unique, generative 15–30 second audio piece summarizing their week:

Key/Scale: Determined by average Mood (e.g., Major keys for high mood, Minor/Dorian modes for low mood).

Tempo (BPM): Driven by Sleep duration (e.g., >8 hours = steady 90 BPM; <5 hours = hurried 130 BPM).

Tension / Timbre: Controlled by Stress levels (e.g., smooth ambient synths for low stress vs. distorted/dissonant string layers for high stress).

Rhythm / Percussion Complexity: Driven by Study / Work Hours (e.g., light acoustic pulses for low hours vs. complex drum patterns for high study loads).

F. Access-to-Work & Equality Act Passport Generator

Aggregates 7 to 30 days of telemetry into an executive PDF report.

Outlines primary health barriers, trends in physical/cognitive capacity, and evidence-based Reasonable Adjustments (e.g., flexible start times, phased shifts, ergonomic equipment) for UK employers, universities, or DWP Access to Work grant applications.
