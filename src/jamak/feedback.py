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


#: 학습 단계 — 웹 UI가 이 순서로 호출하면 phase="all" 과 같은 결과.
ABSORB_PHASES = ("extract", "repair", "propagate")

# ── 3층(ADR-0011): 사람이 손으로 단 병기를 사전으로 흡수 ──────────────────
# 다자어: "해탈(解脫)" — 한글 2자 이상 + 괄호 안이 한자만.
_HANJA_MULTI = re.compile(r"(?<![가-힣])([가-힣]{2,10})\(([一-鿿]{1,10})\)")
# 단일자: "얼굴 안(顔) 자" — 뜻 단어와 짝이어야 동음이 구분된다 (fill 규칙 A와 같은 꼴).
_HANJA_GLYPH = re.compile(r"([가-힣]+) ([가-힣])\(([一-鿿])\) 자")

#: 사람이 2개 이상의 다른 Job에서 같은 병기를 달면 흑판 특수어로 승격(자동 병기 대상).
HANJA_PROMOTE_AT = 2


def _scan_hanja_annotations(text: str) -> set[tuple[str, str, str]]:
    """(gloss, reading, hanja) — 사람이 이 자막에 직접 달아 놓은 병기."""
    found: set[tuple[str, str, str]] = set()
    for m in _HANJA_GLYPH.finditer(text):
        found.add((m.group(1), m.group(2), m.group(3)))
    # 단일자 형태로 이미 잡은 자리는 다자어 규칙이 또 잡지 않게 지운 뒤 훑는다
    rest = _HANJA_GLYPH.sub(" ", text)
    for m in _HANJA_MULTI.finditer(rest):
        found.add(("", m.group(1), m.group(2)))
    return found


def learn_hanja_annotations(session, job) -> dict[str, int]:
    """Absorb hanja a human typed by hand into the HanjaTerm dictionary.

    [WH-CHANGE v0.9.56 | FEAT | 2026-07-17 | CHG-20260717-083]
    Reason: ADR-0011 3층. 검수자가 '해탈(解脫)'을 손으로 달아도 그 셀에서 끝나
      다음 영상에서 또 손으로 달아야 했다(사용자 사례: 정각/열반/해탈/보리 중
      열반만 자동 병기 — 나머지는 사전에 아예 없음). 사람이 단 병기를 사전에
      등록해 2층(漢 채우기)이 갈수록 더 잡게 한다.
    안전장치: 같은 읽기에 다른 한자가 등장하면(정각=正刻/正覺) **동음이의**로
      보고 그 읽기의 모든 항목을 tier=common으로 내려 자동 병기에서 뺀다 —
      한 번의 오등록이 전 영상을 오염시키는 것(광채 사고 계열)을 막는다.
      새 항목은 common으로 시작하고, 서로 다른 Job 2개에서 확인되면 special로
      승격한다(사람 손 2번 = 흑판 어휘라는 증거).
    Related: ADR-0011, CHANGELOG CHG-20260717-083.
    """
    from .db import HanjaTerm

    stats = {"hanja_new": 0, "hanja_promoted": 0, "hanja_ambiguous": 0}
    segs = session.exec(
        select(Segment).where(
            Segment.job_id == job.id,
            Segment.lang == "ko",
            Segment.reviewed == True,  # noqa: E712
        )
    ).all()

    seen: set[tuple[str, str, str]] = set()
    for seg in segs:
        seen |= _scan_hanja_annotations(seg.text_final or "")

    for gloss, reading, hanja in sorted(seen):
        rows = session.exec(
            select(HanjaTerm).where(
                HanjaTerm.reading == reading, HanjaTerm.gloss == gloss
            )
        ).all()
        exact = next((r for r in rows if r.hanja == hanja), None)
        others = [r for r in rows if r.hanja != hanja]

        if others:
            # 같은 읽기에 다른 한자 → 문맥으로만 갈리는 말. 자동 병기 금지.
            stats["hanja_ambiguous"] += 1
            for r in others:
                if r.tier != "common":
                    r.tier = "common"
                    session.add(r)

        if exact is None:
            session.add(
                HanjaTerm(
                    reading=reading,
                    gloss=gloss,
                    hanja=hanja,
                    count=1,
                    tier="common",  # 승격은 다른 Job에서 한 번 더 확인될 때
                    source_job_id=job.id,
                )
            )
            stats["hanja_new"] += 1
            continue

        # 같은 항목: 다른 Job에서 또 확인된 경우에만 카운트 (재학습 부풀림 방지)
        if exact.source_job_id != job.id:
            exact.count += 1
            exact.source_job_id = job.id
            if (
                not others
                and exact.tier != "special"
                and exact.count >= HANJA_PROMOTE_AT
            ):
                exact.tier = "special"
                stats["hanja_promoted"] += 1
            session.add(exact)
    return stats

_ABSORB_KEYS = (
    "reviewed_segments",
    "new_pairs",
    "bumped",
    "repaired",
    "applied",
    "propagated_segments",
    "propagated_replacements",
    "propagation_pairs",
    # 3층(ADR-0011): 사람이 손으로 단 병기 흡수 결과
    "hanja_new",
    "hanja_promoted",
    "hanja_ambiguous",
)


def _collect_pairs(session, job, *, write: bool) -> tuple[dict, int, int, int, int]:
    """Diff reviewed segments into (wrong, right) -> first idx.

    write=False makes this read-only (no Correction rows, no counts) so the
    propagate phase can recompute the same pair set without re-learning it.
    """
    total_segments = len(
        session.exec(
            select(Segment.id).where(Segment.job_id == job.id, Segment.lang == "ko")
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

    scoped_pairs: dict[tuple[str, str], int] = {}
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
            if not write:
                continue
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
    return scoped_pairs, new_pairs, bumped, len(segs), total_segments


# [WH-CHANGE v0.9.53 | FEAT | 2026-07-16 | CHG-20260716-076]
# Reason: 학습이 단일 요청이라 웹은 "학습 중..."밖에 못 띄웠고, 사용자가 진행
#   중인지 멈춘 건지 구분 못 했다. 세 단계를 따로 호출할 수 있게 열어 UI가
#   단계별 진행률을 보여주게 한다. propagate는 extract를 read-only로 다시
#   계산해 pairs를 얻으므로 클라이언트가 단계 사이 상태를 들고 다닐 필요가 없다
#   (그래야 클라이언트가 학습 내용을 조작할 수 없다).
# Related: CHANGELOG v0.9.53
def absorb_job(video_id: str, phase: str = "all") -> dict:
    """Absorb all reviewed segments of a job. Idempotent per run:
    only segments reviewed and with a non-empty final text contribute.

    phase="all" (기본, CLI 경로)은 예전과 동일하게 세 단계를 한 번에 돈다.
    "extract" | "repair" | "propagate" 를 순서대로 호출해도 결과는 같다.
    """
    if phase != "all" and phase not in ABSORB_PHASES:
        raise ValueError(f"unknown absorb phase: {phase}")

    result: dict[str, int] = dict.fromkeys(_ABSORB_KEYS, 0)
    do_extract = phase in ("all", "extract")
    do_repair = phase in ("all", "repair")
    do_propagate = phase in ("all", "propagate")

    scoped_pairs: dict[tuple[str, str], int] = {}
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise ValueError(f"no job for {video_id}")
        # 연습용 영상 (tutorial sandbox, ADR-0009 후속): its edits are drills,
        # not review — absorbing them would pollute corrections/glossary.
        if job.practice:
            return result

        # propagate needs the same pair set; recompute it read-only.
        if do_extract or do_propagate:
            scoped_pairs, new_pairs, bumped, n_reviewed, total_segments = _collect_pairs(
                session, job, write=do_extract
            )
            if do_extract:
                result["reviewed_segments"] = n_reviewed
                result["new_pairs"] = new_pairs
                result["bumped"] = bumped
                # 3층(ADR-0011): 사람이 손으로 단 병기를 한자 사전으로 흡수
                result.update(learn_hanja_annotations(session, job))
                if n_reviewed:
                    job.status = "done" if n_reviewed >= total_segments else "reviewing"
                    job.updated_at = utcnow()
                    session.add(job)
                session.commit()

    # Clean up any older over-propagation from contextual reference pairs
    # before applying newly confirmed safe pairs.
    if do_repair:
        result["repaired"] = repair_unsafe_reference_rewrites(video_id)["segments"]

    # Apply what the reviewer just confirmed to later unreviewed subtitles in
    # this same video. This is deliberately zero-API: it removes repeated
    # typing fatigue without spending Claude calls during review.
    if do_propagate:
        propagation = apply_learned_to_unreviewed(
            video_id,
            [(wrong, right, idx) for (wrong, right), idx in scoped_pairs.items()],
        )
        result["applied"] = propagation["segments"]
        result["propagated_segments"] = propagation["segments"]
        result["propagated_replacements"] = propagation["replacements"]
        result["propagation_pairs"] = propagation["pairs"]

    return result


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
