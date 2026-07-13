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

from .config import PREPASS_MIN_COUNT
from .db import Correction, Job, Segment, get_session, utcnow
from .learned_pairs import clean_pair_text, is_safe_correction_pair

ScopedPair = tuple[str, str, int]


def _tokens(text: str) -> list[str]:
    return text.split()


def _clean(s: str) -> str:
    # strip edge punctuation so "에스드," → "에스드" pairs generalize
    return clean_pair_text(s)


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
        # Pronouns and demonstrative references are context-bound. Learning
        # them as global replacements rewrites what was actually spoken.
        if not is_safe_correction_pair(wrong, right):
            continue
        ctx_start = max(0, j1 - 3)
        context = " ".join(f_tok[ctx_start : min(len(f_tok), j2 + 3)])
        pairs.append((wrong, right, context))
    return pairs


def _replace_pair(text: str, wrong: str, right: str) -> tuple[str, int]:
    pattern = r"(?<![\w가-힣])" + re.escape(wrong) + r"(?![\w가-힣])"
    return re.subn(pattern, right, text)


def _restore_unsafe_pair(
    text: str,
    source: str,
    wrong: str,
    right: str,
) -> tuple[str, int]:
    """Undo a contextual-reference rewrite when it moves text toward source."""
    best = text
    best_score = SequenceMatcher(None, source, text, autojunk=False).ratio()
    replacements = 0
    candidates = (
        (right, wrong, wrong),
        (wrong, right, right),
    )
    for from_text, to_text, source_anchor in candidates:
        if source_anchor not in source:
            continue
        candidate, n = _replace_pair(text, from_text, to_text)
        if not n:
            continue
        score = SequenceMatcher(None, source, candidate, autojunk=False).ratio()
        if score > best_score:
            best = candidate
            best_score = score
            replacements = n
    return best, replacements


def _apply_pairs(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    replacements = 0
    # Longer phrases first so a phrase-level fix wins over a shorter token.
    for wrong, right in sorted(pairs, key=lambda p: len(p[0]), reverse=True):
        if not is_safe_correction_pair(wrong, right):
            continue
        text, n = _replace_pair(text, wrong, right)
        replacements += n
    return text, replacements


def absorb_job(video_id: str) -> dict:
    """Absorb all reviewed segments of a job. Idempotent per run:
    only segments reviewed and with a non-empty final text contribute."""
    scoped_pairs: dict[tuple[str, str], int] = {}
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise ValueError(f"no job for {video_id}")
        # 연습용 영상 (tutorial sandbox, ADR-0009 후속): its edits are drills,
        # not review — absorbing them would pollute corrections/glossary.
        if job.practice:
            return {
                "reviewed_segments": 0,
                "new_pairs": 0,
                "bumped": 0,
                "applied": 0,
                "propagated_segments": 0,
                "propagated_replacements": 0,
                "propagation_pairs": 0,
            }
        total_segments = len(
            session.exec(
                select(Segment.id).where(
                    Segment.job_id == job.id, Segment.lang == "ko"
                )
            ).all()
        )
        segs = session.exec(
            select(Segment)
            .where(
                Segment.job_id == job.id,
                Segment.lang == "ko",
                Segment.reviewed == True,  # noqa: E712
            )
            .order_by(Segment.idx)
        ).all()

        new_pairs = 0
        bumped = 0
        for seg in segs:
            machine = seg.text_llm or seg.text_whisper
            final = seg.text_final
            if not final.strip() or final.strip() == machine.strip():
                continue
            for wrong, right, context in extract_pairs(machine, final):
                key = (wrong, right)
                if key not in scoped_pairs or seg.idx < scoped_pairs[key]:
                    scoped_pairs[key] = seg.idx
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
            job.status = "done" if n_reviewed >= total_segments else "reviewing"
            job.updated_at = utcnow()
            session.add(job)
        session.commit()

    # Clean up any older over-propagation from contextual reference pairs
    # before applying newly confirmed safe pairs.
    repair = repair_unsafe_reference_rewrites(video_id)

    # Apply what the reviewer just confirmed to later unreviewed subtitles in
    # this same video. This is deliberately zero-API: it removes repeated
    # typing fatigue without spending Claude calls during review.
    propagation = apply_learned_to_unreviewed(
        video_id,
        [(wrong, right, idx) for (wrong, right), idx in scoped_pairs.items()],
    )

    return {
        "reviewed_segments": n_reviewed,
        "new_pairs": new_pairs,
        "bumped": bumped,
        "repaired": repair["segments"],
        "applied": propagation["segments"],
        "propagated_segments": propagation["segments"],
        "propagated_replacements": propagation["replacements"],
        "propagation_pairs": propagation["pairs"],
    }


def repair_unsafe_reference_rewrites(video_id: str) -> dict[str, int]:
    """Repair prior over-propagation of contextual reference pairs.

    Only unreviewed machine suggestions are touched. Human-edited final text is
    left alone, even if reviewed is still false.
    """
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise ValueError(f"no job for {video_id}")

        unsafe_pairs = [
            (c.wrong, c.right)
            for c in session.exec(select(Correction)).all()
            if not is_safe_correction_pair(c.wrong, c.right)
        ]
        if not unsafe_pairs:
            return {"segments": 0, "replacements": 0, "pairs": 0}

        segs = session.exec(
            select(Segment)
            .where(
                Segment.job_id == job.id,
                Segment.lang == "ko",
                Segment.reviewed == False,  # noqa: E712
            )
            .order_by(Segment.idx)
        ).all()

        n_segments = 0
        n_replacements = 0
        for seg in segs:
            if seg.text_final or not seg.text_llm:
                continue
            fixed = seg.text_llm
            replacements = 0
            for wrong, right in unsafe_pairs:
                fixed, n = _restore_unsafe_pair(
                    fixed,
                    seg.text_whisper,
                    wrong,
                    right,
                )
                replacements += n
            if fixed != seg.text_llm:
                seg.text_llm = fixed
                session.add(seg)
                n_segments += 1
                n_replacements += replacements

        if n_segments:
            job.updated_at = utcnow()
            session.add(job)
        session.commit()

    return {
        "segments": n_segments,
        "replacements": n_replacements,
        "pairs": len(unsafe_pairs),
    }


def apply_learned_to_unreviewed(
    video_id: str, scoped_pairs: list[ScopedPair] | None = None
) -> dict[str, int]:
    """Deterministic (zero-API) propagation of learned fixes.

    Pairs used:
      - pairs confirmed in reviewed segments of this video, applied only to
        later unreviewed segments
      - globally confirmed pairs (count >= PREPASS_MIN_COUNT), applied to any
        unreviewed segment

    Only unreviewed segments are touched; reviewed text is never rewritten.
    Returns propagation stats.
    """
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise ValueError(f"no job for {video_id}")

        # None means globally safe: no within-video lower bound.
        pair_scopes: dict[tuple[str, str], int | None] = {}
        rows = session.exec(
            select(Correction).where(Correction.count >= PREPASS_MIN_COUNT)
        ).all()
        for c in rows:
            if not is_safe_correction_pair(c.wrong, c.right):
                continue
            pair_scopes[(c.wrong, c.right)] = None

        for wrong, right, after_idx in scoped_pairs or []:
            if not is_safe_correction_pair(wrong, right):
                continue
            key = (wrong, right)
            if key in pair_scopes and pair_scopes[key] is None:
                continue
            if key not in pair_scopes or after_idx < pair_scopes[key]:
                pair_scopes[key] = after_idx

        if not pair_scopes:
            return {"segments": 0, "replacements": 0, "pairs": 0}

        segs = session.exec(
            select(Segment)
            .where(
                Segment.job_id == job.id,
                Segment.lang == "ko",
                Segment.reviewed == False,  # noqa: E712
            )
            .order_by(Segment.idx)
        ).all()

        n_segments = 0
        n_replacements = 0
        for seg in segs:
            pairs = [
                (wrong, right)
                for (wrong, right), after_idx in pair_scopes.items()
                if after_idx is None or seg.idx > after_idx
            ]
            if not pairs:
                continue
            base = seg.text_final or seg.text_llm or seg.text_whisper
            fixed, replacements = _apply_pairs(base, pairs)
            if replacements:
                # write into the tier the reviewer sees, preserving whisper
                if seg.text_final:
                    seg.text_final = fixed
                else:
                    seg.text_llm = fixed
                session.add(seg)
                n_segments += 1
                n_replacements += replacements
        if n_segments:
            job.updated_at = utcnow()
            session.add(job)
        session.commit()

    return {
        "segments": n_segments,
        "replacements": n_replacements,
        "pairs": len(pair_scopes),
    }
