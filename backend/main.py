"""TranscriptoGen AI - HTTP + WebSocket API and static web app.

    uv run uvicorn backend.main:app --reload --port 8000

Endpoints (all JSON unless noted):
  GET  /api/health                      liveness + key/ffmpeg status
  GET  /api/config                      models, language lists, limits
  POST /api/transcribe                  multipart: file + settings fields  -> {job_id}
  POST /api/transcribe/url              JSON {url, ...settings}            -> {job_id}
  GET  /api/jobs/{id}                   progress (message, fraction, elapsed, estimate, remaining)
  GET  /api/jobs/{id}/result            transcript, words, cues, srt, vtt
  GET  /api/jobs/{id}/download/{fmt}    txt | speakers | srt | vtt
  POST /api/images/analyse              multipart: images[] + language     -> ImageExtraction
  POST /api/images/ask                  multipart: images[] + question (+ context, language)
  POST /api/generate/translate          {text, target, cues?}              -> text (+ srt/vtt)
  POST /api/generate/quiz               {text, n, difficulty, language}
  POST /api/generate/notes              {text, language}   (summary notes)
  POST /api/generate/points             {text, language}   (point-wise notes)
  POST /api/generate/minutes            {text, language}   (minutes of meeting)
  WS   /ws/live?lang=ur-PK              binary PCM 16 kHz mono in -> {"text","final"} JSON out
  GET  /                                the web app (frontend/)
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from transcriptogen import config
from transcriptogen.config import LANGUAGE_OPTIONS, TRANSLATION_TARGETS, TranscribeOptions
from transcriptogen.generators import (
    ContentGenerator,
    image_extraction_to_markdown,
    minutes_to_markdown,
    notes_to_markdown,
    point_notes_to_markdown,
    quiz_to_markdown,
)
from transcriptogen.media import ffmpeg, media_kind
from transcriptogen.subtitles import Cue, to_srt, to_vtt
from transcriptogen.youtube import download_audio, is_url

from . import schemas as S
from .jobs import JobStore

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "2048"))
OUTPUT_LANGS = ["English", "Urdu", "Arabic"]

app = FastAPI(title="TranscriptoGen AI API", version="1.0.0",
              description="Transcription, subtitles, translation, quiz, notes, minutes and image understanding.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
jobs = JobStore()


def _gen() -> ContentGenerator:
    return ContentGenerator()


def _settings(language_codes: str, diarization: bool, word_timestamps: bool, smart_mode: bool,
              custom_vocabulary: str) -> TranscribeOptions:
    codes = [c.strip() for c in language_codes.split(",") if c.strip()] if language_codes else []
    vocab = [v.strip() for v in custom_vocabulary.split(",") if v.strip()] if custom_vocabulary else []
    return TranscribeOptions(language_codes=codes, diarization=diarization and not smart_mode,
                             word_timestamps=word_timestamps and not smart_mode, smart_mode=smart_mode,
                             custom_vocabulary=vocab)


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    try:
        keys = len(config.get_api_keys())
    except RuntimeError:
        keys = 0
    try:
        ff = bool(ffmpeg())
    except RuntimeError:
        ff = False
    return {"ok": keys > 0 and ff, "keys_configured": keys, "ffmpeg": ff}


@app.get("/api/config", response_model=S.ConfigOut)
def get_config() -> S.ConfigOut:
    try:
        keys = len(config.get_api_keys())
    except RuntimeError:
        keys = 0
    from transcriptogen.live import LIVE_MODEL
    return S.ConfigOut(
        transcribe_model=config.TRANSCRIBE_MODEL, text_model=config.TEXT_MODEL, live_model=LIVE_MODEL,
        language_options=LANGUAGE_OPTIONS, translation_targets=TRANSLATION_TARGETS,
        output_languages=OUTPUT_LANGS, max_upload_mb=MAX_UPLOAD_MB, keys_configured=keys,
    )


# ---------------------------------------------------------------------------
# transcription jobs
# ---------------------------------------------------------------------------
@app.post("/api/transcribe")
async def transcribe_upload(
    file: UploadFile = File(...),
    language_codes: str = Form("ur-PK,en-US"),
    diarization: bool = Form(True),
    word_timestamps: bool = Form(True),
    smart_mode: bool = Form(False),
    custom_vocabulary: str = Form(""),
    fix_urdu_script: bool = Form(True),
) -> dict:
    suffix = Path(file.filename or "upload").suffix.lower()
    if media_kind("x" + suffix) == "unknown":
        raise HTTPException(400, f"Unsupported file type: {suffix or '(none)'}")
    fd, tmp = tempfile.mkstemp(suffix=suffix, prefix="tg_up_")
    os.close(fd)
    size = 0
    with open(tmp, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                out.close()
                os.unlink(tmp)
                raise HTTPException(413, f"File larger than {MAX_UPLOAD_MB} MB")
            out.write(chunk)
    opts = _settings(language_codes, diarization, word_timestamps, smart_mode, custom_vocabulary)
    job = jobs.submit(Path(tmp), Path(file.filename or "upload").stem, opts, fix_urdu_script)
    return {"job_id": job.id}


@app.post("/api/transcribe/url")
def transcribe_url(req: S.TranscribeUrlRequest) -> dict:
    if not is_url(req.url):
        raise HTTPException(400, "Not a valid http(s) URL")
    try:
        path, info = download_audio(req.url)
    except Exception as e:
        raise HTTPException(400, f"Download failed: {e}") from e
    opts = TranscribeOptions(language_codes=req.language_codes, diarization=req.diarization and not req.smart_mode,
                             word_timestamps=req.word_timestamps and not req.smart_mode, smart_mode=req.smart_mode,
                             custom_vocabulary=req.custom_vocabulary)
    job = jobs.submit(path, (info.get("title") or "youtube")[:80], opts, req.fix_urdu_script)
    return {"job_id": job.id, "title": info.get("title"), "duration": info.get("duration")}


@app.get("/api/jobs/{job_id}", response_model=S.JobProgress)
def job_progress(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    return job.progress()


@app.get("/api/jobs/{job_id}/result", response_model=S.TranscriptOut)
def job_result(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")
    if job.status == "error":
        raise HTTPException(500, job.error or "Transcription failed")
    if job.status != "done":
        raise HTTPException(409, "Job not finished yet")
    return jobs.result_payload(job)


@app.get("/api/jobs/{job_id}/download/{fmt}")
def job_download(job_id: str, fmt: str):
    job = jobs.get(job_id)
    if not job or job.status != "done":
        raise HTTPException(404, "No finished job with that id")
    p = jobs.result_payload(job)
    body = {"txt": p["text"], "speakers": p["speakers_text"], "srt": p["srt"], "vtt": p["vtt"]}.get(fmt)
    if body is None:
        raise HTTPException(400, "fmt must be txt, speakers, srt or vtt")
    ext = "txt" if fmt in ("txt", "speakers") else fmt
    name = f"{job.name}.{'speakers.' if fmt == 'speakers' else ''}{ext}"
    return PlainTextResponse(body, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------
@app.post("/api/generate/translate", response_model=S.TranslateResponse)
def generate_translate(req: S.TranslateRequest) -> dict:
    gen = _gen()
    out: dict = {"text": gen.translate(req.text, req.target)}
    if req.cues:
        cues = [Cue(c.index, c.start, c.end, c.text, c.speaker) for c in req.cues]
        tr = gen.translate_cues(cues, req.target)
        out.update(cues=[c.__dict__ for c in tr], srt=to_srt(tr), vtt=to_vtt(tr))
    return out


@app.post("/api/generate/quiz", response_model=S.MarkdownResponse)
def generate_quiz(req: S.QuizRequest) -> dict:
    q = _gen().quiz(req.text, n=req.n, difficulty=req.difficulty, language=req.language)
    return {"markdown": quiz_to_markdown(q), "data": q.model_dump()}


@app.post("/api/generate/notes", response_model=S.MarkdownResponse)
def generate_notes(req: S.TextRequest) -> dict:
    n = _gen().notes(req.text, language=req.language)
    return {"markdown": notes_to_markdown(n), "data": n.model_dump()}


@app.post("/api/generate/points", response_model=S.MarkdownResponse)
def generate_points(req: S.TextRequest) -> dict:
    p = _gen().point_notes(req.text, language=req.language)
    return {"markdown": point_notes_to_markdown(p), "data": p.model_dump()}


@app.post("/api/generate/minutes", response_model=S.MarkdownResponse)
def generate_minutes(req: S.TextRequest) -> dict:
    m = _gen().meeting_minutes(req.text, language=req.language)
    return {"markdown": minutes_to_markdown(m, date=str(date.today())), "data": m.model_dump()}


# ---------------------------------------------------------------------------
# images
# ---------------------------------------------------------------------------
async def _read_images(images: list[UploadFile]) -> list[tuple[bytes, str]]:
    if not images:
        raise HTTPException(400, "Upload at least one image")
    if len(images) > 10:
        raise HTTPException(400, "At most 10 images")
    out = []
    for f in images:
        data = await f.read()
        if not data:
            continue
        out.append((data, f.content_type or "image/jpeg"))
    return out


@app.post("/api/images/analyse", response_model=S.MarkdownResponse)
async def images_analyse(images: list[UploadFile] = File(...), language: str = Form("English")) -> dict:
    payload = await _read_images(images)
    x = _gen().analyse_images(payload, language=language)
    return {"markdown": image_extraction_to_markdown(x), "data": x.model_dump()}


@app.post("/api/images/ask", response_model=S.ImageAskResponse)
async def images_ask(images: list[UploadFile] = File(...), question: str = Form(...),
                     context: str = Form(""), language: str = Form("English")) -> dict:
    payload = await _read_images(images)
    return {"answer": _gen().ask_images(payload, question, language=language, context=context)}


# ---------------------------------------------------------------------------
# live captions (WebSocket): client streams 16 kHz mono s16le PCM as binary
# frames; server sends {"text": ..., "final": bool}. Send the text "end" to
# finish the stream.
# ---------------------------------------------------------------------------
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket, lang: str = "", smart: bool = False):
    from transcriptogen.live import transcribe_stream

    await ws.accept()
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def frames():
        while True:
            chunk = await queue.get()
            if chunk is None:
                return
            yield chunk

    async def reader():
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if (b := msg.get("bytes")) is not None:
                    await queue.put(b)
                elif (t := msg.get("text")) and t.strip().lower() in ("end", "stop"):
                    break
        finally:
            await queue.put(None)

    reader_task = asyncio.create_task(reader())
    try:
        codes = [c.strip() for c in lang.split(",") if c.strip()]
        async for ev in transcribe_stream(frames(), language_codes=codes, smart=smart, manual_vad=False):
            await ws.send_text(json.dumps({"text": ev.text, "final": ev.final}))
        await ws.send_text(json.dumps({"done": True}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
        except Exception:
            pass
    finally:
        reader_task.cancel()
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# static web app
# ---------------------------------------------------------------------------
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND / "index.html")
