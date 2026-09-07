"""Text generators on top of the transcript: translation, subtitles translation,
MCQ quiz, summary/notes. Uses Gemini text models with JSON schemas."""
from __future__ import annotations

import json
import re
import time
from typing import Any

from google import genai
from pydantic import BaseModel, Field

from . import config
from .subtitles import Cue


# ----------------------------------------------------------------------------
# Schemas (structured output)
# ----------------------------------------------------------------------------
class AnswerOption(BaseModel):
    text: str
    is_correct: bool
    rationale: str = Field(description="Why this option is right or wrong (1 sentence)")


class Question(BaseModel):
    question: str
    options: list[AnswerOption] = Field(description="Exactly 4 options, exactly one correct")
    hint: str = ""
    topic: str = ""


class Quiz(BaseModel):
    title: str
    questions: list[Question]


class TranslatedCue(BaseModel):
    index: int
    text: str


class TranslatedCues(BaseModel):
    cues: list[TranslatedCue]


class StudyNotes(BaseModel):
    summary: str = Field(description="3-5 sentence summary")
    key_points: list[str]
    keywords: list[str]
    chapters: list[str] = Field(description="Suggested section/chapter titles in order")


# ----------------------------------------------------------------------------
# Prompts (kept from earlier Gemini projects, tuned for Urdu/English mixes)
# ----------------------------------------------------------------------------
TRANSLATE_PROMPT = """Translate the following transcript into {target}.

Rules:
- Keep speaker labels (e.g. "Speaker 1:") and paragraph structure exactly as they are.
- Keep technical terms, product names, brand names, acronyms and code identifiers in English.
- If the target is Urdu, write in proper Urdu script (never Roman Urdu, never Devanagari).
- Do not add commentary. Output only the translated transcript.

Transcript:
---
{text}
---"""

TRANSLATE_CUES_PROMPT = """You are translating subtitle cues into {target}.
Translate the `text` of every cue and return the SAME `index` values.
Keep each translation short enough to read as a subtitle (roughly the same length as the source).
Keep technical terms / names in English. For Urdu use Urdu script only.

Cues (JSON):
{cues_json}"""

QUIZ_PROMPT = """Create a multiple-choice quiz with {n} questions from the transcript below.
Difficulty: {difficulty}. Language of the quiz: {language}.
- Exactly 4 options per question, exactly one correct.
- Questions must test understanding of the actual content (facts, concepts, reasoning), not trivia about wording.
- Provide a short rationale for every option and a one-line hint.
- Give a short quiz title.

Transcript:
---
{text}
---"""

URDU_SCRIPT_FIX_PROMPT = """The transcript below was produced by a speech recogniser. The speech is Urdu, but the
recogniser wrote some or all of it in Hindi / Devanagari script (हिंदी). Convert it so that:

## Language Guidelines
- **All Urdu content is written in proper Urdu script (اردو رسم الخط)** - convert every Devanagari word to Urdu script.
- **English words/phrases stay in English** exactly as spoken (technical terms, brand names, acronyms).
- **Mixed language**: keep the natural Urdu/English mix, only change the script of the Urdu portions.
- **DO NOT use Roman Urdu/transliteration** (no Urdu words in Latin letters).
- **DO NOT keep or add Hindi / Devanagari script** - ALWAYS use Urdu script (اردو).
- Do not translate, summarise, add or remove words. Keep speaker labels, line breaks and punctuation.

## Example
Input:  Speaker 1: यह बहुत अहम मौज़ू है और we need to discuss this properly.
Output: Speaker 1: یہ بہت اہم موضوع ہے اور we need to discuss this properly.

Output only the converted transcript.

Transcript:
---
{text}
---"""

NOTES_PROMPT = """Read the transcript and produce study notes in {language}:
a concise summary, 5-10 key points, 5-15 keywords, and ordered chapter titles that describe how the content flows.

Transcript:
---
{text}
---"""

MAX_CHARS = 120_000  # keep well inside the context window for long lectures

# Error classes seen in practice:
#  - 503 "high demand" / 500            -> wait and retry the same model
#  - 429 quota / free_tier / exhausted  -> switch model, then switch API key
#  - "credits are depleted" (billing)   -> switch API key
#  - 404 model not available            -> switch model
_TRANSIENT = ("503", "UNAVAILABLE", "500", "INTERNAL", "DEADLINE")
_QUOTA = ("429", "RESOURCE_EXHAUSTED", "quota", "free_tier", "rate limit", "too_many_requests")
# NB: free-tier quota messages also say "check your plan and billing details",
# so only the prepaid-credit wording counts as a billing (whole project) failure.
_BILLING = ("credits are depleted", "prepayment credit")
_MODEL_GONE = ("404", "NOT_FOUND", "no longer available")
_RETRY_IN = re.compile(r"retry in ([\d.]+)\s*s|retryDelay['\"]?:\s*['\"]?(\d+)s", re.I)


def retry_delay_seconds(e: Exception) -> float | None:
    """Seconds the API asked us to wait ("Please retry in 24.4s" / retryDelay: '24s')."""
    m = _RETRY_IN.search(str(e))
    if not m:
        return None
    return float(m.group(1) or m.group(2))


def classify_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if any(b in low for b in _BILLING):
        return "billing"
    if any(q.lower() in low for q in _QUOTA):
        return "quota"
    if any(m.lower() in low for m in _MODEL_GONE):
        return "model_gone"
    if any(t.lower() in low for t in _TRANSIENT):
        return "transient"
    return "fatal"


class QuotaExhaustedError(RuntimeError):
    """Every configured (API key, model) combination is out of quota."""


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    """True when the text contains Hindi / Devanagari characters."""
    return bool(_DEVANAGARI.search(text or ""))


def _clean(text: str) -> str:
    """Drop markdown fences / '---' delimiters the model sometimes echoes back."""
    lines = text.strip().splitlines()

    def _is_delim(ln: str) -> bool:
        s = ln.strip()
        return s == "---" or s.startswith("```")

    while lines and _is_delim(lines[0]):
        lines.pop(0)
    while lines and _is_delim(lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()


class ContentGenerator:
    """Text generation with automatic (API key x model) rotation.

    Order of preference: primary key with TEXT_MODEL, then the other
    TEXT_MODEL_CANDIDATES on the same key, then the same list on the next key.
    A working combination is remembered for the rest of the session.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        api_keys: list[str] | None = None,
        models: list[str] | None = None,
    ):
        keys = list(api_keys or ([api_key] if api_key else config.get_api_keys()))
        if api_key and api_key not in keys:
            keys.insert(0, api_key)
        # when a single explicit key is given, still fall back to .env keys
        for k in config.get_api_keys() if api_key else []:
            if k not in keys:
                keys.append(k)
        self.keys = keys
        self.models = list(models or config.TEXT_MODEL_CANDIDATES)
        if model:
            self.models = [model] + [m for m in self.models if m != model]
        self._clients: dict[str, genai.Client] = {}
        self._ki = 0   # current key index
        self._mi = 0   # current model index

    # -- helpers -------------------------------------------------------------
    @property
    def model(self) -> str:
        return self.models[self._mi]

    @property
    def client(self) -> genai.Client:
        key = self.keys[self._ki]
        if key not in self._clients:
            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def _advance(self, kind: str) -> bool:
        """Move to the next (key, model) combination. Returns False when exhausted."""
        if kind == "billing":                    # whole project unusable -> next key
            self._ki, self._mi = self._ki + 1, 0
        elif self._mi + 1 < len(self.models):    # quota / model gone -> next model
            self._mi += 1
        else:                                    # models exhausted -> next key
            self._ki, self._mi = self._ki + 1, 0
        return self._ki < len(self.keys)

    # A per-minute rate limit asks for a few seconds; a daily quota asks for hours.
    MAX_WAIT_FOR_QUOTA = 20.0

    def _generate(self, prompt: str, cfg: dict[str, Any], *, transient_retries: int = 3) -> Any:
        """generate_content with backoff on transient errors and rotation on quota errors.

        Short rate-limit waits (<= MAX_WAIT_FOR_QUOTA s) are honoured on the same
        model before rotating; daily-quota errors rotate immediately.
        """
        errors: list[str] = []
        while True:
            waited_quota = 0
            attempt = 0
            while True:
                try:
                    return self.client.models.generate_content(model=self.model, contents=prompt, config=cfg)
                except Exception as e:
                    kind = classify_error(e)
                    short = str(e).split("{")[0].strip()[:120]
                    if kind == "transient" and attempt < transient_retries:
                        attempt += 1
                        time.sleep(3 * (2 ** (attempt - 1)))   # 3s, 6s, 12s
                        continue
                    if kind == "quota":
                        delay = retry_delay_seconds(e)
                        if delay is not None and delay <= self.MAX_WAIT_FOR_QUOTA and waited_quota < 2:
                            waited_quota += 1
                            time.sleep(delay + 1)
                            continue
                    if kind in ("quota", "billing", "model_gone", "transient"):
                        errors.append(f"key#{self._ki + 1}/{self.model}: {kind} ({short})")
                        break
                    raise
            if not self._advance(kind):
                raise QuotaExhaustedError(
                    "All API keys / text models are exhausted or unavailable:\n  " + "\n  ".join(errors)
                    + "\nAdd another key as GEMINI_API_KEY_2 in .env or wait for the daily quota reset."
                )

    def _text(self, prompt: str, temperature: float = 0.3) -> str:
        r = self._generate(prompt, {"temperature": temperature})
        return _clean(r.text or "")

    def _json(self, prompt: str, schema: type[BaseModel], temperature: float = 0.4) -> Any:
        r = self._generate(
            prompt,
            {
                "temperature": temperature,
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        parsed = getattr(r, "parsed", None)
        if parsed is not None:
            return parsed
        return schema.model_validate_json(_clean(r.text or "") or "{}")

    # -- public --------------------------------------------------------------
    def fix_urdu_script(self, text: str) -> str:
        """Rewrite Devanagari (Hindi) output as Urdu script; English is left untouched."""
        if not has_devanagari(text):
            return text
        out: list[str] = []
        # Convert in blocks so very long transcripts stay inside output limits.
        paras = text.split("\n\n")
        block: list[str] = []
        size = 0
        for p in paras + [None]:
            if p is None or size + len(p) > 12_000:
                if block:
                    out.append(self._text(URDU_SCRIPT_FIX_PROMPT.format(text="\n\n".join(block)), temperature=0.1))
                block, size = [], 0
            if p is not None:
                block.append(p)
                size += len(p)
        return "\n\n".join(out)

    def fix_urdu_script_cues(self, cues: list[Cue], batch: int = 80) -> list[Cue]:
        """Same as fix_urdu_script but for subtitle cues (timing preserved)."""
        if not any(has_devanagari(c.text) for c in cues):
            return cues
        out: list[Cue] = []
        for i in range(0, len(cues), batch):
            part = cues[i:i + batch]
            payload = [{"index": c.index, "text": c.text} for c in part]
            prompt = URDU_SCRIPT_FIX_PROMPT.replace(
                "Transcript:\n---\n{text}\n---",
                "The transcript is given as JSON subtitle cues. Convert the `text` of every cue and "
                "return the SAME `index` values.\n\nCues (JSON):\n" + json.dumps(payload, ensure_ascii=False),
            )
            res: TranslatedCues = self._json(prompt, TranslatedCues, temperature=0.1)
            by_idx = {t.index: t.text for t in res.cues}
            for c in part:
                out.append(Cue(c.index, c.start, c.end, by_idx.get(c.index, c.text), c.speaker))
        return out

    def translate(self, text: str, target: str) -> str:
        return self._text(TRANSLATE_PROMPT.format(target=target, text=text[:MAX_CHARS]))

    def translate_cues(self, cues: list[Cue], target: str, batch: int = 80) -> list[Cue]:
        """Translate subtitle cues while keeping their timing."""
        out: list[Cue] = []
        for i in range(0, len(cues), batch):
            part = cues[i:i + batch]
            payload = [{"index": c.index, "text": c.text} for c in part]
            res: TranslatedCues = self._json(
                TRANSLATE_CUES_PROMPT.format(target=target, cues_json=json.dumps(payload, ensure_ascii=False)),
                TranslatedCues,
                temperature=0.2,
            )
            by_idx = {t.index: t.text for t in res.cues}
            for c in part:
                out.append(Cue(c.index, c.start, c.end, by_idx.get(c.index, c.text), c.speaker))
        return out

    def quiz(self, text: str, n: int = 5, difficulty: str = "medium", language: str = "English") -> Quiz:
        return self._json(
            QUIZ_PROMPT.format(n=n, difficulty=difficulty, language=language, text=text[:MAX_CHARS]), Quiz
        )

    def notes(self, text: str, language: str = "English") -> StudyNotes:
        return self._json(NOTES_PROMPT.format(language=language, text=text[:MAX_CHARS]), StudyNotes, temperature=0.3)


def quiz_to_markdown(q: Quiz, *, show_answers: bool = True) -> str:
    lines = [f"# {q.title}", ""]
    letters = "ABCD"
    for i, qu in enumerate(q.questions, 1):
        lines.append(f"**Q{i}. {qu.question}**")
        for j, o in enumerate(qu.options[:4]):
            lines.append(f"- {letters[j]}. {o.text}")
        if qu.hint:
            lines.append(f"  - _Hint: {qu.hint}_")
        if show_answers:
            correct = [letters[j] for j, o in enumerate(qu.options[:4]) if o.is_correct]
            lines.append(f"  - **Answer:** {', '.join(correct) or '?'}")
        lines.append("")
    return "\n".join(lines)
