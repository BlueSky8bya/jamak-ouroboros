"""Auto-timing pass (ADR-0009): make reviewed subtitles comfortable to read
without touching what they say.

Three deterministic fixes, all driven by the cached per-word STT timestamps
(no GPU, no API — safe to run on the cloud host):

1. snap    — clamp each cue to the words actually spoken inside it, so no
             subtitle lingers over silence at either end (same rule as the
             /tighten endpoint).
2. split   — a cue that overflows the char budget (2 lines) or runs too long
             is cut at its widest internal pause; the text is divided at the
             nearest space to the same time ratio.
3. extend  — splitting does NOT lower chars-per-second (text and time divide
             together), so a too-fast cue is instead given more screen time:
             its end is pushed into the following silence, capped before the
             next cue's speech and at a small max linger.

Pure planning functions — the endpoint applies the plan to DB rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import MAX_CHARS_PER_LINE, MAX_LINES, MAX_SEGMENT_SECONDS

MAX_CHARS = MAX_CHARS_PER_LINE * MAX_LINES  # hard text budget per subtitle
MAX_CPS = 17.0  # comfortable reading ceiling (matches the editor's ⏩ badge)
MIN_DUR = 0.30  # never collapse a cue below this (same as /tighten)
CUE_GAP = 0.08  # breathing room kept before the next cue when extending
MAX_LINGER = 2.0  # a subtitle may outlive its speech by at most this much
_MAX_SPLIT_DEPTH = 4  # recursion guard: 1 cue -> at most 16 pieces


@dataclass
class CuePlan:
    """One output piece of an input cue. text is None when the piece keeps the
    cue's original text (i.e. the cue was not split — only retimed)."""

    start: float
    end: float
    text: str | None


def _no_space_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _snap_to_space(text: str, pos: int) -> int:
    """Nearest word boundary (space) to a char position, so a time-ratio cut
    never slices through the middle of a word."""
    spaces = [m.start() for m in re.finditer(r"\s", text)]
    if not spaces:
        return pos
    return min(spaces, key=lambda s: abs(s - pos)) + 1


def _split_rec(
    text: str, words: list[tuple[float, float]], depth: int = 0
) -> list[tuple[str, list[tuple[float, float]]]]:
    """Recursively cut (text, words) at the widest internal pause until every
    piece fits the char/duration budget. Falls back to no split when there is
    no usable pause or the text can't be divided."""
    dur = words[-1][1] - words[0][0]
    if (
        depth >= _MAX_SPLIT_DEPTH
        or len(words) < 4
        or (len(text.strip()) <= MAX_CHARS and dur <= MAX_SEGMENT_SECONDS)
    ):
        return [(text, words)]

    # widest gap, searched away from the edges (a cut right next to an edge
    # would just shave off a fragment and recurse forever)
    n = len(words)
    margin = max(1, n // 5)
    best_i, best_gap = None, -1.0
    for i in range(margin, n - margin + 1):
        gap = words[i][0] - words[i - 1][1]
        if gap > best_gap:
            best_gap, best_i = gap, i
    if best_i is None:
        return [(text, words)]

    cut_t = words[best_i - 1][1]
    span = max(0.01, words[-1][1] - words[0][0])
    ratio = (cut_t - words[0][0]) / span
    pos = _snap_to_space(text, round(len(text) * ratio))
    left, right = text[:pos].strip(), text[pos:].strip()
    if not left or not right:
        return [(text, words)]
    return _split_rec(left, words[:best_i], depth + 1) + _split_rec(
        right, words[best_i:], depth + 1
    )


def plan_track(
    cues: list[dict], words: list[tuple[float, float]]
) -> list[list[CuePlan]]:
    """Plan snap+split+extend for a whole track.

    cues: [{"start", "end", "text"}] in time order (text = working text).
    words: [(start, end)] of every spoken word, sorted.
    Returns one list of CuePlan per input cue (len 1 = retimed only, len > 1 =
    split). A cue with no recognized speech inside keeps its original times.
    """
    # 1+2: snap and split each cue on the words it actually contains
    pieces_per_cue: list[list[CuePlan]] = []
    for cue in cues:
        inside = [
            (ws, we)
            for (ws, we) in words
            if cue["start"] <= (ws + we) / 2 < cue["end"]
        ]
        if not inside:
            # e.g. a YouTube gap-fill row (whisper heard nothing here) — leave
            # its hand-set times alone
            pieces_per_cue.append([CuePlan(cue["start"], cue["end"], None)])
            continue
        parts = _split_rec(cue["text"], inside)
        out: list[CuePlan] = []
        for text, ws_ in parts:
            start = ws_[0][0]
            end = max(ws_[-1][1], start + MIN_DUR)
            out.append(CuePlan(start, end, text if len(parts) > 1 else None))
        pieces_per_cue.append(out)

    # 3: extend for readability — flatten, then push each too-fast piece's end
    # into the silence after it (never into the next piece's speech)
    flat: list[CuePlan] = [p for ps in pieces_per_cue for p in ps]
    texts: list[str] = [
        p.text if p.text is not None else cue["text"]
        for cue, ps in zip(cues, pieces_per_cue)
        for p in ps
    ]
    for i, p in enumerate(flat):
        chars = _no_space_len(texts[i])
        if not chars:
            continue
        needed = chars / MAX_CPS
        cap = (flat[i + 1].start - CUE_GAP) if i + 1 < len(flat) else p.end + MAX_LINGER
        cap = min(cap, p.end + MAX_LINGER)
        new_end = min(max(p.end, p.start + needed), cap)
        if new_end > p.end:
            p.end = new_end

    for p in flat:
        p.start = round(p.start, 3)
        p.end = round(max(p.end, p.start + MIN_DUR), 3)
    return pieces_per_cue
