"""Deterministic subtitle noise filters."""

from __future__ import annotations

import re

from .stt import SttSegment

_NON_WORD = re.compile(r"[\s\W_]+", re.UNICODE)

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
