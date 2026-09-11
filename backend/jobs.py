"""In-memory transcription job store.

A job runs `GeminiTranscriber.transcribe()` in a worker thread; the HTTP layer
polls its progress (message, fraction, elapsed, ETA). Results are kept in
memory for the life of the process (fine for a single-user / FYP deployment;
swap for Redis + a task queue when there are many users).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from transcriptogen.config import TranscribeOptions
from transcriptogen.generators import ContentGenerator, has_devanagari
from transcriptogen.media import safe_unlink
from transcriptogen.models import TranscriptResult
from transcriptogen.subtitles import cues_from_text, cues_from_words, speaker_transcript, to_srt, to_vtt
from transcriptogen.transcriber import GeminiTranscriber


@dataclass
class Job:
    id: str
    name: str
    path: Path
    opts: TranscribeOptions
    fix_urdu: bool = True
    status: str = "queued"
    message: str = "Queued"
    fraction: float = 0.0
    estimate: float | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    error: str | None = None
    result: TranscriptResult | None = None
    cues: list = field(default_factory=list)

    def progress(self) -> dict[str, Any]:
        now = self.finished or time.time()
        elapsed = now - self.started
        remaining = None
        if self.estimate and self.status == "running":
            remaining = max(self.estimate - elapsed, 0.0)
        frac = self.fraction
        if self.estimate and self.status == "running":
            frac = max(frac, min(elapsed / (self.estimate * 1.15), 0.95))
        if self.status == "done":
            frac = 1.0
        return {
            "id": self.id, "status": self.status, "message": self.message, "fraction": round(frac, 3),
            "elapsed": round(elapsed, 1), "estimate": self.estimate, "remaining": remaining, "error": self.error,
        }


class JobStore:
    def __init__(self, transcriber_factory: Callable[[], GeminiTranscriber] | None = None,
                 generator_factory: Callable[[], ContentGenerator] | None = None):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._make_transcriber = transcriber_factory or GeminiTranscriber
        self._make_generator = generator_factory or ContentGenerator

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def submit(self, path: Path, name: str, opts: TranscribeOptions, fix_urdu: bool = True) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], name=name, path=path, opts=opts, fix_urdu=fix_urdu)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
        job.status = "running"
        job.started = time.time()
        transcriber = self._make_transcriber()

        def progress(msg: str, frac: float) -> None:
            job.message, job.fraction = msg, frac
            job.estimate = transcriber.last_estimate

        try:
            result = transcriber.transcribe(job.path, job.opts, progress)
            cues = cues_from_words(result.words) if result.words else cues_from_text(result.text, result.duration)
            if job.fix_urdu and has_devanagari(result.text):
                job.message = "Converting Hindi script to Urdu..."
                gen = self._make_generator()
                result.text = gen.fix_urdu_script(result.text)
                cues = gen.fix_urdu_script_cues(cues)
            job.result, job.cues = result, cues
            job.status, job.message = "done", "Done"
        except Exception as e:  # surfaced through /jobs/{id}
            job.status, job.error, job.message = "error", str(e), "Failed"
        finally:
            job.finished = time.time()
            safe_unlink(job.path)

    @staticmethod
    def result_payload(job: Job) -> dict[str, Any]:
        r = job.result
        assert r is not None
        cues = job.cues
        return {
            "id": job.id, "name": job.name, "text": r.text,
            "speakers_text": speaker_transcript(r.words) if r.words else "",
            "words": [w.__dict__ for w in r.words],
            "cues": [c.__dict__ for c in cues],
            "srt": to_srt(cues), "vtt": to_vtt(cues),
            "duration": r.duration, "chunks": r.chunks, "speakers": r.speakers,
            "language_codes": r.language_codes, "model": r.model,
            "took_seconds": round((job.finished or time.time()) - job.started, 1), "usage": r.usage,
        }
