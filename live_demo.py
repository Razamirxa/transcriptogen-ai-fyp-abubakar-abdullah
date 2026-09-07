"""Demo: stream an audio/video file through gemini-3.5-transcribe-live and print captions.

    uv run live_demo.py samples/sample_lecture.wav
    uv run live_demo.py lecture.mp4 --lang ur-PK --realtime
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from transcriptogen.live import file_to_pcm, pcm_chunks, transcribe_stream


async def run(path: str, langs: list[str], smart: bool, realtime: bool, manual_vad: bool) -> None:
    pcm = file_to_pcm(path)
    print(f"Streaming {len(pcm) / 32000:.1f}s of audio to gemini-3.5-transcribe-live ...")
    finals: list[str] = []
    async for ev in transcribe_stream(pcm_chunks(pcm), language_codes=langs, smart=smart,
                                      realtime=realtime, manual_vad=manual_vad):
        if ev.final:
            finals.append(ev.text)
            sys.stdout.write("\r" + " " * 100 + "\r")
            print("FINAL  :", ev.text)
        else:
            sys.stdout.write("\rinterim: " + ev.text[-90:].ljust(90))
            sys.stdout.flush()
    print("\n--- transcript ---\n" + " ".join(finals))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("--lang", nargs="*", default=[], help="BCP-47 hints, e.g. ur-PK (default auto)")
    p.add_argument("--smart", action="store_true", help="SMART mode (removes fillers)")
    p.add_argument("--realtime", action="store_true", help="pace audio at real speed like a microphone")
    p.add_argument("--auto-vad", action="store_true", help="let the server detect speech segments (mic-style)")
    a = p.parse_args()
    asyncio.run(run(a.source, a.lang, a.smart, a.realtime, not a.auto_vad))


if __name__ == "__main__":
    main()
