"""
Audio Processing, Speech-to-Text (Groq Whisper) & Fluency Service
==================================================================
Adapted from BeFluent (stt.py, fluency.py, submissions.py) for the
Academic & Career Copilot SQLite + FastAPI stack.
"""

import os
import re
import time
from typing import Optional

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm", ".ogg"}
MAX_AUDIO_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB
MIN_AUDIO_SIZE_BYTES = 800               # <800 bytes is empty/corrupt
AUDIO_STORAGE_DIR = os.getenv("AUDIO_STORAGE_DIR", "./data/audio_recordings")
AUDIO_RETENTION_HOURS = float(os.getenv("AUDIO_RETENTION_HOURS", "24"))
STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3-turbo")

# Deterministic filler-word list from BeFluent fluency.py
FILLER_WORDS = [
    "you know", "i mean", "sort of", "kind of",
    "um", "umm", "uh", "uhh", "like", "actually", "basically",
]


def save_audio_upload(session_id: str, turn_index: int, filename: str, contents: bytes) -> str:
    """
    Validate and store an uploaded audio recording under a session-scoped directory.
    """
    ext = os.path.splitext(filename or "recording.wav")[1].lower() or ".wav"
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(f"Unsupported audio format '{ext}'. Allowed: {sorted(ALLOWED_AUDIO_EXTENSIONS)}")

    if not contents or len(contents) < MIN_AUDIO_SIZE_BYTES:
        raise ValueError("Audio recording appears empty or too short. Please record at least 1–2 seconds of speech.")

    if len(contents) > MAX_AUDIO_SIZE_BYTES:
        raise ValueError("Audio file exceeds the 15 MB upload limit.")

    sess_dir = os.path.join(AUDIO_STORAGE_DIR, session_id)
    os.makedirs(sess_dir, exist_ok=True)
    safe_name = f"turn_{turn_index}_{int(time.time())}{ext}"
    file_path = os.path.join(sess_dir, safe_name)

    with open(file_path, "wb") as f:
        f.write(contents)

    logger.info(f"Saved audio upload ({len(contents)} bytes) -> {file_path}")
    return file_path


def cleanup_expired_audio() -> int:
    """Delete stored audio files older than AUDIO_RETENTION_HOURS."""
    if not os.path.exists(AUDIO_STORAGE_DIR):
        return 0
    cutoff = time.time() - (AUDIO_RETENTION_HOURS * 3600)
    removed = 0
    for root, dirs, files in os.walk(AUDIO_STORAGE_DIR, topdown=False):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
            except Exception as e:
                logger.warning(f"Audio cleanup error on {fpath}: {e}")
        for dname in dirs:
            dpath = os.path.join(root, dname)
            try:
                if not os.listdir(dpath):
                    os.rmdir(dpath)
            except Exception:
                pass
    if removed:
        logger.info(f"Audio retention policy cleaned up {removed} expired file(s)")
    return removed


def compute_fluency_metrics(transcript: str, duration_seconds: float) -> dict:
    """Compute deterministic speaking rate (WPM) and filler-word counts."""
    words = transcript.split()
    word_count = len(words)
    minutes = max(duration_seconds / 60.0, 1e-6)
    words_per_minute = round(word_count / minutes, 1) if duration_seconds > 0 else 0.0

    lowered = transcript.lower()
    found_fillers: list[str] = []
    total_filler_count = 0

    remaining_text = lowered
    for phrase in FILLER_WORDS:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        matches = re.findall(pattern, remaining_text)
        if matches:
            total_filler_count += len(matches)
            found_fillers.append(phrase)
            remaining_text = re.sub(pattern, " ", remaining_text)

    return {
        "word_count": word_count,
        "words_per_minute": words_per_minute,
        "filler_word_count": total_filler_count,
        "filler_words": found_fillers,
    }


def transcribe_audio_groq(file_path: str) -> dict:
    """
    Transcribe audio via Groq Whisper (whisper-large-v3-turbo), adapted from BeFluent.
    Returns dict with transcript, duration_seconds, confidence, noise_warning, fluency_metrics.
    """
    load_dotenv(override=False)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        raise RuntimeError("GROQ_API_KEY is not configured in .env for Whisper speech-to-text.")

    from groq import Groq
    client = Groq(api_key=api_key)

    last_err: Optional[Exception] = None
    response = None
    for attempt in range(2):
        try:
            with open(file_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model=STT_MODEL,
                    response_format="verbose_json",
                )
            break
        except Exception as e:
            last_err = e
            logger.warning(f"Whisper STT attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                time.sleep(1.0)

    if response is None:
        raise RuntimeError(f"Speech-to-text transcription failed: {last_err}")

    transcript = (getattr(response, "text", "") or "").strip()
    duration = getattr(response, "duration", None)
    segments = getattr(response, "segments", None) or []

    if duration is None:
        if segments:
            last_seg = segments[-1]
            duration = last_seg.get("end", 0.0) if isinstance(last_seg, dict) else getattr(last_seg, "end", 0.0)
        else:
            duration = 0.0
    duration = float(duration or 0.0)

    # Extract confidence and noise metrics from Whisper segments
    confidence = 0.90
    no_speech_prob = 0.0
    if segments:
        logprobs = []
        nsps = []
        for seg in segments:
            alp = seg.get("avg_logprob") if isinstance(seg, dict) else getattr(seg, "avg_logprob", None)
            nsp = seg.get("no_speech_prob") if isinstance(seg, dict) else getattr(seg, "no_speech_prob", None)
            if alp is not None:
                logprobs.append(float(alp))
            if nsp is not None:
                nsps.append(float(nsp))
        if logprobs:
            import math
            avg_lp = sum(logprobs) / len(logprobs)
            # Map avg_logprob (~ -1.5 to -0.05) cleanly to [0.1, 0.99]
            confidence = round(max(0.1, min(0.99, math.exp(avg_lp))), 3)
        if nsps:
            no_speech_prob = round(sum(nsps) / len(nsps), 3)

    noise_warning = None
    if not transcript:
        noise_warning = "No clear speech detected in the recording. Please retry in a quieter environment."
    elif no_speech_prob > 0.65:
        noise_warning = "High background noise or silence detected; transcription accuracy may be reduced."
    elif confidence < 0.45:
        noise_warning = "Low transcription confidence detected. You can review/edit the transcript or re-record."

    fluency = compute_fluency_metrics(transcript, duration)

    return {
        "transcript": transcript,
        "duration_seconds": round(duration, 2),
        "confidence": confidence,
        "no_speech_prob": no_speech_prob,
        "noise_warning": noise_warning,
        "fluency_metrics": fluency,
    }
