"""Real-time transcription with gemini-3.5-transcribe-live (Live API, WebSocket).

Reference: https://ai.google.dev/gemini-api/docs/live-api/live-transcribe

    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        input_audio_transcription=types.AudioTranscriptionConfig(language_codes=["ur-PK"]),
    )
    async with client.aio.live.connect(model="gemini-3.5-transcribe-live", config=config) as s:
        await s.send_realtime_input(audio=types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
        ...
        r.server_content.interim_input_transcription.text   # partial
        r.server_content.input_transcription.text           # final

Limits: 10 minutes per session, no speaker diarization, no word timestamps.
Audio must be raw 16-bit PCM, mono, 16 kHz.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Iterable

from google import genai
from google.genai import types

from . import config
from .media import ffmpeg

LIVE_MODEL = os.getenv("TRANSCRIBE_LIVE_MODEL", "gemini-3.5-transcribe-live")
SAMPLE_RATE = 16_000
BYTES_PER_100MS = SAMPLE_RATE * 2 // 10   # 16-bit mono


@dataclass
class LiveEvent:
    text: str
    final: bool


def file_to_pcm(path: str | Path) -> bytes:
    """Decode any audio/video file to 16 kHz mono s16le PCM using FFmpeg."""
    r = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        capture_output=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.decode(errors='ignore')[:300]}")
    return r.stdout


def _live_config(
    language_codes: list[str], smart: bool, vocabulary: list[str], manual_vad: bool
) -> types.LiveConnectConfig:
    kwargs: dict = {"language_codes": list(language_codes)}
    if smart:
        kwargs["mode"] = "SMART"
    if vocabulary:
        kwargs["custom_vocabulary"] = list(vocabulary)[:1000]
    cfg: dict = {
        "response_modalities": ["TEXT"],
        "input_audio_transcription": types.AudioTranscriptionConfig(**kwargs),
    }
    if manual_vad:
        # Automatic VAD occasionally drops the word right at a segment boundary
        # (seen with file playback). With VAD off we mark one long activity.
        cfg["realtime_input_config"] = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
        )
    return types.LiveConnectConfig(**cfg)


async def transcribe_stream(
    chunks: Iterable[bytes] | AsyncIterator[bytes],
    *,
    language_codes: list[str] | None = None,
    smart: bool = False,
    vocabulary: list[str] | None = None,
    api_key: str | None = None,
    realtime: bool = False,
    manual_vad: bool = True,
    idle_timeout: float = 8.0,
) -> AsyncIterator[LiveEvent]:
    """Stream PCM chunks (16 kHz mono s16le) and yield interim/final transcript events.

    `chunks` may be a sync iterable (e.g. slices of a file) or an async iterator
    (e.g. microphone frames). With realtime=True the sender paces file audio at
    real speed; leave it False to push a file as fast as the server accepts.
    manual_vad=True (default, best for files) disables server VAD and wraps the
    whole stream in one activity, which avoids dropped words at segment edges;
    use manual_vad=False for an open microphone so the server segments turns.
    The generator stops after `idle_timeout` seconds with no new events once
    the audio has ended.
    """
    client = genai.Client(api_key=api_key or config.get_api_key())
    cfg = _live_config(language_codes or [], smart, vocabulary or [], manual_vad)
    queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue()
    mime = f"audio/pcm;rate={SAMPLE_RATE}"

    async with client.aio.live.connect(model=LIVE_MODEL, config=cfg) as session:

        async def sender() -> None:
            if manual_vad:
                await session.send_realtime_input(activity_start=types.ActivityStart())
            if hasattr(chunks, "__aiter__"):
                async for c in chunks:  # type: ignore[union-attr]
                    await session.send_realtime_input(audio=types.Blob(data=c, mime_type=mime))
            else:
                for c in chunks:  # type: ignore[union-attr]
                    await session.send_realtime_input(audio=types.Blob(data=c, mime_type=mime))
                    await asyncio.sleep(len(c) / (SAMPLE_RATE * 2) if realtime else 0.01)
            if manual_vad:
                await session.send_realtime_input(activity_end=types.ActivityEnd())
            await session.send_realtime_input(audio_stream_end=True)

        async def receiver() -> None:
            try:
                async for r in session.receive():
                    sc = r.server_content
                    if not sc:
                        continue
                    if sc.interim_input_transcription and sc.interim_input_transcription.text:
                        await queue.put(LiveEvent(sc.interim_input_transcription.text, False))
                    if sc.input_transcription and sc.input_transcription.text:
                        await queue.put(LiveEvent(sc.input_transcription.text, True))
            finally:
                await queue.put(None)

        send_task = asyncio.create_task(sender())
        recv_task = asyncio.create_task(receiver())
        try:
            while True:
                timeout = idle_timeout if send_task.done() else None
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if ev is None:
                    break
                yield ev
        finally:
            for t in (send_task, recv_task):
                if not t.done():
                    t.cancel()


def pcm_chunks(pcm: bytes, chunk_bytes: int = BYTES_PER_100MS) -> Iterable[bytes]:
    for i in range(0, len(pcm), chunk_bytes):
        yield pcm[i:i + chunk_bytes]


async def transcribe_file_live(path: str | Path, **kw) -> str:
    """Convenience: stream a file through the live model and return the final text."""
    finals: list[str] = []
    async for ev in transcribe_stream(pcm_chunks(file_to_pcm(path)), realtime=kw.pop("realtime", False), **kw):
        if ev.final:
            finals.append(ev.text)
    return " ".join(finals).strip()
