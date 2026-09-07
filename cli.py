"""Command-line entry point.

Examples:
    uv run cli.py lecture.mp4
    uv run cli.py lecture.mp3 --lang ur-PK en-US --translate Urdu --quiz 5
    uv run cli.py "https://youtu.be/xyz" --no-diarization --out outputs/
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from transcriptogen.config import TranscribeOptions
from transcriptogen.generators import ContentGenerator, has_devanagari, quiz_to_markdown
from transcriptogen.subtitles import cues_from_text, cues_from_words, speaker_transcript, to_srt, to_vtt
from transcriptogen.transcriber import GeminiTranscriber
from transcriptogen.youtube import download_audio, is_url


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TranscriptoGen AI - Gemini 3.5 Transcribe pipeline")
    p.add_argument("source", help="audio/video file path or a YouTube URL")
    p.add_argument("--lang", nargs="*", default=[], help="BCP-47 hints, e.g. ur-PK en-US (default: auto)")
    p.add_argument("--no-diarization", action="store_true")
    p.add_argument("--no-timestamps", action="store_true")
    p.add_argument("--smart", action="store_true", help="smart mode (clean dictation; no speakers/timestamps)")
    p.add_argument("--vocab", nargs="*", default=[], help="custom vocabulary terms")
    p.add_argument("--translate", metavar="LANGUAGE", help="also translate transcript + subtitles")
    p.add_argument("--quiz", type=int, metavar="N", help="generate N MCQs")
    p.add_argument("--notes", action="store_true", help="generate summary / key points")
    p.add_argument("--keep-script", action="store_true",
                   help="do not convert Hindi/Devanagari output to Urdu script")
    p.add_argument("--out", default="outputs", help="output directory")
    a = p.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    src = a.source
    if is_url(src):
        print(f"Downloading {src} ...")
        path, info = download_audio(src)
        stem = (info.get("title") or info.get("id") or "youtube")[:60]
    else:
        path = Path(src)
        stem = path.stem
    stem = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in stem).strip() or "transcript"

    opts = TranscribeOptions(
        language_codes=a.lang,
        diarization=not a.no_diarization,
        word_timestamps=not a.no_timestamps,
        smart_mode=a.smart,
        custom_vocabulary=a.vocab,
    )

    def progress(msg: str, frac: float) -> None:
        print(f"[{frac * 100:5.1f}%] {msg}")

    t0 = time.time()
    tr = GeminiTranscriber()
    result = tr.transcribe(path, opts, progress)
    print(f"Transcribed {result.duration:.0f}s of audio in {time.time() - t0:.1f}s "
          f"(estimate was ~{tr.last_estimate:.0f}s) "
          f"({result.chunks} chunk(s), {len(result.words)} words, speakers={result.speakers})")

    if result.words:
        cues = cues_from_words(result.words)
    else:
        cues = cues_from_text(result.text, result.duration)

    # Urdu speech is sometimes written in Hindi (Devanagari); rewrite it in Urdu script.
    if has_devanagari(result.text) and not a.keep_script:
        print("Devanagari detected -> converting to Urdu script ...")
        gen = ContentGenerator()
        result.text = gen.fix_urdu_script(result.text)
        cues = gen.fix_urdu_script_cues(cues)
        # note: word-level entries in the JSON export keep the recogniser's original script

    (out / f"{stem}.txt").write_text(result.text, encoding="utf-8")
    if result.words:
        (out / f"{stem}.speakers.txt").write_text(speaker_transcript(result.words), encoding="utf-8")
    (out / f"{stem}.srt").write_text(to_srt(cues), encoding="utf-8")
    (out / f"{stem}.vtt").write_text(to_vtt(cues), encoding="utf-8")
    (out / f"{stem}.json").write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    if a.translate or a.quiz or a.notes:
        gen = ContentGenerator()
        if a.translate:
            print(f"Translating to {a.translate} ...")
            (out / f"{stem}.{a.translate}.txt").write_text(gen.translate(result.text, a.translate), encoding="utf-8")
            tcues = gen.translate_cues(cues, a.translate)
            (out / f"{stem}.{a.translate}.srt").write_text(to_srt(tcues), encoding="utf-8")
        if a.quiz:
            print(f"Generating {a.quiz} MCQs ...")
            q = gen.quiz(result.text, n=a.quiz)
            (out / f"{stem}.quiz.md").write_text(quiz_to_markdown(q), encoding="utf-8")
            (out / f"{stem}.quiz.json").write_text(q.model_dump_json(indent=2), encoding="utf-8")
        if a.notes:
            print("Generating notes ...")
            (out / f"{stem}.notes.json").write_text(gen.notes(result.text).model_dump_json(indent=2), encoding="utf-8")

    print(f"Saved outputs to {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
