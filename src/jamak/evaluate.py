"""Accuracy measurement: is the ouroboros actually working?

CER of the machine stages against the human-reviewed final text,
per job in chronological order. The number that must go down over
time is cer_llm (post-correction error rate).
"""

from __future__ import annotations

import re

import jiwer
from sqlmodel import select

from .db import Job, Segment, get_session

# normalization must stay stable across evaluations — changing it is an
# ADR-level decision (RISK_PROFILE: ML_EVALUATION)
_norm = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
    ]
)


def _strip_punct(text: str) -> str:
    return re.sub(r"[^\w가-힣\s]", "", text)


def _cer(reference: str, hypothesis: str) -> float:
    ref = _norm(_strip_punct(reference))
    hyp = _norm(_strip_punct(hypothesis))
    if not ref:
        return 0.0
    return jiwer.cer(ref, hyp)


def evaluate_all() -> list[dict]:
    """Per-job CER for every job that has reviewed segments."""
    out: list[dict] = []
    with get_session() as session:
        jobs = session.exec(select(Job).order_by(Job.created_at)).all()
        for job in jobs:
            segs = session.exec(
                select(Segment).where(
                    Segment.job_id == job.id,
                    # ko only: CER measures Korean STT accuracy. Forked translation
                    # segments have foreign text_final but empty whisper/llm, which
                    # would inflate the metric (ADR-0006).
                    Segment.lang == "ko",
                    Segment.reviewed == True,  # noqa: E712
                )
            ).all()
            segs = [s for s in segs if s.text_final.strip()]
            if not segs:
                continue
            ref = " ".join(s.text_final for s in segs)
            hyp_whisper = " ".join(s.text_whisper for s in segs)
            hyp_llm = " ".join(s.text_llm or s.text_whisper for s in segs)
            out.append(
                {
                    "video_id": job.video_id,
                    "title": job.title[:40],
                    "date": job.created_at.date().isoformat(),
                    "reviewed_segments": len(segs),
                    "cer_whisper": round(_cer(ref, hyp_whisper), 4),
                    "cer_llm": round(_cer(ref, hyp_llm), 4),
                }
            )
    return out
