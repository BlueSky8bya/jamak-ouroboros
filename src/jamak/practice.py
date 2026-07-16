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

    if course == "basic":
        # [WH-CHANGE v0.9.73 | FIX | 2026-07-17 | CHG-20260717-110]
        # Reason: Whisper가 나레이션 L8 "잘 하셨습니다."의 첫 글자를 **앞 대사(L7)
        #   꼬리에 잘못 찍어** 한 단어가 3초 떨어진 두 셀로 갈렸다 —
        #   #13 "잘"(66.6~67.6, L7 구간 안) + #14 "하셨습니다"(70.6~71.3, L8 자리).
        #   연습1은 첫 튜토리얼이고 투어가 셀 텍스트를 나레이션과 대조하는 단계라,
        #   "잘"만 있는 셀은 "지금 → 실제 말" 안내를 무의미하게 만든다(사용자 지적).
        #   앞 조각을 지우고 본체에 붙여 한 셀로 되돌린다. 시각은 본체 것을 쓴다 —
        #   앞 조각의 start를 살리면 자막이 L7 발화 위에 뜬다.
        #   UI 드릴 재료 보정이지 학습 데이터가 아니다 (practice 전용, structure 선례).
        # Related: CHANGELOG CHG-20260717-110.
        for a, b in zip(segs, segs[1:]):
            ta = (a.text_llm or a.text_whisper or "").strip()
            tb = (b.text_llm or b.text_whisper or "").strip()
            if ta == "잘" and tb.startswith("하셨습니다"):
                b.text_llm = f"잘 {tb}"
                b.text_final = ""
                b.reviewed = False
                session.add(b)
                session.delete(a)
                session.flush()
                for i, x in enumerate(
                    sorted((s for s in segs if s is not a), key=lambda s: s.start)
                ):
                    if x.idx != i:
                        x.idx = i
                        session.add(x)
                changed += 1
                break

    if course == "structure":
        # [WH-CHANGE v0.9.13 | FIX | 2026-07-15 | CHG-20260715-037]
        # Reason: 나누기 드릴은 "너무 긴 자막" 하나가 있어야 성립하는데 STT가
        #   대본의 초장문(L2)을 여러 행으로 쪼개고 꼬리 겹침까지 남겼음 —
        #   해당 구간 행들을 병합하고 대본 원문으로 되돌린다 (UI 드릴 재료,
        #   학습 데이터 아님 — practice 전용).
        # Related: CHANGELOG CHG-20260715-037.
        LONG = (
            "제가 지금부터 숨도 안 쉬고 아주 길게 말할 텐데 이렇게 길게 말하면 "
            "자막 한 칸에 글이 꽉 차서 보는 사람이 미처 다 읽기도 전에 자막이 "
            "지나가 버리기 때문에 중간의 적당한 곳에서 둘로 나누어 주는 것이 좋습니다"
        )
        # 창은 대본 L2(초장문) 발화 구간만: 17.0~32.5s (timing.json 16.54~32.74).
        # 넓게 잡으면 앞 대사("차분히 다듬는...") 행까지 삼킨다 — 실제로 삼켜서
        # 좁힘. 텍스트 앵커('숨도')로 이중 확인.
        def _nm(t: str) -> str:
            return re.sub(r"[^\w가-힣]", "", t or "")

        span = [
            s
            for s in segs
            if "길지요" not in (s.text_llm or "")
            and (
                (s.end > 17.0 and s.start < 32.5)
                # STT가 문장 머리를 창보다 이르게 찍는 경우: 텍스트가 초장문의
                # 일부면 흡수 (14.1s '제가 지금부터…' 조각 실측)
                or (s.start >= 12.0 and s.start < 32.5 and _nm(s.text_llm or s.text_whisper) in _nm(LONG))
            )
        ]
        joined = " ".join((s.text_llm or s.text_whisper or "") for s in span)
        if span and "숨도" in joined and (len(span) > 1 or span[0].text_llm != LONG):
            first = span[0]
            first.end = max(x.end for x in span)
            first.text_llm = LONG
            first.text_final = ""
            first.reviewed = False
            session.add(first)
            for x in span[1:]:
                session.delete(x)
            session.flush()
            rest = sorted(
                (s for s in segs if s not in span[1:]), key=lambda s: s.start
            )
            for i, s in enumerate(rest):
                if s.idx != i:
                    s.idx = i
                    session.add(s)
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
    # [WH-CHANGE v0.8.7 | FIX | 2026-07-15 | CHG-20260715-027]
    # Reason: on Postgres the ORM emitted DELETE job before DELETE sttblob in
    # the same flush -> sttblob_job_id_fkey violation -> 연습 재입장이 500으로
    # 죽음 (로컬 SQLite는 FK 미강제라 E2E가 못 잡았음). 자식 행 삭제를 먼저
    # flush해 순서를 명시적으로 고정한다.
    # Related: CHANGELOG CHG-20260715-027.
    session.flush()
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
