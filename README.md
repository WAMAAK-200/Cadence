# Smart Diary (Cadence)

**Cadence** is a Smart Diary app that turns daily check-ins into structured wellbeing telemetry (mood, sleep, stress, study/work), explains real statistical patterns in plain English, provides phase-aware exam guidance, and composes each week into a unique piece of music directly in your browser.

---

## Features

1. **Intelligent Demographic Routing & Onboarding**
   - **Student Mode**: Activates Exam Calendar, Phase-Based Guidance (Early Term, Pre-Exam, Post-Exam), and Revision Goal Tracker.
   - **Employed Mode**: Activates Work-Pacing Engine, Shift Fatigue Monitor, and Reasonable Adjustments log.
   - **Unemployed / Recovery Mode**: Activates Respite Energy Baseline and Social Prescribing signposting.

2. **Structured Micro-Telemetry Entry & Voice Ingestion**
   - 1-tap mood selection with musical tone feedback.
   - Sliders for Sleep duration & quality, Stress (1–10), Fatigue/Pain (1–10), and Study/Work hours.
   - Dialect-aware voice check-in tuned for North East colloquialisms (*proper knackered*, *canny sound*, *buzzing*, *radge*).
   - Instant AI telemetry extraction and spoken empathetic feedback.

3. **Algorithmic Weekly Music Composition**
   - Real-time generative Web Audio synthesizer (`music_synth.js`).
   - **Key / Scale**: Driven by average Mood (Major pentatonic for high mood, Dorian for reflective, Minor harmonic for stress/low mood).
   - **Tempo (BPM)**: Driven by average Sleep duration (>8h = 80–90 BPM, <5h = 130 BPM).
   - **Tension / Timbre**: Modulated by Stress levels (ambient sine waves vs resonant dissonance).
   - **Rhythm Complexity**: Driven by Study / Work hours (sparse pulses vs intricate arpeggios).
   - Real-time oscilloscope waveform canvas visualizer.

4. **Pattern Correlation & Plain-English Insights**
   - Code-calculated rolling Pearson correlations (e.g. sleep vs stress/fatigue).
   - Plain-English actionable advice.
   - Weekly AI summary with recurring topics and positive highlight.

5. **Exam Calendar & Study Tracker**
   - Interactive monthly calendar with day-by-day check-in history.
   - Exam countdown with phase advice (Early Term, Pre-Exam Focus, Exam Period).
   - Subject-specific revision target hours with visual progress bars.

6. **Equality Act & Access to Work Passport**
   - Executive 14–30 day telemetry summary.
   - Outlines primary barriers and evidence-based Reasonable Adjustments for UK universities, employers, or DWP Access to Work applications.

7. **Crisis Safety Net**
   - Automatic screening for crisis language with instant signposting to Samaritans (116 123 free call), university wellbeing services, and 999.

8. **Security & Authentication**
   - Guest mode (`localStorage`) and authenticated accounts (`SQLite` with `bcrypt`/`PBKDF2` hashing and session tokens).

9. **Accessibility (WCAG 2.2 AA)**
   - Font switcher: Sans, Serif (Lora), Mono (Courier Prime).
   - Larger text option, High contrast mode, Wider letter spacing, and Dark mode.

---

## Quick Start

1. Start the unified server:
   ```bash
   python3 security.py
   ```
2. Open your browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```

3. Run integration & unit tests:
   ```bash
   python3 -m unittest test_full_integration.py
   python3 -m unittest discover ai_backend
   ```
