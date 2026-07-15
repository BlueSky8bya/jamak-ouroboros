"""Export the approved glossary (DB is source of truth) to a Markdown doc.

Usage:
    $env:DATABASE_URL=...; uv run python scripts/export_glossary.py

Writes docs/glossary.md — the human-readable "강연 용어사전". These terms are
injected into the AI spellcheck prompt so domain vocabulary is protected from
being 'corrected' into ordinary words. Regenerate after editing terms in the DB.
"""
import sys
from collections import defaultdict
from pathlib import Path

from sqlmodel import select

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jamak.db import GlossaryTerm, get_session  # noqa: E402

OUT = ROOT / "docs" / "glossary.md"


def main() -> None:
    with get_session() as s:
        rows = list(s.exec(select(GlossaryTerm).where(GlossaryTerm.approved == True)))  # noqa: E712
    by_cat: dict[str, list] = defaultdict(list)
    for t in rows:
        by_cat[t.category or "(미분류)"].append(t)

    lines = [
        "# 허경영 강연 용어사전 (glossary)",
        "",
        "> **생성 문서 — 손으로 고치지 마세요.** 원본은 DB `GlossaryTerm` 테이블이며,",
        "> `uv run python scripts/export_glossary.py`로 다시 만듭니다.",
        "",
        "AI 맞춤법 검사가 이 용어들을 **일반어로 오교정하지 않도록 보호**합니다",
        "(예: '5백궁'을 '500궁'으로 바꾸지 않음). 오인식 변형이 있으면 바른 표기로 되돌립니다.",
        "",
        f"총 {len(rows)}종.",
        "",
    ]
    for cat in sorted(by_cat):
        terms = sorted(by_cat[cat], key=lambda t: t.term)
        lines.append(f"## {cat} ({len(terms)})")
        lines.append("")
        lines.append("| 용어 | 오인식 변형 | 설명 |")
        lines.append("|---|---|---|")
        for t in terms:
            lines.append(f"| {t.term} | {t.variants} | {t.note} |")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(rows)} terms, {len(by_cat)} categories)")


if __name__ == "__main__":
    main()
