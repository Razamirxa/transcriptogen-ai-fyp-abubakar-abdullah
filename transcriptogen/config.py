"""Central configuration (env driven)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Model used for audio -> text (Interactions API).
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gemini-3.5-transcribe")
# Model used for translation / quiz / summary (generate_content API).
# gemini-2.5-flash is closed to new API keys (404); Google recommends gemini-3.6-flash.
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.6-flash")
# Used for the final retry when TEXT_MODEL is overloaded (503 "high demand").
TEXT_FALLBACK_MODEL = os.getenv("TEXT_FALLBACK_MODEL", "gemini-3.5-flash")

# Gemini 3.5 Transcribe limits (unary requests).
MAX_MINUTES_PLAIN = 60          # no diarization / timestamps
MAX_MINUTES_ANNOTATED = 30      # diarization or word timestamps enabled
# We chunk a little below the hard limits to stay safe.
CHUNK_MINUTES_PLAIN = 55
CHUNK_MINUTES_ANNOTATED = 25

# Files API: inline bytes are fine below ~20 MB, otherwise upload.
INLINE_LIMIT_BYTES = 15 * 1024 * 1024

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".webm", ".aiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v"}

MIME_BY_EXT = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/m4a",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
    ".aiff": "audio/aiff",
}

# BCP-47 hints offered in the UI. Empty list = automatic detection.
# Urdu and Hindi sound alike, so auto-detect can pick Hindi (Devanagari);
# the default hint is therefore Urdu + English, and Devanagari output is
# converted to Urdu script automatically (see generators.fix_urdu_script).
LANGUAGE_OPTIONS = {
    "Urdu + English (mixed)": ["ur-PK", "en-US"],
    "Urdu": ["ur-PK"],
    "Auto-detect": [],
    "English (US)": ["en-US"],
    "English (UK)": ["en-GB"],
    "Arabic": ["ar-SA"],
    "Hindi": ["hi-IN"],
    "Punjabi": ["pa-IN"],
    "Spanish": ["es-ES"],
    "French": ["fr-FR"],
    "German": ["de-DE"],
    "Chinese (Mandarin)": ["cmn-Hans-CN"],
    "Japanese": ["ja-JP"],
    "Turkish": ["tr-TR"],
}

TRANSLATION_TARGETS = [
    "Urdu", "English", "Arabic", "Hindi", "Punjabi", "Spanish", "French",
    "German", "Chinese (Simplified)", "Japanese", "Turkish", "Persian", "Bengali",
]


@dataclass
class TranscribeOptions:
    """User-selectable knobs for a transcription run."""

    language_codes: list[str] = field(default_factory=list)
    diarization: bool = True
    word_timestamps: bool = True
    smart_mode: bool = False           # smart mode is exclusive with diarization/timestamps
    custom_vocabulary: list[str] = field(default_factory=list)

    @property
    def annotated(self) -> bool:
        return (self.diarization or self.word_timestamps) and not self.smart_mode

    @property
    def chunk_minutes(self) -> int:
        return CHUNK_MINUTES_ANNOTATED if self.annotated else CHUNK_MINUTES_PLAIN


# Text models tried in order when the previous one hits a quota / availability error.
TEXT_MODEL_CANDIDATES = [
    m.strip()
    for m in os.getenv(
        "TEXT_MODEL_CANDIDATES",
        f"{TEXT_MODEL},{TEXT_FALLBACK_MODEL},gemini-3.5-flash-lite,gemini-3.1-flash-lite",
    ).split(",")
    if m.strip()
]


def _valid(key: str | None) -> bool:
    return bool(key) and not key.startswith(("PASTE_", "your_"))


def get_api_keys() -> list[str]:
    """All configured keys, primary first.

    Sources (in order): GEMINI_API_KEYS (comma separated), GEMINI_API_KEY,
    GEMINI_API_KEY_2 ... GEMINI_API_KEY_9, GOOGLE_API_KEY. Duplicates removed.
    Extra keys from other AI Studio projects act as fallbacks when the primary
    project hits its daily free-tier quota or runs out of credits.
    """
    raw: list[str] = []
    raw += [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",")]
    raw.append(os.getenv("GEMINI_API_KEY", ""))
    raw += [os.getenv(f"GEMINI_API_KEY_{i}", "") for i in range(2, 10)]
    raw.append(os.getenv("GOOGLE_API_KEY", ""))
    keys: list[str] = []
    for k in raw:
        if _valid(k) and k not in keys:
            keys.append(k)
    if not keys:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Put it in the .env file "
            "(get one at https://aistudio.google.com/app/apikey)."
        )
    return keys


def get_api_key() -> str:
    return get_api_keys()[0]
