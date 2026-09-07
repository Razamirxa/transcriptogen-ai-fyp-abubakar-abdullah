"""FFmpeg helpers: locate binaries, probe duration, extract audio, split chunks.

We call ffmpeg directly (no moviepy): faster, no Python-side memory footprint,
and no Windows file-handle problems that older projects ran into.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import AUDIO_EXTS, VIDEO_EXTS

_CANDIDATE_DIRS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links"),
    r"C:\ffmpeg\bin",
    r"C:\ffmpeg",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files (x86)\ffmpeg\bin",
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
]


def _works(exe: str | None) -> bool:
    if not exe or not os.path.exists(exe):
        return False
    try:
        r = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _find(tool: str) -> str:
    """Return a working path for ffmpeg / ffprobe or raise a helpful error."""
    names = [tool, f"{tool}.exe"]
    candidates: list[str] = []
    env = os.getenv("FFMPEG_PATH")
    if env:
        if tool in os.path.basename(env).lower():
            candidates.append(env)
        else:
            base = os.path.dirname(env) if os.path.isfile(env) else env
            candidates += [os.path.join(base, n) for n in names]
    w = shutil.which(tool)
    if w:
        candidates.append(w)
    for d in _CANDIDATE_DIRS:
        candidates += [os.path.join(d, n) for n in names]
    for c in candidates:
        if _works(c):
            return c
    raise RuntimeError(
        f"{tool} not found or not working. Install FFmpeg (winget install Gyan.FFmpeg) "
        "or set FFMPEG_PATH in .env."
    )


_cache: dict[str, str] = {}


def ffmpeg() -> str:
    if "ffmpeg" not in _cache:
        _cache["ffmpeg"] = _find("ffmpeg")
    return _cache["ffmpeg"]


def ffprobe() -> str | None:
    if "ffprobe" not in _cache:
        try:
            _cache["ffprobe"] = _find("ffprobe")
        except RuntimeError:
            _cache["ffprobe"] = ""
    return _cache["ffprobe"] or None


def media_kind(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def duration_seconds(path: str | Path) -> float:
    """Duration via ffprobe, falling back to parsing the ffmpeg banner."""
    p = str(path)
    probe = ffprobe()
    if probe:
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", p],
            capture_output=True, text=True, timeout=60,
        )
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    r = subprocess.run([ffmpeg(), "-i", p], capture_output=True, text=True, timeout=60)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        raise RuntimeError(f"Could not read duration of {p}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def extract_audio(src: str | Path, dst: str | Path | None = None, *, bitrate: str = "64k") -> Path:
    """Convert any media to mono 16 kHz MP3: small, fast to upload, API friendly."""
    src = Path(src)
    if dst is None:
        fd, tmp = tempfile.mkstemp(suffix=".mp3", prefix="tg_audio_")
        os.close(fd)
        dst = Path(tmp)
    dst = Path(dst)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", str(src), "-vn",
           "-ac", "1", "-ar", "16000", "-b:a", bitrate, str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[:500]}")
    return dst


@dataclass
class Chunk:
    index: int
    path: Path
    start: float   # seconds offset from the beginning of the original media
    end: float


def split_audio(audio: str | Path, chunk_seconds: int, total: float | None = None) -> list[Chunk]:
    """Cut audio into sequential chunks of chunk_seconds (stream copy, no re-encode)."""
    audio = Path(audio)
    total = total or duration_seconds(audio)
    if total <= chunk_seconds:
        return [Chunk(0, audio, 0.0, total)]
    chunks: list[Chunk] = []
    start = 0.0
    i = 0
    tmpdir = Path(tempfile.mkdtemp(prefix="tg_chunks_"))
    while start < total:
        end = min(start + chunk_seconds, total)
        out = tmpdir / f"chunk_{i:03d}{audio.suffix}"
        cmd = [ffmpeg(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}",
               "-i", str(audio), "-c", "copy", str(out)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg chunking failed: {r.stderr.strip()[:500]}")
        chunks.append(Chunk(i, out, start, end))
        start = end
        i += 1
    return chunks


def safe_unlink(path: str | Path | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass
