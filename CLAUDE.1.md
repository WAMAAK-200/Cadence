# CLAUDE.md

This file is read by every team member's Claude Code session. Several people are prompting Claude on this repo **at the same time**. Your top priority is to avoid stepping on anyone else's work.

## VITAL: stay in sync with the team at all times

Teammates push constantly. Your memory of this repo goes stale within minutes. **Before EVERY response or action in this repo, without exception:**

1. Run `git fetch --all`, then check `git log --all --oneline -n 10` and `git branch -r` for new commits and branches.
2. If `origin/main` has moved, commit or stash your own work, then run `git pull --rebase origin main`. Never discard or overwrite a teammate's changes.
3. Tell the human in one line what changed since your last check (who, which files), or "No changes".
4. If any of these changed, re-read them before continuing, because they override anything you remember: `CLAUDE.md`, `idea.md`, `PROJECT_BRIEF.md`, `docs/design/DESIGN.md`, `TODO.md`, `src/types/diary.ts`.
5. If a change conflicts with the current task, or touches a file you are editing, **stop and tell the human** before going further.
6. Fetch and rebase again immediately before every push.

Never answer from memory of the repo. Work that teammates have not pushed is invisible to you, so commit and push small changes often.

## The project

**Cadence**: a smart diary for students in the North East that turns their term into music. A student does a 10-second voice check-in about their day; the AI produces:

1. A structured **entry**: mood, sleep, study hours and stress, pulled out of what the student said.
2. **Insights** from real patterns in their data (for example, mood is lower after nights under 6 hours' sleep), calculated in code and explained in plain English by the AI.
3. **Exam-aware advice** driven by the student's exam calendar: building habits early in term, protecting sleep and revision near exams, recovery afterwards.
4. A **weekly composition**: each week becomes a short piece of music. Mood sets the key, sleep the tempo, stress the tension and study the rhythm, so calm weeks sound calm and exam weeks sound tense.

It is wellbeing support, not therapy. It must never diagnose, never promise outcomes and never invent organisations, services or figures. If an entry suggests a crisis, it points to human help (Samaritans 116 123 and the student's university wellbeing service).

- Hackathon: DurHack 2026, Durham University, 14–15 November 2026. Theme: **Composition** (art, music and tech; mixing ideas in new combinations).
- Judging: Creativity and innovation, Technical competence and execution, Research and learning, Polish and completion.
- All code is written during the hackathon (24 hours from 12:00 noon Saturday). **Code freeze at the submission deadline (confirm the exact time on the DurHack schedule).**
- The demo must run live, end to end, on realistic input.

## Project documents (read the relevant one before starting)

| File | What it is for | Owner |
|------|----------------|-------|
| `CLAUDE.md` | How we work: lanes, git rules, guardrails, idea coaching | Lane A |
| `idea.md` | **Source of truth for the product**: flow, features, data needs, AI design | Lane A merges; anyone proposes changes in the group chat |
| `PROJECT_BRIEF.md` | The pitch: problem, past-winner analysis, demo script, Devpost submission checklist | Lane A |
| `docs/design/DESIGN.md` | Visual, sound and interaction rules. **Read before any UI or music work** | Lane C |
| `TODO.md` | Tasks per lane | Each owner ticks only their own section |

If two documents disagree, `idea.md` wins on the product and `CLAUDE.md` wins on process. Tell the human so the other file gets fixed.

## Stack (confirm and edit at the start, then do not change)

- Frontend: React + Vite + TypeScript + Tailwind
- Music: Tone.js, in the browser
- Backend: a small server route that calls the Gemini API (the API key must never reach the browser)
- Voice: browser speech-to-text for the check-in; ElevenLabs for the spoken reply (optional, MLH prize)
- Storage: MongoDB Atlas (MLH prize), or local JSON if Atlas is not ready
- Model name read from `GEMINI_MODEL` in `.env`
- Package manager: npm

Do not introduce new frameworks, libraries or tools without the team agreeing in the group chat first.

## Lanes (who owns what)

Each person works in one lane. **Only edit files inside your own lane.** If a change outside your lane is needed, stop and tell the human so they can ask the owner.

| Lane | Owner | Owns |
|------|-------|------|
| A. Project lead and pull request management | TBC | `src/features/checkin/` (voice check-in UI), `package.json` and lockfile, `README.md`, `src/App.tsx` and routing, `CLAUDE.md`, `idea.md`, `PROJECT_BRIEF.md`, Devpost write-up and pitch |
| B. Research and data | TBC | `docs/research/`, `demo-data/` (fictional students and three weeks of entries, verified support contacts), `src/insights/` (pattern calculations: sleep vs mood, study vs stress, exam countdown) |
| C. UI and sound design | TBC | `docs/design/`, Tailwind config and shared styles, `src/features/insights/`, `src/features/calendar/`, `src/features/composition/` (Tone.js music generator and player) |
| D. AI and API usage | Khaliq | `prompts/`, the Gemini API call code, JSON parsing, cost logging |
| E. Backend flow | TBC | `server/` routes and request flow, storage (Atlas or JSON), safety routing, fallback to cached demo data |

Shared files with a single owner:

- `src/types/diary.ts` is the **contract** between lanes. Owned by Lane D. Nobody else edits it. Changes are announced in the group chat before pushing.
- `package.json` and the lockfile: Lane A merges dependency additions. Ask before adding a package.

## Git rules

1. One person scaffolds and pushes the skeleton. Everyone else clones after that.
2. Work on a branch named after your lane, e.g. `lane-d-ai-api`.
3. `git pull --rebase origin main` before every session and before every push.
4. Commit small and often. Prefix messages with the lane: `[D] parse AI response JSON safely`.
5. Merge to `main` at least every 30 minutes so conflicts stay small.
6. Never force-push to `main`. Never rewrite shared history.
7. Never run a formatter or linter fix across the whole repo. Only format files you touched.
8. If a merge conflict touches another lane's file, keep their version and tell the human.

## Instructions for Claude

- Stay in the lane the human states at the start of the session. If they have not said, ask.
- Make the smallest change that achieves the goal. No unrequested refactors, renames or file moves.
- Do not delete or rewrite code you did not write in this session.
- Before editing a shared or out-of-lane file, stop and ask.
- Comment non-obvious logic so teammates can follow it quickly.
- Always handle loading, error and empty states in UI.
- After each change, tell the human exactly which files you touched.

## Idea coaching (when the team asks for help with the idea or pitch)

There is no secret formula or magic prompt. The team will say plainly what they need, with as much detail as they can. If a request is unclear, ask one short question. Use these methods when asked:

1. **Compare with a winner.** Given our idea and a winning entry, analyse our idea's potential, impact and chance of success against it, side by side, and explain the reasons for each conclusion. If asked for **deep reasoning**, explore trade-offs and less obvious angles; if asked for **raw logic**, be strict and back every point with evidence.
2. **Find the winning strategies, debug us, then adjust.** From the winning entries, identify what made them stand out (tone, structure, presentation, originality, demo, theme fit). When asked to "debug me", list our weaknesses and what to improve. Then show how our idea can adopt those strategies without losing its core. If the team asks for a rewrite or says something sounds off or not like them, revise; don't defend the earlier version.
3. **Rewrite as a past winner.** Rewrite our idea as if it were a past hackathon winner, in the style of a winning write-up (name, one-line pitch, solution, challenges, results), using known winners or a sample the team supplies.
4. **Help us ask better.** If the team is unsure what to ask, suggest a few prompts that would get the best results and let them choose.

Past winners to compare against (add more as the team finds them):

| Year | Place | Project | What it did |
|------|-------|---------|-------------|
| DurHack 2025 | 1st | Clap Collider | Clap or move to create music live (Python, OpenCV, MediaPipe, Strudel) |
| DurHack 2025 | 2nd | Echo | AI soundscapes that change with the scenes of a book |
| DurHack 2024 | 1st | Affirmasaurus | Mental health app with a gesture-controlled quiz and a dinosaur companion |
| DurHack 2024 | 2nd | Projector T-Shirt Machine | Draw with your finger and see it projected onto your shirt using pose detection |
| Other event | Best Overall | CogniFlow | AI companion for the gap between therapy sessions, with a therapist dashboard |

Be honest: say clearly when something is generic or weak, and keep advice achievable before the deadline.

## Secrets and data

- API keys live in `.env` only. `.env` is in `.gitignore`. Keep `.env.example` updated with variable names, never values.
- The repo is public at submission. Assume everything committed is visible.
- **Never use real people's personal data.** Demo data in `demo-data/` must be fictional.
- Diary entries are sensitive. Do not log entry text to the console; log only counts and timings.

## Product guardrails (this is scored)

Mental health tools can do harm through bad advice, false reassurance or missed risk. Therefore the AI prompt must:

- Never diagnose, label conditions or give medical advice.
- Detect possible crisis language and route to human help (Samaritans 116 123, university wellbeing service) instead of continuing the chat.
- Base insights on calculated patterns from the student's own data, never guesses.
- Give small, practical suggestions that fit the student's exam dates and stated workload.
- Point to real support only if it is verified; never invent organisations, services or figures.
- Work on a phone screen.

## AI output contract

The AI must return **JSON only**, matching `src/types/diary.ts`. There are three AI calls: check-in extraction (voice transcript to mood, sleep, study, stress and a safety flag), insight explanation (calculated patterns plus exam countdown to plain-English insights and advice) and the spoken reply (one short, warm response). Lane D strips code fences and parses inside `try/catch`. Lane E's server checks the safety flag before anything else, never sends raw transcripts to the music generator, and falls back to cached data from `demo-data/` if the API fails, so the live demo never breaks.

## Cost tracking

Lane D logs input and output token counts for every AI call to the console. This gives a real cost-per-check-in figure for the pitch and the Devpost write-up.

## Timeline

| Time | Milestone |
|------|-----------|
| Sat 12:00 | Stack confirmed, skeleton pushed, lanes assigned |
| Sat 13:00 | Everyone building in their lane |
| Sat 20:00 | Happy path works end to end (check-in, entry saved, insights, weekly composition plays) |
| Sun 02:00 | Feature freeze. Fix bugs and polish only. Sleep in shifts |
| Sun 09:00 | Full demo rehearsal on the demo machine; record a backup video |
| Deadline | Code freeze. Repo public. Devpost submitted |

After feature freeze, Claude should refuse to start new features and focus on stability.
