"""Ouroboros read side: pull learned vocabulary and correction pairs
out of the DB and shape them for injection into whisper / Claude."""

from __future__ import annotations

from sqlmodel import select

from .db import Correction, GlossaryTerm, HanjaTerm, get_session
from .learned_pairs import is_safe_correction_pair


# [WH-CHANGE v0.9.34 | FIX | 2026-07-16 | CHG-20260716-056]
# Reason: 도메인 어휘가 두 테이블에 갈라져 있었다 — glossary(129) 따로, 한자
#   사전 특수어(420) 따로. STT 힌트·맞춤법 보호는 glossary만 봐서 검증된 흑판
#   교리어 412종이 새어나갔다. 두 원본의 합집합을 도메인 어휘로 노출한다.
#   일상어인 한자 common tier(인간·일본 등)는 제외 — 보호할 필요 없고 힌트만
#   희석한다.
# Related: CHANGELOG CHG-20260716-056.
def hanja_domain_readings(limit: int = 600) -> list[str]:
    """검증된 흑판 특수어(한자 다자어)의 한글 표기 — 등장 빈도 내림차순."""
    with get_session() as session:
        rows = session.exec(
            select(HanjaTerm.reading)
            .where(HanjaTerm.gloss == "", HanjaTerm.tier == "special")  # noqa: E712
            .order_by(HanjaTerm.count.desc())
            .limit(limit)
        ).all()
    return [r for r in rows if r and len(r) >= 2]


def domain_terms(limit: int = 900) -> list[str]:
    """맞춤법 보호·STT 힌트용 통합 도메인 어휘 (glossary ∪ 한자 특수어).

    glossary 용어를 confidence 순으로 먼저(가장 중요), 이어서 한자 특수어를
    빈도순으로 붙이고 중복 제거(첫 등장 순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for t in _approved_terms(limit):
        if t.term and t.term not in seen:
            seen.add(t.term)
            out.append(t.term)
    for r in hanja_domain_readings():
        if r not in seen:
            seen.add(r)
            out.append(r)
        if len(out) >= limit:
            break
    return out


# [WH-CHANGE v0.9.33 | FIX | 2026-07-16 | CHG-20260716-055]
# Reason: glossary가 129종으로 커지며 whisper 상한(100/60)을 넘겨 일부 용어가
#   STT 힌트에서 잘렸고, .limit()에 정렬이 없어 어떤 게 잘릴지 임의적이었다.
#   승인 용어 전부를 STT/교정에 넣도록 상한을 올리고, confidence 내림차순으로
#   정렬해 잘릴 경우 저확신 후보부터 밀려나게 한다.
# Related: CHANGELOG CHG-20260716-055.
def _approved_terms(limit: int):
    """Approved terms, highest-confidence first (deterministic tie-break)."""
    with get_session() as session:
        return session.exec(
            select(GlossaryTerm)
            .where(GlossaryTerm.approved == True)  # noqa: E712
            .order_by(GlossaryTerm.confidence.desc(), GlossaryTerm.term)
            .limit(limit)
        ).all()


def whisper_prompt(max_terms: int = 120) -> str:
    """Approved glossary terms as an initial_prompt for whisper.

    Whisper treats the prompt as preceding transcript, so a natural
    sentence listing the vocabulary works better than a bare word list.
    """
    terms = _approved_terms(max_terms)
    if not terms:
        return "허경영 강연입니다. 신인, 축지법, 공중부양, 하늘궁 같은 용어가 나옵니다."
    words = ", ".join(t.term for t in terms)
    return f"허경영 강연입니다. 다음 용어가 자주 나옵니다: {words}."


def whisper_hotwords(max_terms: int = 300) -> str:
    """Unified domain vocabulary (glossary ∪ 한자 특수어) as a space-separated
    hotword string.

    faster-whisper biases the acoustic decoder toward these, so whisper is
    more likely to *hear* domain terms correctly (not just have them fixed
    downstream). Zero-cost, grows as the glossary/한자 사전 grow.

    Only canonical forms — NOT the misrecognition variants, which are the
    *wrong* forms (biasing whisper toward those would defeat the point).
    """
    return " ".join(domain_terms(max_terms))


def glossary_block(max_terms: int = 400) -> str:
    """Glossary as a text block for the Claude correction prompt."""
    terms = _approved_terms(max_terms)
    lines = []
    for t in terms:
        variants = f" (오인식 예: {t.variants})" if t.variants else ""
        cat = f" [{t.category}]" if t.category else ""
        lines.append(f"- {t.term}{cat}{variants}")
    return "\n".join(lines)


def glossary_surface_forms() -> set[str]:
    """Every approved term + its known misrecognition variants, as a flat set.

    Cheap membership test for "does this segment touch domain vocabulary?" —
    lets the correction stage skip the LLM on ordinary segments that carry no
    domain-vocab risk (and that the LLM would return unchanged anyway).
    """
    forms: set[str] = set()
    with get_session() as session:
        rows = session.exec(
            select(GlossaryTerm).where(GlossaryTerm.approved == True)  # noqa: E712
        ).all()
    for t in rows:
        if t.term.strip():
            forms.add(t.term.strip())
        for v in t.variants.split(","):
            if v.strip():
                forms.add(v.strip())
    return forms


def fewshot_corrections(max_pairs: int = 40) -> list[tuple[str, str, str]]:
    """Most frequent learned corrections: (wrong, right, context)."""
    with get_session() as session:
        rows = session.exec(
            select(Correction).order_by(Correction.count.desc()).limit(max_pairs * 3)
        ).all()
    return [
        (c.wrong, c.right, c.context)
        for c in rows
        if is_safe_correction_pair(c.wrong, c.right)
    ][:max_pairs]
