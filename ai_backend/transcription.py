import os

try:
    from .core import AiError
except ImportError:
    from core import AiError


def transcribe_audio(audio_file) -> str:
    """Transcribe a binary audio file; the caller owns and closes the file."""
    if not os.getenv("ELEVENLABS_API_KEY"):
        raise AiError("transcription: ELEVENLABS_API_KEY is not configured")
    try:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        transcription = client.speech_to_text.convert(file=audio_file, model_id="scribe_v1")
    except Exception as e:
        raise AiError(f"transcription: {type(e).__name__}") from e
    text = getattr(transcription, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise AiError("transcription: empty transcript")
    return text


def process_recording(audio_file, mode: str = "student", today: str | None = None):
    """Convenience flow; use transcribe_audio first when transcript review is needed."""
    try:
        from .core import process_recording as process
    except ImportError:
        from core import process_recording as process
    return process(audio_file, mode=mode, today=today)