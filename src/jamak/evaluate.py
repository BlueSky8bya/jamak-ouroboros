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


# [WH-CHANGE v0.6.2 | FIX | 2026-07-14 | CHG-20260714-013]
# Reason: 지표가 두 가지에 오염되고 있었음 — (a) .srt 임포트 영상은 사람 최종본이
#   whisper와 다른 분할·출처라 CER이 폭발 (58%가 모델 성능처럼 보임),
#   (b) 검수자가 에코/중복 텍스트를 잘라내는 구조 편집이 오인식과 섞임.
#   기존 컬럼(전량 CER)은 비교 가능성 유지를 위해 그대로 두고, 출처 표시와
#   길이비 필터 "매칭 CER"(0.5≤final/whisper≤2.0인 세그먼트만)을 추가.
#   매칭 CER이 '기계가 잘못 들었나'에 가장 가까운 다이얼.
# Related: CHANGELOG CHG-20260714-013. 정규화(_norm)는 불변 (ADR-level).
_MATCH_RATIO = (0.5, 2.0)


def evaluate_all() -> list[dict]:
    """Per-job CER for every job that has reviewed segments."""
    from .db import SrtBackup

    out: list[dict] = []
    with get_session() as session:
        srt_imported = set(session.exec(select(SrtBackup.video_id)).all())
        jobs = session.exec(select(Job).order_by(Job.created_at)).all()
        for job in jobs:
            if job.practice:  # tutorial sandbox — synthetic TTS, skews CER
                continue
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

            # 매칭 CER: 구조 편집(에코 삭제·재분배)된 세그먼트 제외 — 최종본과
            # whisper의 길이비가 정상 범위인 행만 (오인식 신호 분리)
            lo, hi = _MATCH_RATIO
            matched = [
                s
                for s in segs
                if s.text_whisper.strip()
                and lo <= len(s.text_final.strip()) / max(1, len(s.text_whisper.strip())) <= hi
            ]
            if matched:
                m_ref = " ".join(s.text_final for s in matched)
                m_llm = " ".join(s.text_llm or s.text_whisper for s in matched)
                cer_matched = round(_cer(m_ref, m_llm), 4)
            else:
                cer_matched = None

            out.append(
                {
                    "video_id": job.video_id,
                    "title": job.title[:40],
                    "date": job.created_at.date().isoformat(),
                    "reviewed_segments": len(segs),
                    "source": "srt" if job.video_id in srt_imported else "app",
                    "cer_whisper": round(_cer(ref, hyp_whisper), 4),
                    "cer_llm": round(_cer(ref, hyp_llm), 4),
                    "cer_matched": cer_matched,
                    "matched_segments": len(matched),
                }
            )
    return out
