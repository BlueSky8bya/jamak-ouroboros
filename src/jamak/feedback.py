"""Ouroboros write side: absorb human review into the learning store.

For every reviewed segment, diff the machine draft (text_llm, falling back
to text_whisper) against text_final. Word-level replacements become
Correction pairs; repeated fixes bump their count, which raises their
priority in the few-shot selection (glossary.fewshot_corrections).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlmodel import select

from .db import Correction, Job, Segment, get_session, utcnow


def _tokens(text: str) -> list[str]:
    return text.split()


def _clean(s: str) -> str:
    # strip edge punctuation so "에스드," → "에스드" pairs generalize
    return re.sub(r"^[^\w가-힣]+|[^\w가-힣]+$", "", s)


def extract_pairs(machine: str, final: str) -> list[tuple[str, str, str]]:
    """(wrong, right, context) pairs from one segment's diff."""
    m_tok, f_tok = _tokens(machine), _tokens(final)
    pairs: list[tuple[str, str, str]] = []
    sm = SequenceMatcher(None, m_tok, f_tok, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "replace":
            continue
        wrong = _clean(" ".join(m_tok[i1:i2]))
        right = _clean(" ".join(f_tok[j1:j2]))
        if not wrong or not right or wrong == right:
            continue
        # skip huge rewrites — those are style edits, not misrecognitions
        if len(wrong) > 30 or len(right) > 30:
            continue
        ctx_start = max(0, j1 - 3)
        context = " ".join(f_tok[ctx_start : min(len(f_tok), j2 + 3)])
        pairs.append((wrong, right, context))
    return pairs


def absorb_job(video_id: str) -> dict:
    """Absorb all reviewed segments of a job. Idempotent per run:
    only segments reviewed and with a non-empty final text contribute."""
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise ValueError(f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(
                Segment.job_id == job.id,
                Segment.reviewed == True,  # noqa: E712
            )
        ).all()

        new_pairs = 0
        bumped = 0
        for seg in segs:
            machine = seg.text_llm or seg.text_whisper
            final = seg.text_final
            if not final.strip() or final.strip() == machine.strip():
                continue
            for wrong, right, context in extract_pairs(machine, final):
                existing = session.exec(
                    select(Correction).where(
                        Correction.wrong == wrong, Correction.right == right
                    )
                ).first()
                if existing:
                    # bump once per job so re-absorbing the same review
                    # doesn't inflate counts
                    if existing.source_job_id != job.id:
                        existing.count += 1
                        existing.source_job_id = job.id
                        session.add(existing)
                        bumped += 1
                else:
                    session.add(
                        Correction(
                            wrong=wrong,
                            right=right,
                            context=context,
                            source_job_id=job.id,
                            count=1,
                        )
                    )
                    new_pairs += 1

        n_reviewed = len(segs)
        if n_reviewed:
            job.status, job.updated_at = "done", utcnow()
            session.add(job)
        session.commit()

    return {"reviewed_segments": n_reviewed, "new_pairs": new_pairs, "bumped": bumped}
