"""Stage 5 — Assemble: segments -> .srt / .vtt with Korean subtitle rules."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import srt

from ..config import MAX_CHARS_PER_LINE, MAX_LINES


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


def to_srt(segments: list[dict], text_key: str, out_path: Path) -> Path:
    """segments: [{start, end, <text_key>}] -> .srt file.

    text_key picks the pipeline stage: text_whisper (M1 draft),
    text_llm (M2 corrected), text_final (reviewed).
    """
    subs = []
    n = 1
    for seg in segments:
        text = (seg.get(text_key) or "").strip()
        if not text:
            continue
        subs.append(
            srt.Subtitle(
                index=n,
                start=dt.timedelta(seconds=seg["start"]),
                end=dt.timedelta(seconds=seg["end"]),
                content=wrap_korean(text),
            )
        )
        n += 1
    out_path.write_text(srt.compose(subs), encoding="utf-8")
    return out_path
