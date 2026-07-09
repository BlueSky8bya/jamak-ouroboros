"""Stage 2.5 — Split: cut long whisper segments into subtitle-sized pieces.

Whisper emits breath-group segments that can run 20+ seconds — far too
much text for one subtitle. Word timestamps let us re-cut precisely:
prefer sentence boundaries (문장부호, 어미+pause), force a cut when a
piece would exceed the char/duration budget.
"""

from __future__ import annotations

import re

from ..config import MAX_CHARS_PER_LINE, MAX_LINES, MAX_SEGMENT_SECONDS
from .stt import SttSegment, Word

MAX_CHARS = MAX_CHARS_PER_LINE * MAX_LINES  # hard budget per subtitle (36)
SOFT_CHARS = 20  # at a sentence boundary past this length, cut proactively
BOUNDARY_GAP = 0.6  # silence between words that counts as a natural break

_SENT_END = re.compile(r"[.?!…]$|[다요죠지]\?*$")


def _text_of(words: list[Word]) -> str:
    return "".join(w.word for w in words).strip()


def _is_boundary(words: list[Word], i: int) -> bool:
    """Is position i (end of words[i]) a natural cut point?"""
    w = words[i].word.strip()
    if w.endswith(("?", ".", "!", "…")):
        return True
    if i + 1 < len(words) and words[i + 1].start - words[i].end >= BOUNDARY_GAP:
        return True
    return False


def _split_words(words: list[Word]) -> list[list[Word]]:
    pieces: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        text = _text_of(cur)
        dur = cur[-1].end - cur[0].start
        global_i = i  # index into full words list for boundary lookahead

        at_boundary = _is_boundary(words, global_i)
        over_soft = len(text) >= SOFT_CHARS
        over_hard = len(text) >= MAX_CHARS or dur >= MAX_SEGMENT_SECONDS

        if (at_boundary and over_soft) or over_hard:
            if over_hard and not at_boundary:
                # forced cut: back up to the last boundary inside cur if any
                back = None
                for k in range(len(cur) - 2, 0, -1):
                    if _is_boundary(words, global_i - (len(cur) - 1 - k)):
                        back = k
                        break
                if back is not None and back >= len(cur) // 3:
                    pieces.append(cur[: back + 1])
                    cur = cur[back + 1 :]
                    continue
            pieces.append(cur)
            cur = []
    if cur:
        # a tiny tail reads badly — glue it to the previous piece when the
        # merged text still fits the hard budget
        if (
            pieces
            and len(_text_of(cur)) <= 6
            and len(_text_of(pieces[-1] + cur)) <= MAX_CHARS
        ):
            pieces[-1] = pieces[-1] + cur
        else:
            pieces.append(cur)
    return pieces


def split_segments(segments: list[SttSegment]) -> list[SttSegment]:
    out: list[SttSegment] = []
    for seg in segments:
        if not seg.words or len(seg.text) <= MAX_CHARS:
            out.append(seg)
            continue
        for piece in _split_words(seg.words):
            text = _text_of(piece)
            if not text:
                continue
            out.append(
                SttSegment(
                    start=piece[0].start,
                    end=piece[-1].end,
                    text=text,
                    words=piece,
                    avg_logprob=seg.avg_logprob,
                )
            )
    return out
