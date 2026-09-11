"""API tests (no Gemini calls): health/config, upload validation, job lifecycle with a fake transcriber."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.jobs import JobStore
from transcriptogen.models import TranscriptResult, Word


class FakeTranscriber:
    last_estimate = 3.0

    def transcribe(self, path, opts, progress):
        progress("Reading media info...", 0.02)
        progress("Transcribing chunk 1/1...", 0.5)
        return TranscriptResult(
            text="Hello world. This is a test.",
            words=[Word("Hello", 0.1, 0.4, "Speaker 1"), Word("world.", 0.5, 0.9, "Speaker 1"),
                   Word("This", 1.2, 1.4, "Speaker 2"), Word("is", 1.4, 1.5, "Speaker 2"),
                   Word("a", 1.5, 1.6, "Speaker 2"), Word("test.", 1.6, 2.0, "Speaker 2")],
            duration=2.5, model="fake", chunks=1, language_codes=list(opts.language_codes),
        )


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(backend_main, "jobs", JobStore(transcriber_factory=FakeTranscriber))
    return TestClient(backend_main.app)


def _wait(client, job_id, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = client.get(f"/api/jobs/{job_id}").json()
        if p["status"] in ("done", "error"):
            return p
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_health_and_config(client):
    h = client.get("/api/health").json()
    assert set(h) == {"ok", "keys_configured", "ffmpeg"}
    c = client.get("/api/config").json()
    assert c["transcribe_model"] == "gemini-3.5-transcribe"
    assert "Urdu + English (mixed)" in c["language_options"]
    assert "Urdu" in c["translation_targets"]


def test_upload_rejects_unknown_type(client):
    r = client.post("/api/transcribe", files={"file": ("notes.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 400


def test_upload_job_lifecycle(client, tmp_path: Path):
    r = client.post(
        "/api/transcribe",
        files={"file": ("lecture.wav", b"RIFF....WAVEfmt ", "audio/wav")},
        data={"language_codes": "en-US", "diarization": "true", "word_timestamps": "true"},
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    p = _wait(client, job_id)
    assert p["status"] == "done" and p["fraction"] == 1.0
    res = client.get(f"/api/jobs/{job_id}/result").json()
    assert res["text"].startswith("Hello world")
    assert res["speakers"] == ["Speaker 1", "Speaker 2"]
    assert len(res["cues"]) == 2 and res["srt"].startswith("1\n00:00:00,100 --> 00:00:00,900")
    assert "WEBVTT" in res["vtt"] and res["language_codes"] == ["en-US"]
    # downloads
    assert client.get(f"/api/jobs/{job_id}/download/srt").text == res["srt"]
    assert "Speaker 2: This is a test." in client.get(f"/api/jobs/{job_id}/download/speakers").text
    assert client.get(f"/api/jobs/{job_id}/download/pdf").status_code == 400


def test_unknown_job(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/result").status_code == 404


def test_url_endpoint_validates(client):
    assert client.post("/api/transcribe/url", json={"url": "not a url"}).status_code == 400


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "TranscriptoGen" in r.text
