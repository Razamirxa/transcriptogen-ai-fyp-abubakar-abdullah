"""Build subtitle cues (SRT / VTT) from word-level timestamps."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Word


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str
    speaker: str | None = None


def fmt_time(t: float, sep: str = ",", *, ms: bool = True) -> str:
    """Seconds -> HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (VTT); ms=False drops millis."""
    total_ms = int(round(max(0.0, t) * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, millis = divmod(rem, 1000)
    base = f"{h:02d}:{m:02d}:{s:02d}"
    return f"{base}{sep}{millis:03d}" if ms else base


def cues_from_words(
    words: list[Word],
    *,
    max_chars: int = 84,
    max_duration: float = 6.0,
    max_gap: float = 1.0,
    split_on_speaker: bool = True,
) -> list[Cue]:
    """Group timed words into readable cues.

    A new cue starts when the speaker changes, the pause between words is
    longer than max_gap, the cue would exceed max_chars, or it would run
    longer than max_duration.
    """
    cues: list[Cue] = []
    buf: list[Word] = []

    def flush() -> None:
        if not buf:
            return
        text = " ".join(w.text for w in buf).strip()
        end = max(buf[-1].end, buf[0].start + 0.3)
        cues.append(Cue(len(cues) + 1, buf[0].start, end, text, buf[0].speaker))
        buf.clear()

    for w in words:
        if not w.text:
            continue
        if buf:
            prev = buf[-1]
            new_len = len(" ".join(x.text for x in buf)) + 1 + len(w.text)
            if (
                (split_on_speaker and w.speaker != prev.speaker)
                or (w.start - prev.end) > max_gap
                or new_len > max_chars
                or (w.end - buf[0].start) > max_duration
            ):
                flush()
        buf.append(w)
    flush()
    return cues


def cues_from_text(text: str, duration: float | None, *, seconds_per_line: float = 5.0) -> list[Cue]:
    """Fallback when no word timestamps exist: spread lines evenly over the duration."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    per = (duration / len(lines)) if duration else seconds_per_line
    t = 0.0
    cues: list[Cue] = []
    for i, ln in enumerate(lines, 1):
        cues.append(Cue(i, t, t + per, ln))
        t += per
    return cues


def to_srt(cues: list[Cue], *, with_speaker: bool = True) -> str:
    out = []
    for c in cues:
        label = f"{c.speaker}: " if (with_speaker and c.speaker) else ""
        out.append(f"{c.index}\n{fmt_time(c.start, ',')} --> {fmt_time(c.end, ',')}\n{label}{c.text}\n")
    return "\n".join(out)


def to_vtt(cues: list[Cue], *, with_speaker: bool = True) -> str:
    out = ["WEBVTT", ""]
    for c in cues:
        label = f"<v {c.speaker}>" if (with_speaker and c.speaker) else ""
        out.append(f"{fmt_time(c.start, '.')} --> {fmt_time(c.end, '.')}\n{label}{c.text}\n")
    return "\n".join(out)


def speaker_transcript(words: list[Word]) -> str:
    """Readable transcript: one paragraph per speaker turn, prefixed with a timestamp."""
    if not words:
        return ""
    paras: list[str] = []
    cur_spk = words[0].speaker
    cur_start = words[0].start
    buf: list[str] = []
    for w in words:
        if w.speaker != cur_spk and buf:
            paras.append(f"[{fmt_time(cur_start, ms=False)}] {cur_spk or 'Speaker'}: {' '.join(buf)}")
            buf, cur_spk, cur_start = [], w.speaker, w.start
        buf.append(w.text)
    paras.append(f"[{fmt_time(cur_start, ms=False)}] {cur_spk or 'Speaker'}: {' '.join(buf)}")
    return "\n\n".join(paras)
