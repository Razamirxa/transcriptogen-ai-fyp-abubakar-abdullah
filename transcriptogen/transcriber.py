"""Audio -> text with Gemini 3.5 Transcribe through the Interactions API.

Reference: https://ai.google.dev/gemini-api/docs/transcribe

    interaction = client.interactions.create(
        model="gemini-3.5-transcribe",
        input=[{"type": "audio", "uri": f.uri, "mime_type": f.mime_type}],
        generation_config={"transcription_config": {
            "language_codes": ["ur-PK"],
            "mode": {"type": "verbatim",
                     "diarization_mode": "speaker",
                     "timestamp_granularities": ["word"]},
        }},
    )
    interaction.output_text                      # full transcript
    interaction.steps[].content[].annotations[]  # word_info: text/start_offset/end_offset/speaker
"""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from typing import Any, Callable

from google import genai

from . import config
from .config import TranscribeOptions
from .media import Chunk, duration_seconds, extract_audio, media_kind, safe_unlink, split_audio
from .models import TranscriptResult, Word

ProgressCb = Callable[[str, float], None]


def _noop(_msg: str, _frac: float) -> None:  # default progress callback
    pass


# ----------------------------------------------------------------------------
# Request building
# ----------------------------------------------------------------------------
def build_transcription_config(opts: TranscribeOptions) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if opts.language_codes:
        cfg["language_codes"] = list(opts.language_codes)
    if opts.smart_mode:
        cfg["mode"] = {"type": "smart"}
        if opts.custom_vocabulary:
            cfg["custom_vocabulary"] = list(opts.custom_vocabulary)[:1000]
        return cfg
    mode: dict[str, Any] = {"type": "verbatim"}
    if opts.diarization:
        mode["diarization_mode"] = "speaker"
    if opts.word_timestamps:
        mode["timestamp_granularities"] = ["word"]
    cfg["mode"] = mode
    # custom vocabulary is incompatible with diarization / timestamps
    if opts.custom_vocabulary and not (opts.diarization or opts.word_timestamps):
        cfg["custom_vocabulary"] = list(opts.custom_vocabulary)[:1000]
    return cfg


# ----------------------------------------------------------------------------
# Response parsing
# ----------------------------------------------------------------------------
_OFFSET_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(ms|s)?\s*$")


def parse_offset(value: Any) -> float:
    """Accepts "0.100s", "250ms", 1.5, timedelta or None and returns seconds."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "total_seconds"):
        return float(value.total_seconds())
    m = _OFFSET_RE.match(str(value))
    if not m:
        return 0.0
    num, unit = m.groups()
    return float(num) / 1000.0 if unit == "ms" else float(num)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def normalise_speaker(raw: Any) -> str | None:
    """Map API labels ("spk_1", "spk:0", "SPEAKER_2") to "Speaker N" (1-based)."""
    if not raw:
        return None
    s = str(raw)
    m = re.search(r"(\d+)", s)
    if not m:
        return s
    n = int(m.group(1))
    if ":" in s or n == 0:      # zero-based variants
        n += 1
    return f"Speaker {n}"


def extract_words(interaction: Any, offset: float = 0.0) -> list[Word]:
    """Collect word_info annotations from steps[].content[].annotations[]."""
    words: list[Word] = []
    for step in _get(interaction, "steps", None) or []:
        for content in _get(step, "content", None) or []:
            for ann in _get(content, "annotations", None) or []:
                if _get(ann, "type") != "word_info":
                    continue
                text = (_get(ann, "text") or "").strip()
                if not text:
                    continue
                words.append(
                    Word(
                        text=text,
                        start=parse_offset(_get(ann, "start_offset")) + offset,
                        end=parse_offset(_get(ann, "end_offset")) + offset,
                        speaker=normalise_speaker(_get(ann, "speaker")),
                    )
                )
    return words


def _usage_dict(interaction: Any) -> dict[str, Any]:
    u = _get(interaction, "usage")
    if u is None:
        return {}
    if hasattr(u, "model_dump"):
        try:
            return u.model_dump(exclude_none=True)
        except Exception:
            pass
    return dict(u) if isinstance(u, dict) else {"raw": str(u)}


_RETRYABLE = ("429", "500", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED")
# Billing problems also come back as 429 but never recover by retrying.
# (Free-tier quota messages mention "billing details" too, so match only the prepaid wording.)
_BILLING = ("credits are depleted", "prepayment credit")


class BillingError(RuntimeError):
    """Raised when the Gemini project has no credits / billing is not enabled."""


def _is_quota(e: Exception) -> bool:
    low = str(e).lower()
    return "429" in low or "quota" in low or "resource_exhausted" in low or "free_tier" in low


def _classify(e: Exception) -> str:
    msg = str(e).lower()
    if any(b in msg for b in _BILLING):
        return "billing"
    if any(c.lower() in msg for c in _RETRYABLE):
        return "retry"
    return "fatal"


# ----------------------------------------------------------------------------
# Client wrapper
# ----------------------------------------------------------------------------
class GeminiTranscriber:
    """Transcription client that rotates to the next API key on quota / billing errors."""

    def __init__(self, api_key: str | None = None, model: str = config.TRANSCRIBE_MODEL,
                 api_keys: list[str] | None = None):
        keys = list(api_keys or config.get_api_keys())
        if api_key:
            keys = [api_key] + [k for k in keys if k != api_key]
        self.keys = keys
        self._ki = 0
        self._clients: dict[str, genai.Client] = {}
        self.model = model

    @property
    def client(self) -> genai.Client:
        key = self.keys[self._ki]
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def _next_key(self) -> bool:
        if self._ki + 1 < len(self.keys):
            self._ki += 1
            return True
        return False

    # -- low level -----------------------------------------------------------
    def _audio_part(self, path: Path) -> tuple[dict[str, Any], str | None]:
        """Inline small files, upload big ones via the Files API.

        Returns (interaction input part, remote file name or None).
        """
        mime = config.MIME_BY_EXT.get(path.suffix.lower(), "audio/mpeg")
        if path.stat().st_size <= config.INLINE_LIMIT_BYTES:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            return {"type": "audio", "data": data, "mime_type": mime}, None
        f = self.client.files.upload(file=str(path), config={"mime_type": mime})
        for _ in range(150):  # wait until ACTIVE (max ~5 min)
            state = str(getattr(f, "state", "") or "").upper()
            if "PROCESSING" not in state:
                break
            time.sleep(2)
            f = self.client.files.get(name=f.name)
        if "FAILED" in str(getattr(f, "state", "") or "").upper():
            raise RuntimeError("Gemini Files API failed to process the upload.")
        return {"type": "audio", "uri": f.uri, "mime_type": f.mime_type or mime}, f.name

    def transcribe_chunk(
        self,
        path: str | Path,
        opts: TranscribeOptions,
        *,
        offset: float = 0.0,
        retries: int = 3,
    ) -> tuple[str, list[Word], dict[str, Any]]:
        """Transcribe one file that is already inside the model's duration limit."""
        path = Path(path)
        cfg = build_transcription_config(opts)
        errors: list[str] = []
        while True:
            # Files uploaded with one key are not visible to another, so (re)build the part per key.
            part, remote = self._audio_part(path)
            switch = False
            try:
                for attempt in range(retries):
                    try:
                        interaction = self.client.interactions.create(
                            model=self.model,
                            input=[part],
                            generation_config={"transcription_config": cfg},
                        )
                        text = (getattr(interaction, "output_text", None) or "").strip()
                        return text, extract_words(interaction, offset), _usage_dict(interaction)
                    except Exception as e:
                        kind = _classify(e)
                        short = str(e).split("{")[0].strip()[:120]
                        if kind == "billing":
                            errors.append(f"key#{self._ki + 1}: billing ({short})")
                            switch = True
                            break
                        if kind == "retry":
                            if _is_quota(e):          # daily/rate quota -> try the next key
                                errors.append(f"key#{self._ki + 1}: quota ({short})")
                                switch = True
                                break
                            if attempt < retries - 1:
                                time.sleep(5 * (2 ** attempt))
                                continue
                        raise
            finally:
                if remote:
                    try:
                        self.client.files.delete(name=remote)
                    except Exception:
                        pass
            if not (switch and self._next_key()):
                break
        raise BillingError(
            "Transcription failed on every configured API key:\n  " + "\n  ".join(errors)
            + "\n-> open https://ai.studio/projects, add credits / check quota for the key's project "
            "(gemini-3.5-transcribe is a paid model), or add another key as GEMINI_API_KEY_2 in .env."
        )

    # -- high level ----------------------------------------------------------
    def transcribe(
        self,
        media_path: str | Path,
        opts: TranscribeOptions | None = None,
        progress: ProgressCb = _noop,
    ) -> TranscriptResult:
        """Full pipeline: any audio/video file -> TranscriptResult (chunked when long)."""
        opts = opts or TranscribeOptions()
        media_path = Path(media_path)
        if media_kind(media_path) == "unknown":
            raise ValueError(f"Unsupported file type: {media_path.suffix}")

        progress("Reading media info...", 0.02)
        total = duration_seconds(media_path)

        progress("Extracting / normalising audio with FFmpeg...", 0.05)
        audio = extract_audio(media_path)
        tmp_paths: list[Path] = [audio]
        try:
            chunks: list[Chunk] = split_audio(audio, opts.chunk_minutes * 60, total)
            if len(chunks) > 1:
                tmp_paths += [c.path for c in chunks]

            texts: list[str] = []
            words: list[Word] = []
            usage: dict[str, Any] = {}
            n = len(chunks)
            for c in chunks:
                frac = 0.15 + 0.8 * (c.index / n)
                progress(f"Transcribing chunk {c.index + 1}/{n} ({c.start / 60:.0f}-{c.end / 60:.0f} min)...", frac)
                t, w, u = self.transcribe_chunk(c.path, opts, offset=c.start)
                texts.append(t)
                words.extend(w)
                for k, v in u.items():
                    if isinstance(v, (int, float)):
                        usage[k] = usage.get(k, 0) + v
            progress("Done", 1.0)
            return TranscriptResult(
                text="\n\n".join(t for t in texts if t),
                words=words,
                duration=total,
                model=self.model,
                chunks=n,
                language_codes=list(opts.language_codes),
                usage=usage,
            )
        finally:
            for p in tmp_paths:
                safe_unlink(p)
