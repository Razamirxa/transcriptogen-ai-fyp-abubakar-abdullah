"""Request / response models for the HTTP API."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---- transcription ----------------------------------------------------------
class TranscribeSettings(BaseModel):
    language_codes: list[str] = Field(default_factory=lambda: ["ur-PK", "en-US"])
    diarization: bool = True
    word_timestamps: bool = True
    smart_mode: bool = False
    custom_vocabulary: list[str] = Field(default_factory=list)
    fix_urdu_script: bool = True


class TranscribeUrlRequest(TranscribeSettings):
    url: str


class WordOut(BaseModel):
    text: str
    start: float
    end: float
    speaker: str | None = None


class CueOut(BaseModel):
    index: int
    start: float
    end: float
    text: str
    speaker: str | None = None


class JobProgress(BaseModel):
    id: str
    status: Literal["queued", "running", "done", "error"]
    message: str = ""
    fraction: float = 0.0
    elapsed: float = 0.0
    estimate: float | None = None
    remaining: float | None = None
    error: str | None = None


class TranscriptOut(BaseModel):
    id: str
    name: str
    text: str
    speakers_text: str
    words: list[WordOut]
    cues: list[CueOut]
    srt: str
    vtt: str
    duration: float | None
    chunks: int
    speakers: list[str]
    language_codes: list[str]
    model: str
    took_seconds: float
    usage: dict[str, Any] = Field(default_factory=dict)


# ---- generation -------------------------------------------------------------
class TextRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str = "English"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1)
    target: str = "Urdu"
    cues: list[CueOut] | None = None


class TranslateResponse(BaseModel):
    text: str
    cues: list[CueOut] | None = None
    srt: str | None = None
    vtt: str | None = None


class QuizRequest(TextRequest):
    n: int = Field(5, ge=3, le=20)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class MarkdownResponse(BaseModel):
    markdown: str
    data: dict[str, Any]


# ---- images -----------------------------------------------------------------
class ImageAskResponse(BaseModel):
    answer: str


# ---- misc -------------------------------------------------------------------
class ConfigOut(BaseModel):
    transcribe_model: str
    text_model: str
    live_model: str
    language_options: dict[str, list[str]]
    translation_targets: list[str]
    output_languages: list[str]
    max_upload_mb: int
    keys_configured: int
