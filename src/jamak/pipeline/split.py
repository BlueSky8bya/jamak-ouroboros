"""Stage 2.5 — Split: cut long whisper segments into subtitle-sized pieces.

Whisper emits breath-group segments that can run 20+ seconds — far too
much text for one subtitle. Word timestamps let us re-cut precisely:
prefer sentence boundaries (문장부호, 어미+pause), force a cut when a
piece would exceed the char/duration budget.
"""

from __future__ import annotations

import re
import statistics

from ..config import MAX_CHARS_PER_LINE, MAX_LINES, MAX_SEGMENT_SECONDS
from .stt import SttSegment, Word

DEFAULT_MAX_CHARS = MAX_CHARS_PER_LINE * MAX_LINES  # hard budget per subtitle (36)
DEFAULT_SOFT_CHARS = 20  # at a sentence boundary past this length, cut proactively
BOUNDARY_GAP = 0.6  # silence between words that counts as a natural break
MIN_LEARN_SAMPLES = 40  # need this many reviewed subtitles before learning length


def learned_line_budget() -> tuple[int, int] | None:
    """(soft, hard) char budget learned from human-reviewed subtitles.

    The reviewer's final subtitles ARE their preferred length. We fit the
    split budget to them so future videos are cut the way this reviewer
    likes — one more thing the ouroboros loop extracts from finished work.
    Returns None until enough reviewed samples exist.
    """
    from sqlmodel import select

    from ..db import Segment, get_session

    with get_session() as session:
        rows = session.exec(
            select(Segment.text_final).where(
                Segment.reviewed == True  # noqa: E712
            )
        ).all()
    lengths = sorted(len(t.strip()) for t in rows if t and t.strip())
    if len(lengths) < MIN_LEARN_SAMPLES:
        return None

    def pct(p: float) -> int:
        return lengths[min(len(lengths) - 1, int(p * len(lengths)))]

    hard = int(min(48, max(24, pct(0.9))))
    soft = int(min(hard - 2, max(14, statistics.median(lengths))))
    return soft, hard

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


def _split_words(words: list[Word], soft_chars: int, max_chars: int) -> list[list[Word]]:
    pieces: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        text = _text_of(cur)
        dur = cur[-1].end - cur[0].start
        global_i = i  # index into full words list for boundary lookahead

        at_boundary = _is_boundary(words, global_i)
        over_soft = len(text) >= soft_chars
        over_hard = len(text) >= max_chars or dur >= MAX_SEGMENT_SECONDS

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
            and len(_text_of(pieces[-1] + cur)) <= max_chars
        ):
            pieces[-1] = pieces[-1] + cur
        else:
            pieces.append(cur)
    return pieces


def split_segments(
    segments: list[SttSegment], budget: tuple[int, int] | None = None
) -> list[SttSegment]:
    soft_chars, max_chars = budget or learned_line_budget() or (
        DEFAULT_SOFT_CHARS,
        DEFAULT_MAX_CHARS,
    )
    out: list[SttSegment] = []
    for seg in segments:
        if not seg.words or len(seg.text) <= max_chars:
            out.append(seg)
            continue
        for piece in _split_words(seg.words, soft_chars, max_chars):
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
