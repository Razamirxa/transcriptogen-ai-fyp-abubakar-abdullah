from transcriptogen.models import Word
from transcriptogen.subtitles import (
    cues_from_text,
    cues_from_words,
    fmt_time,
    speaker_transcript,
    to_srt,
    to_vtt,
)


def _words():
    return [
        Word("Hello", 0.0, 0.4, "Speaker 1"),
        Word("everyone", 0.45, 0.9, "Speaker 1"),
        Word("welcome", 0.95, 1.4, "Speaker 1"),
        # long pause -> new cue
        Word("Thanks", 3.0, 3.3, "Speaker 1"),
        # speaker change -> new cue
        Word("Hi", 3.4, 3.6, "Speaker 2"),
        Word("there", 3.65, 3.9, "Speaker 2"),
    ]


def test_fmt_time():
    assert fmt_time(0) == "00:00:00,000"
    assert fmt_time(3661.5, ".") == "01:01:01.500"
    assert fmt_time(59.9996) == "00:01:00,000"
    assert fmt_time(75, ms=False) == "00:01:15"


def test_cues_split_on_gap_and_speaker():
    cues = cues_from_words(_words())
    assert [c.text for c in cues] == ["Hello everyone welcome", "Thanks", "Hi there"]
    assert cues[0].speaker == "Speaker 1" and cues[2].speaker == "Speaker 2"
    assert cues[0].start == 0.0 and cues[0].end == 1.4
    assert [c.index for c in cues] == [1, 2, 3]


def test_cues_split_on_length():
    words = [Word(f"w{i}", i * 0.2, i * 0.2 + 0.1, None) for i in range(60)]
    cues = cues_from_words(words, max_chars=20, max_duration=100)
    assert all(len(c.text) <= 20 for c in cues)
    assert sum(len(c.text.split()) for c in cues) == 60


def test_srt_and_vtt_format():
    cues = cues_from_words(_words())
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,400\nSpeaker 1: Hello everyone welcome\n")
    vtt = to_vtt(cues)
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.400\n<v Speaker 1>Hello")
    assert "Speaker" not in to_srt(cues, with_speaker=False)


def test_text_fallback_spreads_evenly():
    cues = cues_from_text("line one\n\nline two\nline three", duration=30)
    assert len(cues) == 3
    assert cues[0].start == 0 and abs(cues[2].end - 30) < 1e-6


def test_speaker_transcript():
    txt = speaker_transcript(_words())
    assert txt.startswith("[00:00:00] Speaker 1: Hello everyone welcome Thanks")
    assert "[00:00:03] Speaker 2: Hi there" in txt
