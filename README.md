# TranscriptoGen AI 🎧

**Final Year Project (BSSE, Minhaj University Lahore)**
Abubakar Khan (2022F-mulbsswe-036) & Muhammad Abdullah (2022F-mulbsswe-029)
Supervisor: Maya Bint Yousaf · Co-supervisor: Misbah Akram

> Ye README Abubakar aur Abdullah ke liye **A to Z guide** hai, Roman Urdu mein. Setup se lekar
> code samajhne, chalane, errors theek karne aur FYP presentation tak sab kuch yahan hai.

---

## 1. Ye project kya karta hai?

Koi bhi **video ya audio file** (ya YouTube link) do, ye app usse banata hai:

| Feature | Kya milta hai |
| --- | --- |
| **Transcription** | Awaz ko text mein (85+ languages, Urdu + English mix bhi) |
| **Speaker diarization** | Kaun kab bola: `Speaker 1`, `Speaker 2` ... |
| **Subtitles (SRT / VTT)** | Har lafz ke real timestamps se bani subtitle files |
| **Translation** | Transcript aur subtitles ka tarjuma (Urdu, English, Arabic, Hindi, aur 9 aur languages), timing same rehti hai |
| **Quiz (MCQs)** | Lecture se sawal, 4 options, hint, aur har option ki wajah |
| **Study notes** | Summary, key points, chapters, keywords |
| **Live captions** | Real-time transcription demo (`live_demo.py`) |
| **Lambi videos** | 1 ghante+ ki video bhi chalti hai, code khud chunks banata hai |

AI models (Google Gemini):

- `gemini-3.5-transcribe` → audio se text (Interactions API). Ye **dedicated speech model** hai.
- `gemini-3.5-transcribe-live` → real-time captions (Live API, WebSocket).
- `gemini-3.6-flash` (aur fallbacks) → translation, quiz, notes.

---

## 2. Zaroori cheezein (requirements)

| Cheez | Kyun chahiye | Kaise lein |
| --- | --- | --- |
| **Python 3.13** | Project isi version par bana hai | `uv` khud download kar leta hai |
| **uv** | Package manager (pip + venv ka modern replacement) | PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **FFmpeg** | Video se audio nikalna, chunks banana | PowerShell: `winget install Gyan.FFmpeg` phir terminal restart |
| **Gemini API key** | Google ke models use karne ke liye | <https://aistudio.google.com/app/apikey> → Create API key |
| **Git** (optional) | Code GitHub se lene ke liye | <https://git-scm.com> |

> ⚠️ `gemini-3.5-transcribe` **paid model** hai. Jis AI Studio project se key banao usme billing / prepaid credits hone chahiye
> (rate ≈ $0.005 per minute audio, yani 1 ghante ka lecture ≈ $0.30). Text models (translation/quiz) free tier par bhi chalte hain,
> lekin din mein sirf ~20 requests per model. Section 9 mein detail hai.

---

## 3. Setup (step by step, Windows)

```powershell
# 1) Project folder mein jao
cd "E:\Projects\students fyp\bakar khan\transcriptogen-ai"

# 2) Virtual environment banao aur saari packages install karo (uv.lock ke mutabiq)
uv venv
uv sync

# 3) API key file banao
copy .env.example .env
notepad .env        # yahan GEMINI_API_KEY=... paste karo, save karo

# 4) FFmpeg check karo (version dikhna chahiye)
ffmpeg -version

# 5) Tests chalao (internet / API ki zaroorat nahi, 27 tests pass hone chahiye)
uv run pytest

# 6) App chalao
uv run streamlit run app.py
```

Browser khud khulega: <http://localhost:8501>

`.env` file aisi dikhni chahiye:

```
GEMINI_API_KEY=AQ.Ab8...apni_key
GEMINI_API_KEY_2=AIza...doosre_project_ki_key   # optional fallback
```

> `.env` kabhi GitHub par push mat karna, `.gitignore` mein already hai. Har banda apni key use kare.

---

## 4. App kaise use karein (UI ka flow)

App teen steps mein chalti hai, **kuch bhi automatic nahi hota**, har cheez button par:

### Step 1 – Generate transcript

1. **Upload file** tab mein audio/video drag karo (mp3, wav, m4a, mp4, mkv, mov ... 2 GB tak) **ya** **YouTube / media URL** tab mein link paste karo.
2. Right side **Settings**:
   - **Language hint**: default `Urdu + English (mixed)`. Urdu lecture ke liye yehi rakho. Pure English ke liye `English (US)`, kisi aur language ke liye `Auto-detect`.
   - **Mode**:
     - `Verbatim` = jo bola gaya wahi likha jaye, speakers aur timestamps ke saath (subtitles ke liye ye chahiye).
     - `Smart` = saaf dictation (umm/aah hata deta hai) lekin **speakers/timestamps nahi milte**.
   - **Speaker diarization** aur **Word timestamps** on rakho (subtitle timing inhi se banti hai).
   - **Advanced → Custom vocabulary**: khaas naam/terms comma se likho (jaise `Minhaj University, FastAPI`). Google ki restriction: ye **sirf tab** lagti hai jab diarization aur timestamps **off** hon ya Smart mode ho.
   - **Advanced → Convert Hindi to Urdu script**: on rakho (section 8 dekho).
3. **🎯 Generate transcript** dabao. Neeche dikhega: media length, **estimated time**, elapsed / remaining timer, progress bar.

### Step 2 – Transcript

Chaar tabs, har ek mein **pehle download button, phir poora preview** (koi truncation nahi, copy kar sakte ho):

- **Transcript** → `.txt`
- **Speakers** → speaker-wise paragraphs with timestamps → `.speakers.txt`
- **SRT** → `.srt` (YouTube, VLC, Premiere sab mein chalta hai)
- **VTT** → `.vtt` (web players ke liye)

Upar caption mein check karo: characters, cues, **last cue kahan khatam hui vs media length**. Dono qareeb hon to transcript poora hai.

### Step 3 – Generate more from this transcript

- **Translation**: target language chuno → **🌐 Translate** → text + translated `.srt`/`.vtt`. Ek se zyada languages generate kar ke unke beech switch kar sakte ho.
- **Quiz**: questions count, difficulty, language → **❓ Generate quiz** → sawal hal karo → **Check answers** → score aur har sawal ki explanation. Download `.md`.
- **Study notes**: language → **📚 Generate notes** → summary, key points, chapters, keywords. Download `.md`.

Naya transcript generate karoge to purani translation/quiz/notes clear ho jayengi.

---

## 5. Command line (CLI) se chalana

UI ke bina, batch ya testing ke liye:

```powershell
# Basic
uv run cli.py "lecture.mp4"

# Urdu lecture, English translation, 5 MCQs, notes
uv run cli.py "lecture.mp4" --lang ur-PK en-US --translate English --quiz 5 --notes

# YouTube se
uv run cli.py "https://youtu.be/xxxx" --translate Urdu

# Sirf saaf text, speakers/timestamps ke bina (tez aur sasta)
uv run cli.py "audio.mp3" --no-diarization --no-timestamps

# Smart mode + custom vocabulary
uv run cli.py "audio.mp3" --smart --vocab "Qdrant" "FastAPI"
```

Output `outputs/` folder mein: `.txt`, `.speakers.txt`, `.srt`, `.vtt`, `.json` (words + timestamps), `.<Language>.txt/.srt`, `.quiz.md/.json`, `.notes.json`.

Saare options: `uv run cli.py --help`

---

## 6. Live captions demo

```powershell
uv run live_demo.py samples/sample_lecture.wav --realtime            # file ko mic ki tarah stream karta hai
uv run live_demo.py "lecture.mp3" --lang ur-PK --realtime
```

Screen par interim (aadhe jumle) aur FINAL lines aati hain. Limits: 10 minute per session, speakers/timestamps nahi.
Asli microphone ke liye `sounddevice` se PCM frames le kar `transcribe_stream(..., manual_vad=False)` ko async iterator do (`transcriptogen/live.py` dekho).

---

## 7. Project structure (kaun si file kya karti hai)

```
transcriptogen-ai/
├── app.py                    # Streamlit UI (Step 1/2/3)
├── cli.py                    # command line pipeline
├── live_demo.py              # real-time captions demo
├── .env                      # API keys (git par nahi jati)
├── .env.example              # .env ka template
├── pyproject.toml / uv.lock  # dependencies (uv)
├── requirements.txt          # wahi dependencies pip format mein
├── packages.txt              # system package list (ffmpeg)
├── .streamlit/config.toml    # upload limit 2 GB, theme
├── samples/sample_lecture.wav# 25 sec test audio
├── outputs/                  # CLI outputs (git par nahi)
├── tests/                    # pytest (offline)
└── transcriptogen/           # asal code (package)
    ├── config.py             # models ke naam, limits, language list, TranscribeOptions, API keys parhna
    ├── media.py              # FFmpeg: ffmpeg dhoondna, duration, audio nikalna (mono 16 kHz mp3), chunks
    ├── transcriber.py        # gemini-3.5-transcribe call, word annotations parse, chunking, key rotation, ETA
    ├── subtitles.py          # words -> cues -> SRT / VTT / speaker transcript
    ├── generators.py         # translation, translated cues, quiz, notes, Hindi->Urdu fix, model/key rotation
    ├── youtube.py            # yt-dlp se audio download
    ├── live.py               # gemini-3.5-transcribe-live (Live API) wrapper
    └── models.py             # Word aur TranscriptResult dataclasses
```

---

## 8. Code kaise kaam karta hai (FYP viva ke liye samajh lo)

### 8.1 Pipeline

```
file / URL
   │  youtube.py (yt-dlp)            ← sirf URL par
   ▼
media.py : ffmpeg -> mono 16 kHz mp3 -> agar lamba ho to chunks (25 min / 55 min)
   ▼
transcriber.py : har chunk -> Gemini 3.5 Transcribe -> text + words[{text,start,end,speaker}]
                 (chunk ka start time har word mein add hota hai taake timing sahi rahe)
   ▼
subtitles.py : words -> cues (speaker change / 1 s pause / 84 chars / 6 s par nayi line) -> SRT, VTT
   ▼
generators.py : transcript -> translation / quiz / notes (Gemini text model, JSON schema)
```

### 8.2 Transcription call (asal API code)

```python
from google import genai
client = genai.Client()   # GEMINI_API_KEY env se

interaction = client.interactions.create(
    model="gemini-3.5-transcribe",
    input=[{"type": "audio", "data": <base64 audio>, "mime_type": "audio/mpeg"}],   # ya Files API ka uri
    generation_config={"transcription_config": {
        "language_codes": ["ur-PK", "en-US"],          # [] = auto detect
        "mode": {"type": "verbatim",
                 "diarization_mode": "speaker",        # speakers
                 "timestamp_granularities": ["word"]}, # har lafz ka time
    }},
)
interaction.output_text          # poora transcript
# words: interaction.steps[].content[].annotations[]  jahan type == "word_info"
#        -> .text, .start_offset ("0.100s"), .end_offset, .speaker ("spk:0")
```

Google ke rules jo code mein baked hain (`TranscribeOptions`):

- `smart` mode mein speakers/timestamps nahi milte.
- `custom_vocabulary` diarization/timestamps ke saath nahi chalti (code khud drop kar deta hai).
- Ek request mein max 1 ghanta audio, **30 min** agar diarization/timestamps on hon → isliye chunks 25 / 55 min ke.
- Diarization 3 speakers tak reliable (8 tak support).
- 15 MB tak file inline (base64) jati hai, badi file Files API se upload ho kar baad mein delete.

### 8.3 Subtitles kaise bante hain

`subtitles.py` → `cues_from_words()`: lafz jodta jata hai, nayi cue tab shuru hoti hai jab speaker badle, 1 second se lambi khamoshi ho, 84 characters se zyada ho jayen, ya cue 6 second se lambi ho. Phir `to_srt()` / `to_vtt()` format banate hain. Timestamps asli hain (purane projects mein andaze se hote the).

### 8.4 Urdu vs Hindi (Devanagari) ka masla

Urdu aur Hindi ki awaz ek jaisi hai, isliye speech model kabhi Urdu ko **हिंदी script** mein likh deta hai. Ye model prompt nahi maanta (test kiya), isliye do-layer hal:

1. Default language hint `ur-PK + en-US` → Urdu script select hota hai.
2. Agar phir bhi Devanagari aaye to `generators.fix_urdu_script()` text model se usse Urdu script mein badal deta hai (English words waise hi rehte hain), subtitles ke liye bhi timing rakh kar.

Known limitation: Urdu ke beech bole gaye English words (jaise "vocabulary") speech model Urdu script mein likhta hai (وکیبلری). English terms wapas chahiye hon to Translation (English) use karo.

### 8.5 Translation / quiz / notes

`generators.py` mein prompts hain. Quiz aur notes **structured JSON** (pydantic schema) mein aate hain taake UI seedha parse kar sake. Translation mein technical terms English mein rehte hain aur Urdu ke liye Urdu script (Roman Urdu nahi).

---

## 9. API keys, quota aur billing (sab se zyada errors yahin se aate hain)

### Keys kahan se

1. <https://aistudio.google.com/app/apikey> → project chuno → Create API key.
2. Us project mein **billing enable** karo ya prepaid credits daalo (transcribe model ke liye zaroori).
3. `.env` mein `GEMINI_API_KEY=` ke aage paste karo.

### Free tier ki limit

Har model ke sirf ~**20 requests per day** aur chhoti per-minute limit. Isliye code mein **automatic rotation** hai:

- Text calls: `gemini-3.6-flash` → `gemini-3.5-flash` → `gemini-3.5-flash-lite` → `gemini-3.1-flash-lite`, phir agli key par wahi list.
- Chhota rate-limit ("retry in 1s") same model par wait kar ke retry; daily quota par foran agla model.
- Transcription: quota / credit error par agli key.
- Fallback key doosre AI Studio **project** ki honi chahiye (`GEMINI_API_KEY_2`), same project ki dusri key ka faida nahi.

### Errors aur unka hal

| Error message | Matlab | Hal |
| --- | --- | --- |
| `GEMINI_API_KEY is not set` | `.env` nahi ya khali | `.env` banao, key paste karo, app restart |
| `API key not valid` | Key ghalat / expire | AI Studio se nayi key |
| `429 ... prepayment credits are depleted` | Project ka balance zero | ai.studio/projects → Billing → credits add karo, ya doosre project ki key |
| `429 ... free_tier_requests, limit: 20` | Us model ka daily quota khatam | Code khud agla model/key try karta hai; sab khatam hon to `GEMINI_API_KEY_2` add karo ya kal chalao |
| `503 ... high demand` | Google busy | Code khud 3/6/12 s wait kar ke retry karta hai, phir fallback model |
| `404 ... gemini-2.5-flash no longer available` | Purana model naye keys ke liye band | Hum `gemini-3.6-flash` use karte hain, kuch nahi karna |
| `ffmpeg not found` | FFmpeg install/PATH nahi | `winget install Gyan.FFmpeg`, terminal restart; ya `.env` mein `FFMPEG_PATH=C:\...\ffmpeg.exe` |
| `ImportError: cannot import name ...` app mein | Purana Streamlit process, code badla hai | Ctrl+C se app band, dobara `uv run streamlit run app.py` |
| Transcript Hindi mein | Language hint auto tha | Hint `Urdu + English` rakho; fix checkbox on rakho |
| Subtitles ki timing andaze se | Word timestamps off the | Verbatim mode + Word timestamps on |
| YouTube download fail | yt-dlp purana / video private | `uv add yt-dlp --upgrade`; public video use karo |

---

## 10. Tests

```powershell
uv run pytest            # 27 tests, offline, API key ki zaroorat nahi
uv run pytest -v         # har test ka naam
```

Tests kya check karte hain: request config sahi banta hai, API response ke words sahi parse hote hain (offsets, speaker labels, chunk offset), SRT/VTT format, cue splitting, retry/rotation logic, Devanagari detection, ETA estimate.

---

## 11. Settings jo `.env` se badal sakte ho

```
GEMINI_API_KEY=...                 # zaroori
GEMINI_API_KEY_2=...               # optional fallback (doosra project)
TRANSCRIBE_MODEL=gemini-3.5-transcribe
TEXT_MODEL=gemini-3.6-flash
TEXT_FALLBACK_MODEL=gemini-3.5-flash
TEXT_MODEL_CANDIDATES=gemini-3.6-flash,gemini-3.5-flash,gemini-3.5-flash-lite
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
```

Nayi package add karni ho: `uv add package-name` (phir `uv export --no-hashes --no-dev --no-emit-project -o requirements.txt` taake requirements.txt bhi update ho).

---

## 12. Kitna time lagta hai (estimate)

Real runs par naapa gaya (2026-09-07):

| Audio | Diarization + timestamps | Plain |
| --- | --- | --- |
| 25 sec | ~5 s | ~4 s |
| 6.5 min | ~22 s | ~12 s |
| 1 ghanta (andaza) | ~3.5 min (3 chunks) | ~2 min |

App Step 1 mein chalte waqt **elapsed / estimated / remaining** dikhati hai. Estimate `transcriber.estimate_seconds()` mein hai.

---

## 13. Known limitations (viva mein imandari se batao)

- Speech model prompt/instructions nahi maanta, sirf `language_codes` aur config.
- Urdu speech ke andar English words Urdu script mein likhe jate hain.
- Diarization 3 speakers ke baad experimental; alag chunks mein speaker labels reset ho sakte hain (chunk 1 ka Speaker 2 aur chunk 2 ka Speaker 2 alag log ho sakte hain).
- Live model: 10 min/session, speakers/timestamps nahi.
- Free tier quota chhota hai; demo se pehle keys/credits check karo.

---

## 14. Future work / roadmap (FYP proposal ke mutabiq)

- [ ] FastAPI backend + React/Next.js frontend (Streamlit abhi prototype UI hai)
- [ ] User accounts aur history (PostgreSQL)
- [ ] Video player jisme transcript ka lafz highlight ho (word timestamps already hain)
- [x] Real-time captions (`live.py` / `live_demo.py`), UI mein integrate karna baqi
- [ ] AI dubbing: translated cues par TTS
- [ ] Custom vocabulary ko diarization ke saath use karne ka workaround (post-processing)

---

## 15. Glossary

| Term | Matlab |
| --- | --- |
| Transcription / ASR | Awaz ko text mein badalna (Automatic Speech Recognition) |
| Diarization | Ye pehchanna ke kaun sa hissa kis speaker ne bola |
| Word timestamps | Har lafz ka start/end time (seconds) |
| Cue | Subtitle ki ek entry (number, time range, text) |
| SRT / VTT | Subtitle file formats (SubRip / WebVTT) |
| Chunk | Lambi audio ka tukra jo alag request mein jata hai |
| Interactions API | Google ka naya API jis se transcribe model call hota hai |
| Live API | WebSocket based streaming API (real-time) |
| BCP-47 code | Language code jaise `ur-PK`, `en-US` |
| Quota / rate limit | Kitni requests allowed hain (per minute / per day) |
| uv | Python package/venv manager (`uv add`, `uv run`, `uv sync`) |
| Streamlit | Python se web UI banane ki library |
