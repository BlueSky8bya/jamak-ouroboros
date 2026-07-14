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

from .noise import cascade_indices, is_known_prompt_leak, is_prompt_echo
from .stt import SttSegment

# below this token-set similarity (0-100) the segment gets flagged
FLAG_THRESHOLD = 65


def strip_speaker_markers(text: str) -> str:
    """Remove YouTube '>>' / '>' speaker-change markers from caption text.

    Our subtitles never use them, so they must never enter the DB — even when a
    segment is seeded verbatim from a YouTube caption. Purely deterministic
    (no API): applied at caption-parse time so every downstream use is clean.
    """
    text = re.sub(r"(^|\s)>>?(\s|$)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_json3_captions(path: Path) -> list[tuple[float, float, str]]:
    """YouTube json3 -> [(start, end, text)] with times in seconds."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[float, float, str]] = []
    for event in data.get("events", []):
        if "segs" not in event:
            continue
        text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
        text = strip_speaker_markers(text)
        if not text:
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


LOW_CONF_PROB = 0.55  # whisper word-probability below this = flag as suspect


def low_conf_words(seg: SttSegment, threshold: float = LOW_CONF_PROB, cap: int = 6) -> str:
    """Comma-separated list of the words whisper was least sure about here.

    faster-whisper returns a per-word probability. Surfacing the low-probability
    words lets the reviewer's eye jump straight to what whisper likely misheard,
    instead of re-reading the whole line. Deterministic, no API.
    """
    out: list[str] = []
    for w in seg.words or []:
        token = w.word.strip()
        if not re.search(r"[가-힣A-Za-z0-9]", token):
            continue  # skip pure punctuation/space
        if w.probability < threshold and token not in out:
            out.append(token)
    return ", ".join(out[:cap])


def deroll_captions(
    captions: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    """Collapse YouTube rolling auto-captions into distinct, non-overlapping lines.

    Auto-captions slide: the same line reappears across several overlapping
    events. We keep the first occurrence of each distinct line and clamp each
    line's end to the next line's start so the timeline doesn't overlap. The
    result is a clean sequence of real subtitle lines with sane timings —
    usable to fill spans whisper missed entirely.
    """
    uniq: list[list] = []
    seen: set[str] = set()
    for s, e, t in sorted(captions, key=lambda c: c[0]):
        key = _normalize(t)
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append([s, e, t])
    for i in range(len(uniq) - 1):
        uniq[i][1] = max(uniq[i][0], min(uniq[i][1], uniq[i + 1][0]))
    return [(s, e, t) for s, e, t in uniq]


def youtube_gap_rows(
    existing: list[dict],
    captions: list[tuple[float, float, str]],
    pad: float = 0.3,
) -> list[dict]:
    """Rows from YouTube captions for time spans no whisper segment covers.

    Fixes the case where whisper drops the opening (speech over intro music /
    VAD trimming) so the first subtitle starts well after the speaker began.
    Each gap line becomes a flagged, YouTube-seeded row.

    [WH-CHANGE v0.6.7 | FIX | 2026-07-14 | CHG-20260714-018]
    Reason: YouTube auto-captions keep showing a sentence's TAIL during the
      pause after it. Those tail lines land in whisper-silent gaps and were
      dutifully imported as rows — ghost duplicates after nearly every pause
      ("...먹었습니다." → "먹었습니다."). Reviewers were deleting them by hand
      (the structural-edit noise the CER analysis surfaced). Now a gap
      candidate whose normalized text is already contained in the nearest
      preceding row's text is dropped. Trade-off: a genuinely re-spoken exact
      repeat right after a pause is skipped too — rare, and these rows are
      flagged guesses, not ground truth.
    Related: CHANGELOG CHG-20260714-018.
    """
    covered = [(r["start"], r["end"]) for r in existing]
    by_start = sorted(existing, key=lambda r: r["start"])
    derolled = deroll_captions(captions)
    rows: list[dict] = []
    for s, e, t in derolled:
        mid = (s + e) / 2 if e > s else s
        if any(cs - pad <= mid <= ce + pad for cs, ce in covered):
            continue
        prev = None
        for r in by_start:
            if r["start"] <= s + pad:
                prev = r
            else:
                break
        if prev is not None:
            prev_text = _normalize(
                prev.get("text_llm") or prev.get("text_whisper") or ""
            )
            cand = _normalize(t)
            if cand and cand in prev_text:
                continue  # echo of the sentence that just ended — ghost line
            # [WH-CHANGE v0.8.7 | FIX | 2026-07-15 | CHG-20260715-028]
            # Reason: 재렌더 연습 영상에서 에코가 다시 뚫림 — ① STT 오타
            #   ('다듭'≠'다듬')가 정확 부분문자열 매칭을 깨고, ② 꼬리 자막이
            #   이전 행 전체 + 부스러기('...있습니다.네')인 역방향 포함은 검사
            #   안 했음. 퍼지(partial_ratio)와 역방향을 추가하되, 이전 행이
            #   6자 미만이면 건너뜀 — 조각 행('잘') 때문에 진짜 놓친 발화
            #   ("잘 넘어오셨나요?")까지 버리는 오탐 방지.
            # Related: CHANGELOG CHG-20260715-028.
            if cand and len(prev_text) >= 6 and (
                prev_text in cand or fuzz.partial_ratio(cand, prev_text) >= 85
            ):
                continue
        rows.append(
            {
                "start": s,
                "end": e if e > s else s + 1.5,
                # whisper heard NOTHING here — leave its column empty so the
                # reference panel is honest ("음성인식" blank), not a fake
                # duplicate of the YouTube text. The working text is seeded from
                # YouTube (text_llm/text_final) so it still shows and exports.
                "text_whisper": "",
                "text_youtube": t,
                "text_llm": t,
                "text_final": t,
                "flagged": True,
            }
        )
    return rows


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

    # prompt-agnostic hallucination signature: a run of consecutive identical
    # subtitles. Catches the echo cascade even when we passed no initial_prompt.
    cascade = cascade_indices([s.text for s in stt_segments])

    out: list[dict] = []
    n_echo = 0
    for i, seg in enumerate(stt_segments):
        yt_text = youtube_text_for_span(captions, seg.start, seg.end)
        whisper_text = seg.text

        is_echo = (
            i in cascade
            or is_known_prompt_leak(whisper_text)
            or (prompt_text and is_prompt_echo(whisper_text, prompt_text))
        )
        if is_echo:
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
                "low_conf": low_conf_words(seg),
            }
        )

    # fill spans whisper missed entirely (the dropped opening + internal gaps)
    # from YouTube captions so the first subtitle starts where speech starts
    if captions:
        out.extend(youtube_gap_rows(out, captions))
        out.sort(key=lambda r: r["start"])

    return out, n_echo
