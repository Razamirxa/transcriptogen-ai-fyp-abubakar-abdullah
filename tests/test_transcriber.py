"""Tests for request building and response parsing (no network)."""
from types import SimpleNamespace

from transcriptogen.config import TranscribeOptions
from transcriptogen.transcriber import (
    build_transcription_config,
    extract_words,
    normalise_speaker,
    parse_offset,
)


def test_parse_offset_variants():
    assert parse_offset("0.100s") == 0.1
    assert parse_offset("12s") == 12.0
    assert parse_offset("250ms") == 0.25
    assert parse_offset(1.5) == 1.5
    assert parse_offset(None) == 0.0
    assert parse_offset("garbage") == 0.0


def test_normalise_speaker():
    assert normalise_speaker("spk_1") == "Speaker 1"
    assert normalise_speaker("spk:0") == "Speaker 1"
    assert normalise_speaker("spk:2") == "Speaker 3"
    assert normalise_speaker("SPEAKER_2") == "Speaker 2"
    assert normalise_speaker(None) is None


def test_build_config_verbatim_with_everything():
    cfg = build_transcription_config(
        TranscribeOptions(language_codes=["ur-PK", "en-US"], diarization=True, word_timestamps=True,
                          custom_vocabulary=["Qdrant"])
    )
    assert cfg["language_codes"] == ["ur-PK", "en-US"]
    assert cfg["mode"] == {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}
    # custom vocab is dropped because it is incompatible with diarization / timestamps
    assert "custom_vocabulary" not in cfg


def test_build_config_smart_mode_and_vocab():
    cfg = build_transcription_config(TranscribeOptions(smart_mode=True, custom_vocabulary=["Gemini"]))
    assert cfg["mode"] == {"type": "smart"}
    assert cfg["custom_vocabulary"] == ["Gemini"]
    assert "language_codes" not in cfg  # auto-detect


def test_chunk_minutes_follow_limits():
    assert TranscribeOptions(diarization=True).chunk_minutes == 25
    assert TranscribeOptions(diarization=False, word_timestamps=False).chunk_minutes == 55
    assert TranscribeOptions(smart_mode=True).chunk_minutes == 55


def _fake_interaction():
    ann = [
        SimpleNamespace(type="word_info", text="Hello", start_offset="0.100s", end_offset="0.450s", speaker="spk_1"),
        SimpleNamespace(type="url_citation", text="ignored"),
        {"type": "word_info", "text": "world", "start_offset": "0.500s", "end_offset": "0.900s", "speaker": "spk_2"},
        SimpleNamespace(type="word_info", text="  ", start_offset="1s", end_offset="2s", speaker="spk_1"),
    ]
    content = SimpleNamespace(type="text", text="Hello world", annotations=ann)
    step = SimpleNamespace(type="model_output", content=[content])
    return SimpleNamespace(output_text="Hello world", steps=[step])


def test_extract_words_with_offset():
    words = extract_words(_fake_interaction(), offset=60.0)
    assert [w.text for w in words] == ["Hello", "world"]
    assert words[0].start == 60.1 and words[0].end == 60.45
    assert words[0].speaker == "Speaker 1" and words[1].speaker == "Speaker 2"


def test_estimate_seconds_is_sane():
    from transcriptogen.transcriber import estimate_seconds, fmt_eta

    annotated = TranscribeOptions(diarization=True, word_timestamps=True)
    plain = TranscribeOptions(diarization=False, word_timestamps=False)
    e_short = estimate_seconds(25, annotated)
    e_long = estimate_seconds(392, annotated)
    assert 4 <= e_short <= 12                      # measured ~5 s
    assert 18 <= e_long <= 35                      # measured ~22 s
    assert estimate_seconds(392, plain) < e_long   # plain mode is faster
    assert estimate_seconds(3600 * 1.5, annotated) > estimate_seconds(3600, annotated)  # more chunks
    assert fmt_eta(45) == "45s" and fmt_eta(125) == "2m 05s"


def test_extract_words_handles_missing_steps():
    assert extract_words(SimpleNamespace(output_text="x", steps=None)) == []
    assert extract_words({"output_text": "x"}) == []
