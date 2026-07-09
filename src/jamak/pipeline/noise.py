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
