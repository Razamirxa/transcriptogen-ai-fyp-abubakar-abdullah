"""TranscriptoGen AI - Streamlit UI.

Flow: 1) upload / URL + settings -> Generate transcript
      2) transcript, speakers, subtitles (full previews + downloads)
      3) optional extras, each only when its own button is pressed:
         translation, quiz (MCQs), study notes.

Run:  uv run streamlit run app.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from transcriptogen import config
from transcriptogen.config import LANGUAGE_OPTIONS, TRANSLATION_TARGETS, TranscribeOptions
from transcriptogen.generators import ContentGenerator, has_devanagari, quiz_to_markdown
from transcriptogen.subtitles import (
    cues_from_text,
    cues_from_words,
    fmt_time,
    speaker_transcript,
    to_srt,
    to_vtt,
)
from transcriptogen.transcriber import GeminiTranscriber
from transcriptogen.youtube import download_audio, is_url

st.set_page_config(page_title="TranscriptoGen AI", page_icon="🎧", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none; }
.rtl { direction: rtl; text-align: right; font-family: 'Noto Nastaliq Urdu','Jameel Noori Nastaleeq',
       'Noto Naskh Arabic', serif; font-size: 1.15rem; line-height: 2.1; white-space: pre-wrap; }
.ltr { white-space: pre-wrap; font-family: ui-monospace, Consolas, monospace; font-size: 0.92rem; line-height: 1.6; }
.box { max-height: 560px; overflow: auto; border: 1px solid #ddd; padding: 14px; border-radius: 8px; background: #fafafa; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_rtl(text: str) -> bool:
    sample = text[:600]
    return sum("؀" <= ch <= "ۿ" for ch in sample) > len(sample) * 0.2


def show_full_text(text: str) -> None:
    """Full, scrollable preview (no truncation) with RTL support."""
    cls = "rtl" if _is_rtl(text) else "ltr"
    st.markdown(f'<div class="box {cls}">{_escape(text)}</div>', unsafe_allow_html=True)


def show_code_full(text: str, key: str) -> None:
    """Full preview of SRT/VTT etc. in a scrollable text area (copy friendly)."""
    st.text_area("", value=text, height=520, key=key, label_visibility="collapsed")


def build_cues(result, fixed_cues):
    if fixed_cues:
        return fixed_cues
    if result.words:
        return cues_from_words(result.words)
    return cues_from_text(result.text, result.duration)


def safe_name(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in stem).strip() or "transcript"


def reset_outputs() -> None:
    for k in ("result", "fixed_cues", "stem", "translations", "quiz", "notes"):
        st.session_state.pop(k, None)


# API key(s) come from .env locally, or from st.secrets on Streamlit Community Cloud.
try:
    for _name in ("GEMINI_API_KEY", "GEMINI_API_KEYS", *[f"GEMINI_API_KEY_{i}" for i in range(2, 10)]):
        if _name in st.secrets and st.secrets[_name]:
            config.os.environ.setdefault(_name, str(st.secrets[_name]))
except Exception:  # no secrets.toml locally -> fine
    pass
try:
    API_KEYS = config.get_api_keys()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🎧 TranscriptoGen AI")
st.caption("Video / audio → transcript · speakers · subtitles · translation · quiz · notes  |  "
           f"models: `{config.TRANSCRIBE_MODEL}` + `{config.TEXT_MODEL}`  |  "
           "FYP by Abubakar Khan & Muhammad Abdullah, School of Software Engineering, MUL")

# ---------------------------------------------------------------------------
# Step 1 - input + settings + transcribe
# ---------------------------------------------------------------------------
st.header("1️⃣ Generate transcript")

in_col, opt_col = st.columns([3, 2])
with in_col:
    tab_upload, tab_url = st.tabs(["📁 Upload file", "▶️ YouTube / media URL"])
    with tab_upload:
        uploaded = st.file_uploader(
            "Audio or video (up to 2 GB)",
            type=[e.lstrip(".") for e in sorted(config.AUDIO_EXTS | config.VIDEO_EXTS)],
        )
        if uploaded is not None and uploaded.size <= 60 * 1024 * 1024:
            kind = "video" if Path(uploaded.name).suffix.lower() in config.VIDEO_EXTS else "audio"
            (st.video if kind == "video" else st.audio)(uploaded)
    with tab_url:
        url = st.text_input("URL", placeholder="https://www.youtube.com/watch?v=...")

with opt_col:
    st.subheader("Settings")
    lang_label = st.selectbox("Language hint", list(LANGUAGE_OPTIONS), index=0,
                              help="Urdu + English avoids Hindi (Devanagari) output. Auto-detect for other languages.")
    mode = st.radio("Mode", ["Verbatim (speakers + timestamps)", "Smart (clean dictation, no speakers/timestamps)"],
                    index=0)
    smart = mode.startswith("Smart")
    c1, c2 = st.columns(2)
    diar = c1.checkbox("Speaker diarization", value=True, disabled=smart)
    ts = c2.checkbox("Word timestamps (real subtitle timing)", value=True, disabled=smart)
    with st.expander("Advanced"):
        vocab_raw = st.text_input(
            "Custom vocabulary (comma separated)", "",
            help="Names / technical terms to recognise better. Google only applies this when diarization "
                 "and timestamps are OFF (or in Smart mode).",
        )
        fix_script = st.checkbox("Convert Hindi (Devanagari) output to Urdu script automatically", value=True)

opts = TranscribeOptions(
    language_codes=LANGUAGE_OPTIONS[lang_label],
    diarization=diar and not smart,
    word_timestamps=ts and not smart,
    smart_mode=smart,
    custom_vocabulary=[v.strip() for v in vocab_raw.split(",") if v.strip()],
)

run = st.button("🎯 Generate transcript", type="primary", use_container_width=True)

if run:
    if uploaded is None and not (url and is_url(url)):
        st.error("Upload a file or paste a valid URL first.")
        st.stop()
    reset_outputs()
    prog = st.progress(0.0)
    status = st.empty()

    def progress(msg: str, frac: float) -> None:
        status.info(msg)
        prog.progress(min(max(frac, 0.0), 1.0))

    tmp_path: Path | None = None
    try:
        if uploaded is not None:
            suffix = Path(uploaded.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(uploaded.getbuffer())
                tmp_path = Path(f.name)
            stem = Path(uploaded.name).stem
        else:
            progress("Downloading audio with yt-dlp...", 0.01)
            tmp_path, info = download_audio(url)
            stem = info.get("title") or "youtube"
            st.caption(f"Downloaded: **{stem}** ({(info.get('duration') or 0) / 60:.1f} min)")

        result = GeminiTranscriber(api_keys=API_KEYS).transcribe(tmp_path, opts, progress)

        fixed_cues = None
        if fix_script and has_devanagari(result.text):
            status.info("Hindi/Devanagari detected → converting to Urdu script ...")
            gen = ContentGenerator(api_keys=API_KEYS)
            result.text = gen.fix_urdu_script(result.text)
            fixed_cues = gen.fix_urdu_script_cues(build_cues(result, None))
    except Exception as e:
        st.error(f"Failed: {e}")
        st.stop()
    finally:
        if tmp_path:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    st.session_state.update(result=result, fixed_cues=fixed_cues, stem=stem, translations={})
    status.success(
        f"Done · {result.duration / 60:.1f} min · {result.chunks} chunk(s) · {len(result.words)} timed words · "
        f"speakers: {', '.join(result.speakers) or 'n/a'}"
    )

# ---------------------------------------------------------------------------
# Step 2 - transcript outputs
# ---------------------------------------------------------------------------
if "result" not in st.session_state:
    st.info("Upload a file or paste a URL, adjust settings if needed, then press **Generate transcript**.")
    st.stop()

result = st.session_state["result"]
stem = safe_name(st.session_state["stem"])
cues = build_cues(result, st.session_state.get("fixed_cues"))
srt, vtt = to_srt(cues), to_vtt(cues)

st.header("2️⃣ Transcript")
st.caption(
    f"{len(result.text):,} characters · {len(cues)} subtitle cues · last cue ends at "
    f"{fmt_time(cues[-1].end, ms=False) if cues else '-'} · media length {fmt_time(result.duration or 0, ms=False)}"
)

t_txt, t_spk, t_srt, t_vtt, t_json = st.tabs(["📝 Transcript", "🗣️ Speakers", "🎞️ SRT", "🎞️ VTT", "🧾 JSON"])

with t_txt:
    st.download_button("⬇️ Download .txt", result.text, f"{stem}.txt", "text/plain", key="dl_txt")
    show_full_text(result.text)

with t_spk:
    if result.words and result.speakers:
        sp = speaker_transcript(result.words)
        st.download_button("⬇️ Download speakers .txt", sp, f"{stem}.speakers.txt", "text/plain", key="dl_spk")
        show_full_text(sp)
    else:
        st.info("Enable speaker diarization (Verbatim mode) to get speaker-attributed output.")

with t_srt:
    if not result.words:
        st.warning("No word timestamps: subtitle timing is estimated evenly. Enable timestamps for real timing.")
    st.download_button("⬇️ Download .srt", srt, f"{stem}.srt", "text/plain", key="dl_srt")
    show_code_full(srt, "srt_full")

with t_vtt:
    st.download_button("⬇️ Download .vtt", vtt, f"{stem}.vtt", "text/vtt", key="dl_vtt")
    show_code_full(vtt, "vtt_full")

with t_json:
    payload = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    st.download_button("⬇️ Download .json", payload, f"{stem}.json", "application/json", key="dl_json")
    show_code_full(payload, "json_full")
    if result.usage:
        st.caption(f"Usage: {result.usage}")

# ---------------------------------------------------------------------------
# Step 3 - extras, each on its own button
# ---------------------------------------------------------------------------
st.header("3️⃣ Generate more from this transcript")
st.caption("Nothing here runs automatically - press a button to generate.")

x_tr, x_quiz, x_notes = st.tabs(["🌐 Translation", "❓ Quiz (MCQs)", "📚 Study notes"])

# ---- translation ----------------------------------------------------------
with x_tr:
    tc1, tc2 = st.columns([2, 1])
    target_lang = tc1.selectbox("Target language", TRANSLATION_TARGETS, index=0)
    tc2.write("")
    tc2.write("")
    if tc2.button("🌐 Translate", type="primary", use_container_width=True):
        with st.spinner(f"Translating to {target_lang} (transcript + timed subtitles)..."):
            try:
                gen = ContentGenerator(api_keys=API_KEYS)
                tr_text = gen.translate(result.text, target_lang)
                tr_cues = gen.translate_cues(cues, target_lang)
                st.session_state["translations"][target_lang] = {
                    "text": tr_text, "srt": to_srt(tr_cues), "vtt": to_vtt(tr_cues)}
            except Exception as e:
                st.error(f"Translation failed: {e}")

    translations = st.session_state.get("translations", {})
    if translations:
        langs = list(translations)
        pick = st.radio("Generated translations", langs, index=len(langs) - 1, horizontal=True)
        tr = translations[pick]
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Translation .txt", tr["text"], f"{stem}.{pick}.txt", key=f"dl_tr_txt_{pick}")
        d2.download_button("⬇️ Translated .srt", tr["srt"], f"{stem}.{pick}.srt", key=f"dl_tr_srt_{pick}")
        d3.download_button("⬇️ Translated .vtt", tr["vtt"], f"{stem}.{pick}.vtt", key=f"dl_tr_vtt_{pick}")
        p1, p2 = st.tabs(["Text", "SRT"])
        with p1:
            show_full_text(tr["text"])
        with p2:
            show_code_full(tr["srt"], f"tr_srt_{pick}")

# ---- quiz -----------------------------------------------------------------
with x_quiz:
    q1, q2, q3, q4 = st.columns([1, 1, 1, 1])
    n_q = q1.slider("Questions", 3, 20, 5)
    difficulty = q2.select_slider("Difficulty", ["easy", "medium", "hard"], value="medium")
    quiz_lang = q3.selectbox("Quiz language", ["English", "Urdu", "Arabic"], index=0)
    q4.write("")
    q4.write("")
    if q4.button("❓ Generate quiz", type="primary", use_container_width=True):
        with st.spinner("Generating MCQs..."):
            try:
                q = ContentGenerator(api_keys=API_KEYS).quiz(result.text, n=n_q, difficulty=difficulty, language=quiz_lang)
                st.session_state["quiz"] = q
                st.session_state.pop("quiz_submitted", None)
            except Exception as e:
                st.error(f"Quiz generation failed: {e}")

    q = st.session_state.get("quiz")
    if q:
        st.subheader(q.title)
        letters = "ABCD"
        answers = {}
        with st.form("quiz_form"):
            for i, qu in enumerate(q.questions):
                st.markdown(f"**Q{i + 1}. {qu.question}**")
                answers[i] = st.radio(
                    "", [f"{letters[j]}. {o.text}" for j, o in enumerate(qu.options[:4])],
                    key=f"q{i}", index=None, label_visibility="collapsed",
                )
                if qu.hint:
                    st.caption(f"💡 Hint: {qu.hint}")
            submitted = st.form_submit_button("✅ Check answers")
        if submitted:
            score = 0
            for i, qu in enumerate(q.questions):
                chosen = answers.get(i)
                correct_j = next((j for j, o in enumerate(qu.options[:4]) if o.is_correct), None)
                ok = chosen is not None and correct_j is not None and chosen.startswith(letters[correct_j])
                score += ok
                why = qu.options[correct_j].rationale if correct_j is not None else ""
                label = letters[correct_j] if correct_j is not None else "?"
                (st.success if ok else st.error)(f"Q{i + 1}: {'Correct' if ok else 'Wrong'} · answer {label}. {why}")
            st.metric("Score", f"{score}/{len(q.questions)}")
        m1, m2 = st.columns(2)
        m1.download_button("⬇️ Quiz .md", quiz_to_markdown(q), f"{stem}.quiz.md", key="dl_quiz_md")
        m2.download_button("⬇️ Quiz .json", q.model_dump_json(indent=2), f"{stem}.quiz.json", key="dl_quiz_json")

# ---- notes ----------------------------------------------------------------
with x_notes:
    n1, n2 = st.columns([2, 1])
    notes_lang = n1.selectbox("Notes language", ["English", "Urdu", "Arabic"], index=0)
    n2.write("")
    n2.write("")
    if n2.button("📚 Generate notes", type="primary", use_container_width=True):
        with st.spinner("Summarising..."):
            try:
                st.session_state["notes"] = ContentGenerator(api_keys=API_KEYS).notes(result.text, language=notes_lang)
            except Exception as e:
                st.error(f"Notes failed: {e}")

    n = st.session_state.get("notes")
    if n:
        st.markdown("### Summary")
        st.write(n.summary)
        st.markdown("### Key points")
        for kp in n.key_points:
            st.markdown(f"- {kp}")
        st.markdown("### Chapters")
        for i, ch in enumerate(n.chapters, 1):
            st.markdown(f"{i}. {ch}")
        st.markdown("**Keywords:** " + ", ".join(n.keywords))
        st.download_button("⬇️ Notes .json", n.model_dump_json(indent=2), f"{stem}.notes.json", key="dl_notes")
