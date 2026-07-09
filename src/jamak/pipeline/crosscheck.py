"""Stage 3 — Cross-check: whisper vs YouTube auto-captions.

Two independent engines heard the same audio. Where they agree, confidence
is high. Where they disagree, a human (or Claude) should look. The flag is
what drives review priority in the web UI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from rapidfuzz import fuzz

from .noise import is_prompt_echo
from .stt import SttSegment

# below this token-set similarity (0-100) the segment gets flagged
FLAG_THRESHOLD = 65


def parse_json3_captions(path: Path) -> list[tuple[float, float, str]]:
    """YouTube json3 -> [(start, end, text)] with times in seconds."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[float, float, str]] = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
        text = re.sub(r"\s+", " ", text)
        if not text or text == "\n":
            continue
        start = event.get("tStartMs", 0) / 1000.0
        dur = event.get("dDurationMs", 0) / 1000.0
        out.append((start, start + dur, text))
    return out


def youtube_text_for_span(
    captions: list[tuple[float, float, str]], start: float, end: float
) -> str:
    """Collect auto-caption text overlapping [start, end]."""
    parts = [t for (s, e, t) in captions if s < end and e > start]
    return " ".join(parts).strip()


def _normalize(text: str) -> str:
    # strip punctuation/whitespace so the comparison is about words, not style
    return re.sub(r"[^\w가-힣]", "", text)


def crosscheck(
    stt_segments: list[SttSegment],
    captions_path: Path | None,
    prompt_text: str = "",
) -> tuple[list[dict], int]:
    """Attach YouTube text + disagreement flag to each whisper segment.

    Returns (rows, n_prompt_echo). Rows are dicts ready to become Segment
    rows: {start, end, text_whisper, text_youtube, flagged}.

    Prompt-echo handling: when whisper regurgitated its initial_prompt over
    a silent/music stretch, the whisper text is garbage. If YouTube heard
    real speech there, we substitute it (so the reviewer/LLM works from the
    real words, not the leaked prompt) and force-flag. With no YouTube text,
    the echo segment is dropped entirely.
    """
    captions = parse_json3_captions(captions_path) if captions_path else []

    out: list[dict] = []
    n_echo = 0
    for seg in stt_segments:
        yt_text = youtube_text_for_span(captions, seg.start, seg.end)
        whisper_text = seg.text

        if prompt_text and is_prompt_echo(whisper_text, prompt_text):
            n_echo += 1
            if not yt_text:
                continue  # pure prompt leak over silence — drop
            # whisper output here is garbage (leaked prompt); seed the working
            # text from YouTube so there is real content even without the LLM,
            # and force-flag so the human still verifies it
            out.append(
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text_whisper": yt_text,
                    "text_youtube": yt_text,
                    "flagged": True,
                }
            )
            continue

        if yt_text:
            score = fuzz.token_set_ratio(_normalize(whisper_text), _normalize(yt_text))
            flagged = score < FLAG_THRESHOLD
        else:
            # no second opinion: flag only if whisper itself was unsure
            flagged = seg.avg_logprob < -0.8
        out.append(
            {
                "start": seg.start,
                "end": seg.end,
                "text_whisper": whisper_text,
                "text_youtube": yt_text,
                "flagged": flagged,
            }
        )
    return out, n_echo
