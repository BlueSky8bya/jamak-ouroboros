"""Deterministic subtitle noise filters."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .stt import SttSegment

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)
_WORDS = re.compile(r"[^\w가-힣]+", re.UNICODE)

# Conservative: only short standalone audience replies, not full sentences.
_STANDALONE_AUDIENCE_RESPONSES = {
    "네",
    "네네",
    "예",
    "예예",
    "넵",
}


def _normalize_reply(text: str) -> str:
    return _NON_WORD.sub("", text).strip()


def is_standalone_audience_response(text: str) -> bool:
    """Return True when a subtitle is only a short audience response."""
    return _normalize_reply(text) in _STANDALONE_AUDIENCE_RESPONSES


def filter_standalone_audience_responses(
    segments: list[SttSegment],
) -> list[SttSegment]:
    return [
        seg
        for seg in segments
        if not is_standalone_audience_response(seg.text)
    ]


def _compact(text: str) -> str:
    return _WORDS.sub("", text).lower()


def is_prompt_echo(text: str, prompt_text: str) -> bool:
    """True when a subtitle is whisper regurgitating its initial_prompt.

    faster-whisper can emit the initial_prompt verbatim over silent or
    music-only stretches (a known hallucination). Those show up as
    subtitles that are (almost) a contiguous slice of the prompt.
    """
    nt = _compact(text)
    npt = _compact(prompt_text)
    if len(nt) < 6 or not npt:
        return False
    if nt in npt:
        return True
    match = SequenceMatcher(None, nt, npt).find_longest_match(0, len(nt), 0, len(npt))
    return match.size >= 0.8 * len(nt)


# The keyword-list sentence whisper historically echoed (old default
# initial_prompt). Kept so repair can recognise leaked prompts in videos
# transcribed before we stopped feeding an initial_prompt, even though the
# live glossary prompt has since changed.
KNOWN_PROMPT_TEMPLATES = (
    "허경영 강연입니다. 신인, 축지법, 공중부양, 하늘궁 같은 용어가 나옵니다.",
    "신인, 축지법, 공중부양, 하늘궁 같은 용어가 나옵니다.",
)


def is_known_prompt_leak(text: str) -> bool:
    """True when text matches a known leaked-prompt template (prompt-agnostic)."""
    return any(is_prompt_echo(text, tmpl) for tmpl in KNOWN_PROMPT_TEMPLATES)


def cascade_indices(texts: list[str], min_run: int = 2, min_len: int = 6) -> set[int]:
    """Indices in a run of >=min_run consecutive identical subtitles.

    Whisper's prompt-echo hallucination repeats the *same* sentence across many
    adjacent segments (condition_on_previous_text carrying the loop forward).
    Real speech almost never repeats an identical >=6-char sentence back to
    back, so a consecutive-duplicate run is a reliable hallucination signature
    — and, unlike is_prompt_echo, it needs no knowledge of the prompt text.
    """
    norm = [_compact(t) for t in texts]
    flagged: set[int] = set()
    i, n = 0, len(norm)
    while i < n:
        j = i
        while j + 1 < n and norm[j + 1] == norm[i] and len(norm[i]) >= min_len:
            j += 1
        if j - i + 1 >= min_run:
            flagged.update(range(i, j + 1))
        i = j + 1
    return flagged
