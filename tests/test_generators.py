"""Retry / rotation logic for the text generators (no network)."""
from types import SimpleNamespace

import pytest

from transcriptogen import generators
from transcriptogen.generators import ContentGenerator, QuotaExhaustedError, _clean, classify_error


class _Models:
    """Scripted fake of client.models: each entry is an Exception to raise or text to return."""

    def __init__(self, script, log, key):
        self.script, self.log, self.key = script, log, key

    def generate_content(self, *, model, contents, config):
        self.log.append((self.key, model))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item, parsed=None)


def _gen(script, monkeypatch, keys=("k1", "k2"), models=("m1", "m2")):
    monkeypatch.setattr(generators.time, "sleep", lambda s: None)
    g = ContentGenerator.__new__(ContentGenerator)
    g.keys, g.models, g._ki, g._mi = list(keys), list(models), 0, 0
    log: list = []
    shared = list(script)
    g._clients = {k: SimpleNamespace(models=_Models(shared, log, k)) for k in keys}
    g.calls = log
    return g


def test_classify_error():
    assert classify_error(Exception("429 RESOURCE_EXHAUSTED quota free_tier")) == "quota"
    assert classify_error(Exception("429 Your prepayment credits are depleted")) == "billing"
    # free-tier quota text mentions "billing details" but is NOT a billing failure
    assert classify_error(Exception(
        "429 RESOURCE_EXHAUSTED. You exceeded your current quota, please check your plan and billing details. "
        "Quota exceeded for metric: generate_content_free_tier_requests, limit: 20. Please retry in 24.4s."
    )) == "quota"
    assert classify_error(Exception("503 UNAVAILABLE high demand")) == "transient"
    assert classify_error(Exception("404 NOT_FOUND no longer available")) == "model_gone"
    assert classify_error(Exception("400 INVALID_ARGUMENT")) == "fatal"


def test_has_devanagari():
    assert generators.has_devanagari("यह बहुत अहम है and English")
    assert not generators.has_devanagari("یہ بہت اہم ہے and English")
    assert not generators.has_devanagari("")


def test_clean_strips_delimiters():
    assert _clean("---\nhello\n---") == "hello"
    assert _clean("```json\n{\"a\":1}\n```") == '{"a":1}'
    assert _clean("  plain  ") == "plain"


def test_transient_retries_same_model(monkeypatch):
    g = _gen([Exception("503 UNAVAILABLE"), Exception("503 UNAVAILABLE"), "---\nOK\n---"], monkeypatch)
    assert g._text("p") == "OK"
    assert g.calls == [("k1", "m1")] * 3


def test_quota_switches_model_then_key(monkeypatch):
    g = _gen([Exception("429 quota free_tier"), Exception("429 quota free_tier"), "OK"], monkeypatch)
    assert g._text("p") == "OK"
    assert g.calls == [("k1", "m1"), ("k1", "m2"), ("k2", "m1")]
    # the working combination is remembered
    g._clients["k2"].models.script.append("AGAIN")
    assert g._text("p") == "AGAIN"
    assert g.calls[-1] == ("k2", "m1")


def test_retry_delay_parsing():
    assert generators.retry_delay_seconds(Exception("... Please retry in 1.186615514s.")) == pytest.approx(1.1866, 1e-3)
    assert generators.retry_delay_seconds(Exception("... 'retryDelay': '24s' ...")) == 24.0
    assert generators.retry_delay_seconds(Exception("no hint")) is None


def test_short_rate_limit_waits_on_same_model(monkeypatch):
    slept = []
    monkeypatch.setattr(generators.time, "sleep", lambda s: slept.append(s))
    g = _gen([Exception("429 quota. Please retry in 1.2s."), "OK"], monkeypatch)
    monkeypatch.setattr(generators.time, "sleep", lambda s: slept.append(s))
    assert g._text("p") == "OK"
    assert g.calls == [("k1", "m1"), ("k1", "m1")]      # same key & model
    assert slept and slept[0] == pytest.approx(2.2, 1e-6)


def test_long_daily_quota_rotates_immediately(monkeypatch):
    slept = []
    g = _gen([Exception("429 quota free_tier. Please retry in 3600s."), "OK"], monkeypatch)
    monkeypatch.setattr(generators.time, "sleep", lambda s: slept.append(s))
    assert g._text("p") == "OK"
    assert g.calls == [("k1", "m1"), ("k1", "m2")]
    assert slept == []


def test_billing_switches_key_immediately(monkeypatch):
    g = _gen([Exception("429 Your prepayment credits are depleted"), "OK"], monkeypatch)
    assert g._text("p") == "OK"
    assert g.calls == [("k1", "m1"), ("k2", "m1")]


def test_all_exhausted_raises(monkeypatch):
    g = _gen([Exception("429 quota")] * 4, monkeypatch)
    with pytest.raises(QuotaExhaustedError, match="GEMINI_API_KEY_2"):
        g._text("p")
    assert len(g.calls) == 4


def test_fatal_error_not_retried(monkeypatch):
    g = _gen([Exception("400 INVALID_ARGUMENT"), "never"], monkeypatch)
    with pytest.raises(Exception, match="400"):
        g._text("p")
    assert g.calls == [("k1", "m1")]


def test_markdown_converters():
    from transcriptogen.generators import (
        ActionItem, MeetingMinutes, NoteSection, PointNotes, StudyNotes,
        minutes_to_markdown, notes_to_markdown, point_notes_to_markdown,
    )

    p = PointNotes(title="Photosynthesis", sections=[NoteSection(heading="Stages", points=["Light reactions", "Calvin cycle"])],
                   key_takeaways=["Light -> chemical energy"])
    md = point_notes_to_markdown(p)
    assert md.startswith("# Photosynthesis\n\n## Stages\n- Light reactions\n- Calvin cycle")
    assert "## Key takeaways\n- Light -> chemical energy" in md

    m = MeetingMinutes(title="Sprint sync", meeting_type="team meeting", participants=["Speaker 1", "Speaker 2"],
                       agenda=["Status", "Blockers"], discussion_summary="Discussed progress.",
                       key_points=["On track"], decisions=["Ship Friday"],
                       action_items=[ActionItem(task="Fix login", owner="Speaker 2", deadline="Thursday")],
                       open_questions=[], next_steps=["Demo"])
    md = minutes_to_markdown(m, date="2026-09-11")
    assert "# Minutes of Meeting: Sprint sync" in md and "**Date:** 2026-09-11" in md
    assert "| 1 | Fix login | Speaker 2 | Thursday |" in md
    assert "## Open questions\n- None" in md

    n = StudyNotes(summary="S", key_points=["k1"], keywords=["kw"], chapters=["c1"])
    assert "## Summary\nS\n\n## Key points\n- k1" in notes_to_markdown(n)


def test_fix_urdu_script_skips_clean_text(monkeypatch):
    g = _gen([], monkeypatch)
    urdu = "Speaker 1: یہ بہت اہم موضوع ہے اور we need to discuss this."
    assert g.fix_urdu_script(urdu) == urdu
    assert g.calls == []


def test_fix_urdu_script_calls_model_when_devanagari(monkeypatch):
    g = _gen(["Speaker 1: یہ بہت اہم موضوع ہے"], monkeypatch)
    assert g.fix_urdu_script("Speaker 1: यह बहुत अहम मौज़ू है") == "Speaker 1: یہ بہت اہم موضوع ہے"
    assert g.calls == [("k1", "m1")]
