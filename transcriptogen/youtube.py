"""Download audio from YouTube / other yt-dlp supported URLs."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .media import ffmpeg

_URL_RE = re.compile(r"^https?://", re.I)


def is_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip()))


def download_audio(
    url: str,
    out_dir: str | Path | None = None,
    *,
    max_minutes: int | None = None,
) -> tuple[Path, dict]:
    """Return (path to mp3, info dict with title/duration/id)."""
    import yt_dlp  # lazy import keeps app start-up fast

    out_dir = Path(out_dir or tempfile.mkdtemp(prefix="tg_yt_"))
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ffmpeg_location": str(Path(ffmpeg()).parent),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "96"}
        ],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        minutes = (info.get("duration") or 0) / 60
        if max_minutes and minutes > max_minutes:
            raise ValueError(f"Video is {minutes:.0f} min long; the limit is {max_minutes} min.")
        ydl.download([url])
    path = out_dir / f"{info['id']}.mp3"
    if not path.exists():
        cands = list(out_dir.glob(f"{info['id']}.*"))
        if not cands:
            raise RuntimeError("yt-dlp finished but no audio file was produced")
        path = cands[0]
    return path, {"title": info.get("title"), "duration": info.get("duration"), "id": info.get("id")}
