"""TranscriptoGen AI - Streamlit UI.

Flow: 1) upload / URL + settings -> Generate transcript
      2) optional: upload images (slides, whiteboard, notes) -> extract text / ask questions
      3) transcript, speakers, subtitles (full previews + downloads)
      4) optional extras, each only when its own button is pressed:
         translation, quiz (MCQs), notes, meeting minutes
         (source = transcript, and/or the text extracted from images)

Run:  uv run streamlit run app.py
"""
from __future__ import annotations

import tempfile
import threading
import time
from datetime import date
from pathlib import Path

import streamlit as st

from transcriptogen import config
from transcriptogen.config import LANGUAGE_OPTIONS, TRANSLATION_TARGETS, TranscribeOptions
from transcriptogen.generators import (
    ContentGenerator,
    has_devanagari,
    image_extraction_to_markdown,
    minutes_to_markdown,
    notes_to_markdown,
    point_notes_to_markdown,
    quiz_to_markdown,
)
from transcriptogen.subtitles import (
    cues_from_text,
    cues_from_words,
    fmt_time,
    speaker_transcript,
    to_srt,
    to_vtt,
)
from transcriptogen.transcriber import GeminiTranscriber, fmt_eta
from transcriptogen.youtube import download_audio, is_url

st.set_page_config(page_title="TranscriptoGen AI", page_icon="🎧", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
<style>
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display: none; }
.preview textarea { font-size: 0.95rem !important; line-height: 1.7 !important; }
</style>
""",
    unsafe_allow_html=True,
)

IMAGE_TYPES = ["png", "jpg", "jpeg", "webp", "gif", "bmp"]
OUTPUT_LANGS = ["English", "Urdu", "Arabic"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _is_rtl(text: str) -> bool:
    sample = text[:600]
    return sum("؀" <= ch <= "ۿ" for ch in sample) > len(sample) * 0.2


def show_full_text(text: str, key: str, height: int = 560) -> None:
    """Full, scrollable, copyable preview (no truncation); RTL styling for Urdu/Arabic.

    A native text area is used on purpose: theme-safe, never truncated, copy friendly.
    st.container(key=...) exposes the CSS class st-key-<key> so only this area is styled.
    """
    with st.container(key=f"wrap_{key}"):
        if _is_rtl(text):
            st.markdown(
                f"<style>.st-key-wrap_{key} textarea {{ direction: rtl; text-align: right; font-size: 1.15rem; "
                "line-height: 2.1; font-family: 'Noto Nastaliq Urdu','Jameel Noori Nastaleeq',"
                "'Noto Naskh Arabic', serif; }}</style>",
                unsafe_allow_html=True,
            )
        st.text_area("preview", value=text, height=height, key=key, label_visibility="collapsed")


def show_code_full(text: str, key: str) -> None:
    st.text_area("preview", value=text, height=520, key=key, label_visibility="collapsed")


def build_cues(result, fixed_cues):
    if fixed_cues:
        return fixed_cues
    if result.words:
        return cues_from_words(result.words)
    return cues_from_text(result.text, result.duration)


def safe_name(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in stem).strip() or "transcript"


def reset_generated() -> None:
    """Drop everything derived from the previous source (new transcript or new images)."""
    for k in ("translations", "quiz", "notes", "point_notes", "minutes"):
        st.session_state.pop(k, None)


def reset_transcript() -> None:
    for k in ("result", "fixed_cues", "stem"):
        st.session_state.pop(k, None)
    reset_generated()


def source_text() -> str:
    """Text that Step 4 works on: transcript and/or text extracted from images."""
    parts: list[str] = []
    result = st.session_state.get("result")
    if result is not None:
        parts.append(result.text)
    img = st.session_state.get("images")
    if img is not None and st.session_state.get("use_images", True):
        parts.append(
            f"[Content of {st.session_state.get('image_count', 0)} uploaded image(s): {img.content_type}]\n"
            f"Description: {img.description}\n\nExtracted text:\n{img.extracted_text}"
        )
    return "\n\n".join(parts)


# API key(s): .env locally, st.secrets on Streamlit Community Cloud
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
st.caption("Video / audio → transcript · speakers · subtitles · translation · quiz · notes · meeting minutes  |  "
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
    reset_transcript()
    prog = st.progress(0.0)
    status = st.empty()
    timer = st.empty()
    t_start = time.time()

    tmp_path: Path | None = None
    try:
        if uploaded is not None:
            suffix = Path(uploaded.name).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(uploaded.getbuffer())
                tmp_path = Path(f.name)
            stem = Path(uploaded.name).stem
        else:
            status.info("Downloading audio with yt-dlp...")
            tmp_path, info = download_audio(url)
            stem = info.get("title") or "youtube"
            st.caption(f"Downloaded: **{stem}** ({(info.get('duration') or 0) / 60:.1f} min)")

        # Worker thread so the UI can tick elapsed / remaining time.
        state = {"msg": "Starting...", "frac": 0.0, "result": None, "error": None, "est": None}
        transcriber = GeminiTranscriber(api_keys=API_KEYS)

        def progress(msg: str, frac: float) -> None:      # called from the worker thread
            state["msg"], state["frac"] = msg, frac
            state["est"] = transcriber.last_estimate

        def work() -> None:
            try:
                state["result"] = transcriber.transcribe(tmp_path, opts, progress)
            except Exception as e:
                state["error"] = e

        th = threading.Thread(target=work, daemon=True)
        th.start()
        while th.is_alive():
            elapsed = time.time() - t_start
            est = state["est"]
            status.info(state["msg"])
            if est:
                remaining = max(est - elapsed, 0.0)
                frac = max(state["frac"], min(elapsed / (est * 1.15), 0.95))
                timer.caption(f"⏱️ Elapsed {fmt_eta(elapsed)} · estimated total ~{fmt_eta(est)} · "
                              f"remaining ~{fmt_eta(remaining) if remaining > 0 else 'almost done'}")
            else:
                frac = state["frac"]
                timer.caption(f"⏱️ Elapsed {fmt_eta(elapsed)}")
            prog.progress(min(max(frac, 0.0), 1.0))
            time.sleep(0.5)
        th.join()
        if state["error"]:
            raise state["error"]
        result = state["result"]

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

    prog.progress(1.0)
    st.session_state.update(result=result, fixed_cues=fixed_cues, stem=stem, translations={})
    took = time.time() - t_start
    timer.caption(f"⏱️ Took {fmt_eta(took)} (estimate was ~{fmt_eta(transcriber.last_estimate or 0)})")
    status.success(
        f"Done · {result.duration / 60:.1f} min · {result.chunks} chunk(s) · {len(result.words)} timed words · "
        f"speakers: {', '.join(result.speakers) or 'n/a'}"
    )

# ---------------------------------------------------------------------------
# Step 2 - images (optional): slides, whiteboard, handwritten notes, documents
# ---------------------------------------------------------------------------
st.header("2️⃣ Images (optional): slides · whiteboard · notes · documents")
st.caption("Upload photos of the lecture slides, whiteboard or handwritten notes. The app reads the text (OCR), "
           "describes the images and can answer questions about them. The extracted text can be used together with the "
           "transcript in step 4.")

img_files = st.file_uploader("Images (up to 10)", type=IMAGE_TYPES, accept_multiple_files=True, key="img_upload")
img_files = (img_files or [])[:10]
if img_files:
    cols = st.columns(min(len(img_files), 5))
    for i, f in enumerate(img_files):
        cols[i % len(cols)].image(f, caption=f.name, use_container_width=True)

ic1, ic2, ic3 = st.columns([2, 1, 1])
img_lang = ic1.selectbox("Output language (description / answers)", OUTPUT_LANGS, index=0, key="img_lang")
ic2.write("")
ic2.write("")
do_extract = ic2.button("🔍 Extract text & describe", type="primary", use_container_width=True, disabled=not img_files)
ic3.write("")
ic3.write("")
if ic3.button("🗑️ Clear image results", use_container_width=True, disabled="images" not in st.session_state):
    for k in ("images", "image_count", "image_answer"):
        st.session_state.pop(k, None)
    reset_generated()

if do_extract:
    with st.spinner(f"Reading {len(img_files)} image(s)..."):
        try:
            payload = [(f.getvalue(), f.type or "image/jpeg") for f in img_files]
            st.session_state["images"] = ContentGenerator(api_keys=API_KEYS).analyse_images(payload, language=img_lang)
            st.session_state["image_count"] = len(img_files)
            st.session_state.pop("image_answer", None)
            reset_generated()
        except Exception as e:
            st.error(f"Image analysis failed: {e}")

img = st.session_state.get("images")
if img is not None:
    st.success(f"{img.title} · {img.content_type} · language: {img.detected_language}")
    a, b = st.columns([1, 1])
    with a:
        st.markdown("**Description**")
        st.write(img.description)
        st.markdown("**Key points**")
        for k in img.key_points:
            st.markdown(f"- {k}")
    with b:
        st.markdown("**Extracted text**")
        show_full_text(img.extracted_text, "img_text", height=300)
    st.download_button("⬇️ Image analysis .md", image_extraction_to_markdown(img), "images.md", key="dl_img")
    st.checkbox("Use the extracted text together with the transcript in step 4 (notes / quiz / minutes / translation)",
                value=True, key="use_images")

    st.markdown("**Ask something about the images**")
    qa1, qa2 = st.columns([4, 1])
    question = qa1.text_input("Question", placeholder="e.g. What does the diagram on slide 2 show? / Is formula ka matlab?",
                              key="img_question", label_visibility="collapsed")
    qa2.write("")
    if qa2.button("💬 Ask", use_container_width=True, disabled=not question.strip()):
        with st.spinner("Looking at the images..."):
            try:
                payload = [(f.getvalue(), f.type or "image/jpeg") for f in img_files]
                if not payload:
                    st.warning("Upload the images again to ask questions (files are not kept after a reload).")
                else:
                    ctx = st.session_state["result"].text if "result" in st.session_state else ""
                    st.session_state["image_answer"] = ContentGenerator(api_keys=API_KEYS).ask_images(
                        payload, question, language=img_lang, context=ctx)
            except Exception as e:
                st.error(f"Question failed: {e}")
    if st.session_state.get("image_answer"):
        st.info(st.session_state["image_answer"])

# ---------------------------------------------------------------------------
# Step 3 - transcript outputs
# ---------------------------------------------------------------------------
result = st.session_state.get("result")
if result is None and img is None:
    st.info("Generate a transcript (step 1) and/or analyse images (step 2) to continue.")
    st.stop()

stem = safe_name(st.session_state.get("stem", "images"))
cues = None
if result is not None:
    cues = build_cues(result, st.session_state.get("fixed_cues"))
    srt, vtt = to_srt(cues), to_vtt(cues)

    st.header("3️⃣ Transcript")
    st.caption(
        f"{len(result.text):,} characters · {len(cues)} subtitle cues · last cue ends at "
        f"{fmt_time(cues[-1].end, ms=False) if cues else '-'} · media length {fmt_time(result.duration or 0, ms=False)}"
    )

    t_txt, t_spk, t_srt, t_vtt = st.tabs(["📝 Transcript", "🗣️ Speakers", "🎞️ SRT", "🎞️ VTT"])
    with t_txt:
        st.download_button("⬇️ Download .txt", result.text, f"{stem}.txt", "text/plain", key="dl_txt")
        show_full_text(result.text, "transcript_full")
    with t_spk:
        if result.words and result.speakers:
            sp = speaker_transcript(result.words)
            st.download_button("⬇️ Download speakers .txt", sp, f"{stem}.speakers.txt", "text/plain", key="dl_spk")
            show_full_text(sp, "speakers_full")
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

# ---------------------------------------------------------------------------
# Step 4 - extras, each on its own button
# ---------------------------------------------------------------------------
src = source_text()
what = " + ".join(x for x, ok in (("transcript", result is not None),
                                  ("image text", img is not None and st.session_state.get("use_images", True))) if ok)
st.header("4️⃣ Generate more")
st.caption(f"Source: **{what}** · nothing here runs automatically, press a button to generate.")

x_tr, x_quiz, x_notes, x_mom = st.tabs(["🌐 Translation", "❓ Quiz (MCQs)", "📚 Notes", "📋 Meeting minutes"])

# ---- translation ----------------------------------------------------------
with x_tr:
    tc1, tc2 = st.columns([2, 1])
    target_lang = tc1.selectbox("Target language", TRANSLATION_TARGETS, index=0)
    tc2.write("")
    tc2.write("")
    if tc2.button("🌐 Translate", type="primary", use_container_width=True):
        with st.spinner(f"Translating to {target_lang}..."):
            try:
                gen = ContentGenerator(api_keys=API_KEYS)
                tr_text = gen.translate(src, target_lang)
                entry = {"text": tr_text}
                if cues:
                    tr_cues = gen.translate_cues(cues, target_lang)
                    entry.update(srt=to_srt(tr_cues), vtt=to_vtt(tr_cues))
                st.session_state.setdefault("translations", {})[target_lang] = entry
            except Exception as e:
                st.error(f"Translation failed: {e}")

    translations = st.session_state.get("translations", {})
    if translations:
        langs = list(translations)
        pick = st.radio("Generated translations", langs, index=len(langs) - 1, horizontal=True)
        tr = translations[pick]
        d1, d2, d3 = st.columns(3)
        d1.download_button("⬇️ Translation .txt", tr["text"], f"{stem}.{pick}.txt", key=f"dl_tr_txt_{pick}")
        if "srt" in tr:
            d2.download_button("⬇️ Translated .srt", tr["srt"], f"{stem}.{pick}.srt", key=f"dl_tr_srt_{pick}")
            d3.download_button("⬇️ Translated .vtt", tr["vtt"], f"{stem}.{pick}.vtt", key=f"dl_tr_vtt_{pick}")
            p1, p2 = st.tabs(["Text", "SRT"])
            with p1:
                show_full_text(tr["text"], f"tr_text_{pick}")
            with p2:
                show_code_full(tr["srt"], f"tr_srt_{pick}")
        else:
            show_full_text(tr["text"], f"tr_text_{pick}")

# ---- quiz -----------------------------------------------------------------
with x_quiz:
    q1, q2, q3, q4 = st.columns([1, 1, 1, 1])
    n_q = q1.slider("Questions", 3, 20, 5)
    difficulty = q2.select_slider("Difficulty", ["easy", "medium", "hard"], value="medium")
    quiz_lang = q3.selectbox("Quiz language", OUTPUT_LANGS, index=0)
    q4.write("")
    q4.write("")
    if q4.button("❓ Generate quiz", type="primary", use_container_width=True):
        with st.spinner("Generating MCQs..."):
            try:
                q = ContentGenerator(api_keys=API_KEYS).quiz(src, n=n_q, difficulty=difficulty, language=quiz_lang)
                st.session_state["quiz"] = q
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
        st.download_button("⬇️ Quiz .md", quiz_to_markdown(q), f"{stem}.quiz.md", key="dl_quiz_md")

# ---- notes ----------------------------------------------------------------
with x_notes:
    n1, n2, n3 = st.columns([2, 2, 1])
    notes_lang = n1.selectbox("Notes language", OUTPUT_LANGS, index=0, key="notes_lang")
    notes_kind = n2.radio("Format", ["Point-wise notes (detailed bullets)", "Summary notes (short)"],
                          index=0, key="notes_kind")
    n3.write("")
    n3.write("")
    if n3.button("📚 Generate notes", type="primary", use_container_width=True):
        with st.spinner("Writing notes..."):
            try:
                gen = ContentGenerator(api_keys=API_KEYS)
                if notes_kind.startswith("Point"):
                    st.session_state["point_notes"] = gen.point_notes(src, language=notes_lang)
                else:
                    st.session_state["notes"] = gen.notes(src, language=notes_lang)
            except Exception as e:
                st.error(f"Notes failed: {e}")

    p = st.session_state.get("point_notes")
    if p:
        st.markdown(f"### 📌 {p.title}")
        for s in p.sections:
            st.markdown(f"**{s.heading}**")
            for pt in s.points:
                st.markdown(f"- {pt}")
        st.markdown("**Key takeaways**")
        for k in p.key_takeaways:
            st.markdown(f"- {k}")
        st.download_button("⬇️ Point-wise notes .md", point_notes_to_markdown(p), f"{stem}.points.md", key="dl_points")

    n = st.session_state.get("notes")
    if n:
        if p:
            st.divider()
        st.markdown("### 📝 Summary notes")
        st.write(n.summary)
        st.markdown("**Key points**")
        for kp in n.key_points:
            st.markdown(f"- {kp}")
        st.markdown("**Chapters**")
        for i, ch in enumerate(n.chapters, 1):
            st.markdown(f"{i}. {ch}")
        st.markdown("**Keywords:** " + ", ".join(n.keywords))
        st.download_button("⬇️ Summary notes .md", notes_to_markdown(n, f"Notes: {stem}"), f"{stem}.notes.md", key="dl_notes")

# ---- meeting minutes --------------------------------------------------------
with x_mom:
    st.caption("For meetings, discussions, interviews or speeches: agenda, decisions, action items, next steps.")
    m1, m2, m3 = st.columns([2, 2, 1])
    mom_lang = m1.selectbox("Minutes language", OUTPUT_LANGS, index=0, key="mom_lang")
    mom_date = m2.date_input("Meeting date", value=date.today(), key="mom_date")
    m3.write("")
    m3.write("")
    if m3.button("📋 Generate minutes", type="primary", use_container_width=True):
        with st.spinner("Writing minutes of meeting..."):
            try:
                st.session_state["minutes"] = ContentGenerator(api_keys=API_KEYS).meeting_minutes(src, language=mom_lang)
            except Exception as e:
                st.error(f"Minutes failed: {e}")

    m = st.session_state.get("minutes")
    if m:
        st.markdown(f"### 📋 {m.title}")
        st.markdown(f"**Date:** {mom_date}  ·  **Type:** {m.meeting_type}  ·  **Participants:** {', '.join(m.participants) or '-'}")
        c_a, c_b = st.columns(2)
        with c_a:
            st.markdown("**Agenda**")
            for i, a in enumerate(m.agenda, 1):
                st.markdown(f"{i}. {a}")
            st.markdown("**Decisions**")
            for d in m.decisions or ["None recorded"]:
                st.markdown(f"- {d}")
            st.markdown("**Open questions**")
            for qn in m.open_questions or ["None"]:
                st.markdown(f"- {qn}")
        with c_b:
            st.markdown("**Discussion summary**")
            st.write(m.discussion_summary)
            st.markdown("**Key points**")
            for k in m.key_points:
                st.markdown(f"- {k}")
            st.markdown("**Next steps**")
            for s in m.next_steps or ["None"]:
                st.markdown(f"- {s}")
        st.markdown("**Action items**")
        if m.action_items:
            st.table([{"#": i, "Task": a.task, "Owner": a.owner, "Deadline": a.deadline}
                      for i, a in enumerate(m.action_items, 1)])
        else:
            st.caption("No action items were identified.")
        st.download_button("⬇️ Minutes .md", minutes_to_markdown(m, date=str(mom_date)), f"{stem}.minutes.md", key="dl_minutes")
