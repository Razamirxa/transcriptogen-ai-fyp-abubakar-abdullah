# TranscriptoGen AI 🎧

**FYP (BSSE, Minhaj University Lahore)** — Abubakar Khan (2022F-mulbsswe-036) & Muhammad Abdullah (2022F-mulbsswe-029)
Supervisor: Maya Bint Yousaf · Co-supervisor: Misbah Akram

A web-based AI platform that turns any video/audio (file or YouTube link) into:

| Feature | How |
|---|---|
| **Transcription** (85+ languages, Urdu/English code-switching) | `gemini-3.5-transcribe` via the **Interactions API** |
| **Speaker diarization** | `diarization_mode: "speaker"` → `Speaker 1`, `Speaker 2`… |
| **Real subtitle timing** (SRT / WebVTT) | word-level timestamps (`timestamp_granularities: ["word"]`) grouped into readable cues |
| **Multilingual subtitles + translation** | Gemini text model translates cues *keeping the timing* |
| **Quiz / MCQ generator** | structured JSON output (pydantic schema) with rationale + hints, interactive in the UI |
| **Study notes** | summary, key points, chapters, keywords |
| **Long media** | audio is normalised with FFmpeg and split into chunks (25 min with diarization/timestamps, 55 min otherwise) with timestamps offset-corrected |

## Quick start

```bash
# 1. Python 3.13 + uv
uv venv                # already created; activates .venv
uv sync                # installs google-genai, streamlit, yt-dlp, python-dotenv, pytest

# 2. API key  (https://aistudio.google.com/app/apikey)
copy .env.example .env  # then paste GEMINI_API_KEY=...

# 3. FFmpeg must be installed (Windows: winget install Gyan.FFmpeg)

# 4. Run
uv run streamlit run app.py          # web UI
uv run cli.py samples/sample_lecture.wav --quiz 5 --translate Urdu   # CLI
uv run pytest                        # tests (offline, no API calls)
```

## Project layout

```
transcriptogen-ai/
├── app.py                  # Streamlit UI (upload / YouTube, tabs for every output)
├── cli.py                  # command-line pipeline
├── transcriptogen/
│   ├── config.py           # models, limits, language lists, TranscribeOptions
│   ├── media.py            # FFmpeg: find binary, duration, extract mono 16 kHz mp3, chunk
│   ├── transcriber.py      # Gemini 3.5 Transcribe (Interactions API) + word annotation parsing
│   ├── subtitles.py        # words -> cues -> SRT / VTT / speaker transcript
│   ├── generators.py       # translation, translated cues, quiz, notes (JSON schemas)
│   ├── youtube.py          # yt-dlp audio download
│   └── models.py           # Word / TranscriptResult dataclasses
├── tests/                  # pytest (request building, response parsing, subtitle logic)
├── samples/                # sample_lecture.wav (Windows TTS) for smoke tests
└── outputs/                # CLI outputs (git-ignored)
```

## How the transcription call works

```python
from google import genai
client = genai.Client()                       # GEMINI_API_KEY from env

interaction = client.interactions.create(
    model="gemini-3.5-transcribe",
    input=[{"type": "audio", "uri": f.uri, "mime_type": f.mime_type}],   # or {"type":"audio","data":<base64>,...}
    generation_config={"transcription_config": {
        "language_codes": ["ur-PK", "en-US"],          # [] = auto-detect
        "mode": {"type": "verbatim",
                 "diarization_mode": "speaker",
                 "timestamp_granularities": ["word"]},
    }},
)
interaction.output_text                        # full transcript
# word annotations: interaction.steps[].content[].annotations[] where type == "word_info"
#   -> .text, .start_offset ("0.100s"), .end_offset, .speaker ("spk_1")
```

Rules baked into `TranscribeOptions` (from the official docs):

* `smart` mode = clean dictation, **no** speakers / timestamps.
* `custom_vocabulary` is **incompatible** with diarization and timestamps (dropped automatically).
* Unary limit: 1 h per request, **30 min** when diarization/timestamps are on → we chunk below that.
* Diarization is reliable up to 3 speakers (up to 8 supported).
* Files ≤ 15 MB are sent inline (base64); bigger ones go through the Files API and are deleted afterwards.

## Billing / model notes (Sept 2026)

* `gemini-3.5-transcribe` is a **paid** model. If you see
  `429 ... Your prepayment credits are depleted`, the AI Studio *project* behind your key has no
  credits: open <https://ai.studio/projects>, select that project → Billing → add prepaid credits
  (≈ $0.005 per audio minute; a 1-hour lecture ≈ $0.30), or create the key in a project that has billing.
* `gemini-2.5-flash` returns 404 for new API keys; the text model default is now `gemini-3.6-flash`
  (override with `TEXT_MODEL` in `.env`). Text calls retry on 503 "high demand" / 429 with backoff and
  use `TEXT_FALLBACK_MODEL` (default `gemini-3.5-flash`) on the last attempt.
* Verified end-to-end on 2026-09-07: 25 s sample → 55 word annotations (`spk:0`, offsets like `"0.100s"`),
  SRT/VTT with real timing, Urdu translation, 3-question quiz, notes.

## Real-time captions (`gemini-3.5-transcribe-live`)

`transcriptogen/live.py` wraps the Live API (WebSocket): 16 kHz mono PCM in, interim + final
transcript events out. Verified 2026-09-07 (connect ≈ 0.7 s, interim results every few hundred ms).

```bash
uv run live_demo.py samples/sample_lecture.wav --realtime    # simulate a live mic from a file
```

Limits: 10 min per session, no speaker diarization / word timestamps (use the unary model for those).
For a real microphone feed `sounddevice` frames as an async iterator into `transcribe_stream(..., manual_vad=False)`.
Note: with the server's automatic VAD a word at a segment boundary was dropped in testing; for file
streaming the wrapper therefore disables VAD and sends one `activity_start`/`activity_end` pair (default).

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (private is fine) and open <https://share.streamlit.io>.
2. New app → pick the repo, branch `main`, main file `app.py`.
3. **Settings → Secrets** → paste (see `.streamlit/secrets.example.toml`):
   ```toml
   GEMINI_API_KEY = "your_primary_key"
   GEMINI_API_KEY_2 = "optional_fallback_key"
   ```
4. Deploy. `requirements.txt` (generated from `uv.lock`) installs the Python deps and
   `packages.txt` installs FFmpeg on the server. Uploads on the free tier are limited to ~200 MB
   per file; use the YouTube-URL input for bigger media.

Regenerate `requirements.txt` after adding packages: `uv export --no-hashes --no-dev --no-emit-project -o requirements.txt`.

## Quota handling: multiple keys and model rotation

Free-tier projects get about **20 requests per day per model** (e.g. `gemini-3.6-flash`) and a small
per-minute rate limit. To keep the app usable:

* Put extra keys from *different* AI Studio projects in `.env` as `GEMINI_API_KEY_2`, `GEMINI_API_KEY_3`
  (or a comma-separated `GEMINI_API_KEYS`).
* Text calls rotate automatically: `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` →
  `gemini-3.1-flash-lite` on the current key, then the same list on the next key. Short "retry in 1s"
  rate limits are waited out on the same model; daily-quota errors rotate immediately; the working
  combination is remembered for the session.
* Transcription (`gemini-3.5-transcribe`) rotates to the next key on quota / credit errors.
* When everything is exhausted you get one clear `QuotaExhaustedError` listing what failed on each key.

## Urdu vs Hindi output

Urdu and Hindi sound the same, so a recogniser on auto-detect can write Urdu speech in Devanagari.
`gemini-3.5-transcribe` is a dedicated ASR model: it accepts a text part but **ignores prompt
instructions** (verified), so the old "write in Urdu script, not Hindi" prompt cannot steer it. Instead:

1. The default language hint is **Urdu + English** (`["ur-PK", "en-US"]`), which selects the Urdu script.
2. If Devanagari still appears in the output, the app/CLI automatically rewrites it in Urdu script with the
   text model (`fix_urdu_script`, English words untouched, timing-preserving version for subtitles).
   CLI: `--keep-script` disables this.

Tested on a DigiSkills Urdu lecture clip (`samples/sample_urdu.mp3`): auto, `ur-PK` and `ur-PK+en-US`
all produced Urdu script. Known limitation: spoken English words inside Urdu speech are written in Urdu
script by the ASR model (e.g. "vocabulary" → "وکیبلری"); use the Translation tab (English) or the
notes/quiz features when you need the English terms back.

## Roman Urdu note (for the students)

* `app.py` chalane se pehle `.env` mein apni Gemini key daalo.
* Lambi video (1 ghanta+) bhi chalegi — code khud chunks banata hai aur timestamps ko shift karta hai.
* Urdu output Urdu script mein aata hai (Roman Urdu nahi); UI mein RTL rendering automatic hai.
* Quiz tab mein answers select kar ke "Check answers" dabao — score aur rationale dikhega.
* Har tab se .txt / .srt / .vtt / .json / .md download kar sakte ho.

## Roadmap / future scope (from the FYP proposal)

- [ ] FastAPI backend + React/Next.js frontend (Streamlit is the prototype UI)
- [ ] User accounts & history (PostgreSQL)
- [ ] Interactive video player with transcript highlighting (word timestamps already available)
- [x] Real-time captions with `gemini-3.5-transcribe-live` (Live API) — `live.py` / `live_demo.py`; UI integration pending
- [ ] AI dubbing (TTS on translated cues)
