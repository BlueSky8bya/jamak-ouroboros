"""Stage 5 — Assemble: segments -> .srt / .vtt with Korean subtitle rules."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import srt

from ..config import MAX_CHARS_PER_LINE, MAX_LINES

# A blank shorter than this between two cues reads as a flicker/blink, not a
# pause. Below it, we run the cues continuously (no gap); at or above it, we keep
# the gap as a real silence. (~2-3 frames; between our word-tightening noise and
# the 0.7s pause the pipeline splits on.)
GAP_JOIN_BELOW = 0.2


def wrap_korean(text: str, max_chars: int = MAX_CHARS_PER_LINE, max_lines: int = MAX_LINES) -> str:
    """Break text into subtitle lines at word boundaries."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for w in words:
        candidate = f"{current} {w}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    # too many lines -> rebalance into max_lines roughly equal chunks
    if len(lines) > max_lines:
        joined = " ".join(lines)
        target = len(joined) // max_lines + 1
        lines, current = [], ""
        for w in joined.split():
            candidate = f"{current} {w}".strip()
            if len(candidate) <= target or not current:
                current = candidate
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
    return "\n".join(lines[: max_lines + 1])


# CJK scripts read ~18 chars/line; Latin/Cyrillic subtitle norm is ~42
# (Netflix TTSS). Wrapping a translation by the Korean 18-char rule cramps it
# and can even clip long lines — so the budget is per target language.
CJK_LANGS = {"ko", "ja", "zh-Hans", "zh-Hant"}


def line_budget(lang: str) -> int:
    return MAX_CHARS_PER_LINE if lang in CJK_LANGS else 42


def to_srt(segments: list[dict], text_key: str, out_path: Path, lang: str = "ko") -> Path:
    """segments: [{start, end, <text_key>}] -> .srt file.

    text_key picks the pipeline stage: text_whisper (M1 draft),
    text_llm (M2 corrected), text_final (reviewed). lang picks the per-script
    line-length budget (CJK ~18 vs Latin/Cyrillic ~42).
    """
    max_chars = line_budget(lang)
    rows = [
        [float(seg["start"]), float(seg["end"]), text]
        for seg in segments
        if (text := (seg.get(text_key) or "").strip())
    ]
    rows.sort(key=lambda r: r[0])
    # flicker guard: close any sub-threshold gap (or overlap) so consecutive cues
    # run continuously; keep gaps >= GAP_JOIN_BELOW as real pauses.
    for i in range(len(rows) - 1):
        if rows[i + 1][0] - rows[i][1] < GAP_JOIN_BELOW:
            rows[i][1] = rows[i + 1][0]
    subs = [
        srt.Subtitle(
            index=i + 1,
            start=dt.timedelta(seconds=s),
            end=dt.timedelta(seconds=e),
            content=wrap_korean(t, max_chars=max_chars),
        )
        for i, (s, e, t) in enumerate(rows)
    ]
    out_path.write_text(srt.compose(subs), encoding="utf-8")
    return out_path
