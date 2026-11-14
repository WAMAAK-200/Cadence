# Who works on what

## Frontend - Yahya

## Backend - Tom

## AI - Warith & Khaliq

### Voice check-ins

Install the `elevenlabs` Python package and set `ELEVENLABS_API_KEY` on the server.
Pass an open binary audio file to `ai_backend.core.transcribe_audio`, let the user
review the transcript, then pass the confirmed text to `extract_checkin` and check
its safety level. `process_recording` is available for immediate processing without
review and returns the entry and `spoken_reply`; crisis replies use the fixed message.
The caller owns the file and must obtain consent, validate uploads, and handle `AiError`.
Do not log audio or transcripts. The recording UI and server endpoint are not included.