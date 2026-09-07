"""Plain data structures shared by the pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Word:
    text: str
    start: float          # seconds
    end: float            # seconds
    speaker: str | None = None


@dataclass
class TranscriptResult:
    text: str
    words: list[Word] = field(default_factory=list)
    duration: float | None = None
    model: str = ""
    chunks: int = 1
    language_codes: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def speakers(self) -> list[str]:
        seen: list[str] = []
        for w in self.words:
            if w.speaker and w.speaker not in seen:
                seen.append(w.speaker)
        return seen

    @property
    def has_timestamps(self) -> bool:
        return bool(self.words) and any(w.end > 0 for w in self.words)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
