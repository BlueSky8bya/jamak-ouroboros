"""Per-user tutorial practice sessions (PLAN v4 §4.3).

A *baseline* practice job (one per course, `practice_course` set) is frozen
after rehearsal; every reviewer who starts a course gets a *clone* — a deep
copy of the baseline's Korean segments under a synthetic video_id
"<base>~<key>". Clones make parallel practice collision-free by construction
and "start over" is just re-cloning. The synthetic video_id lets every
existing video_id-keyed endpoint operate on clones unchanged; the frontend
strips the "~..." suffix when embedding the YouTube player.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from sqlmodel import Session, select

from .db import Job, Segment, SttBlob, Translation, get_session, utcnow

SESSION_KEY_RE = re.compile(r"^[a-z0-9-]{4,40}$")
CLONE_TTL_DAYS = 7

# Deterministic screen-draft defects planted at course-bind time (P5 found the
# scripted baits were all defeated by whisper hotwords — the STT is too good).
# Injection edits text_llm on the BASELINE once; every clone inherits the same
# start state, so drills are identical for all reviewers. Replacements are
# idempotent: once applied, the source word is gone and the rule no-ops.
COURSE_TEXT_DEFECTS: dict[str, list[tuple[str, str, int]]] = {
    # course id -> [(correct, planted_typo, max_rows_to_touch)]
    "basic": [
        ("깻잎", "깨입", 1),
        ("밤나무", "밥나무", 1),
        ("축지법", "축제법", 1),
        ("공중부양", "공중부용", 1),
    ],
    "fast": [
        ("뭉치", "몽치", 2),
    ],
}


def inject_course_defects(session: Session, job: Job, course: str) -> int:
    """Plant deterministic defects on the baseline for this course. Returns
    the number of rows changed. Runs at bind time only (caller skips when the
    job is already bound to the same course)."""
    changed = 0
    segs = session.exec(
        select(Segment)
        .where(Segment.job_id == job.id, Segment.lang == "ko")
        .order_by(Segment.idx)
    ).all()

    for correct, typo, max_rows in COURSE_TEXT_DEFECTS.get(course, []):
        touched = 0
        for s in segs:
            if touched >= max_rows:
                break
            src = s.text_llm or s.text_whisper
            if correct in src:
                s.text_llm = src.replace(correct, typo)
                # reviewed rows would hide the draft; baselines are unreviewed,
                # but clear defensively so the defect is always visible.
                s.reviewed = False
                s.text_final = ""
                session.add(s)
                touched += 1
                changed += 1

    if course == "timing":
        # one trailing-silence defect: extend the first cue that has >=1.5s of
        # following silence so it visibly overhangs into the pause (✂ / ✨
        # material that survives; natural fast-cps rows already exist).
        for a, b in zip(segs, segs[1:]):
            gap = b.start - a.end
            if gap >= 1.5:
                a.end = round(b.start - 0.15, 3)
                session.add(a)
                changed += 1
                break

    return changed


def _clone_video_id(base_video_id: str, session_key: str) -> str:
    # hash, don't truncate: two keys sharing a prefix must not collide on the
    # UNIQUE video_id (found in E2E with "browser-user-a"/"...-b")
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:10]
    return f"{base_video_id}~{digest}"


def get_or_create_practice_session(
    base_video_id: str, session_key: str, reset: bool = False
) -> dict:
    """Return (creating if needed) this browser's clone of a baseline practice
    job. reset=True discards the existing clone first — 'start over'."""
    if "~" in base_video_id:
        raise ValueError("already a practice-session video")
    if not SESSION_KEY_RE.match(session_key):
        raise ValueError("bad session key")

    with get_session() as session:
        base = session.exec(
            select(Job).where(Job.video_id == base_video_id)
        ).first()
        if base is None:
            raise LookupError(f"no job for {base_video_id}")
        if not base.practice or base.clone_of is not None:
            raise PermissionError("연습용 영상이 아닙니다")  # BR-DATA-001 guard
        # ko-single-track contract: no fork tracks on tutorial videos
        non_ko = session.exec(
            select(Segment.id)
            .where(Segment.job_id == base.id, Segment.lang != "ko")
            .limit(1)
        ).first()
        if non_ko is not None:
            raise PermissionError("연습용 영상에 번역 트랙이 있어 복제할 수 없습니다")

        existing = session.exec(
            select(Job).where(
                Job.clone_of == base.id, Job.session_key == session_key
            )
        ).first()
        if existing is not None and not reset:
            return {"video_id": existing.video_id, "created": False}
        if existing is not None:
            _delete_clone(session, existing)

        clone = Job(
            video_id=_clone_video_id(base.video_id, session_key),
            url=base.url,
            title=base.title,
            channel=base.channel,
            duration_seconds=base.duration_seconds,
            upload_date=base.upload_date,
            status=base.status,
            practice=True,
            clone_of=base.id,
            session_key=session_key,
        )
        session.add(clone)
        session.commit()
        session.refresh(clone)

        for s in session.exec(
            select(Segment)
            .where(Segment.job_id == base.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all():
            data = s.model_dump(exclude={"id"})
            data["job_id"] = clone.id
            session.add(Segment(**data))
        blob = session.exec(
            select(SttBlob).where(SttBlob.job_id == base.id)
        ).first()
        if blob is not None:
            session.add(SttBlob(job_id=clone.id, data=blob.data))
        session.commit()
        return {"video_id": clone.video_id, "created": True}


def _delete_clone(session: Session, clone: Job) -> None:
    """Delete a practice clone and its rows. Double guard (clone_of set AND
    practice) — this must never be reachable for real review data."""
    assert clone.clone_of is not None and clone.practice, "refusing: not a clone"
    seg_ids = session.exec(
        select(Segment.id).where(Segment.job_id == clone.id)
    ).all()
    if seg_ids:
        for tr in session.exec(
            select(Translation).where(Translation.segment_id.in_(seg_ids))
        ).all():
            session.delete(tr)
        for seg in session.exec(
            select(Segment).where(Segment.job_id == clone.id)
        ).all():
            session.delete(seg)
    for blob in session.exec(
        select(SttBlob).where(SttBlob.job_id == clone.id)
    ).all():
        session.delete(blob)
    session.delete(clone)
    session.commit()


def cleanup_stale_clones(ttl_days: int = CLONE_TTL_DAYS) -> int:
    """Drop practice clones idle longer than the TTL (worker housekeeping)."""
    cutoff = utcnow() - timedelta(days=ttl_days)
    removed = 0
    with get_session() as session:
        stale = session.exec(
            select(Job).where(
                Job.clone_of != None,  # noqa: E711
                Job.practice == True,  # noqa: E712
                Job.updated_at < cutoff,
            )
        ).all()
        for clone in stale:
            _delete_clone(session, clone)
            removed += 1
    return removed
