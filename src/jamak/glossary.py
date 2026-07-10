"""Ouroboros read side: pull learned vocabulary and correction pairs
out of the DB and shape them for injection into whisper / Claude."""

from __future__ import annotations

from sqlmodel import select

from .db import Correction, GlossaryTerm, get_session
from .learned_pairs import is_safe_correction_pair


def whisper_prompt(max_terms: int = 60) -> str:
    """Approved glossary terms as an initial_prompt for whisper.

    Whisper treats the prompt as preceding transcript, so a natural
    sentence listing the vocabulary works better than a bare word list.
    """
    with get_session() as session:
        terms = session.exec(
            select(GlossaryTerm)
            .where(GlossaryTerm.approved == True)  # noqa: E712
            .limit(max_terms)
        ).all()
    if not terms:
        return "허경영 강연입니다. 신인, 축지법, 공중부양, 하늘궁 같은 용어가 나옵니다."
    words = ", ".join(t.term for t in terms)
    return f"허경영 강연입니다. 다음 용어가 자주 나옵니다: {words}."


def whisper_hotwords(max_terms: int = 100) -> str:
    """Approved glossary terms as a space-separated hotword string.

    faster-whisper biases the acoustic decoder toward these, so whisper is
    more likely to *hear* domain terms correctly (not just have them fixed
    downstream). Zero-cost, grows as the glossary is approved.
    """
    with get_session() as session:
        terms = session.exec(
            select(GlossaryTerm.term)
            .where(GlossaryTerm.approved == True)  # noqa: E712
            .limit(max_terms)
        ).all()
    return " ".join(t for t in terms if t)


def glossary_block(max_terms: int = 200) -> str:
    """Glossary as a text block for the Claude correction prompt."""
    with get_session() as session:
        terms = session.exec(
            select(GlossaryTerm)
            .where(GlossaryTerm.approved == True)  # noqa: E712
            .limit(max_terms)
        ).all()
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
