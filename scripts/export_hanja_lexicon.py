"""Export the HanjaTerm lexicon (DB is the source of truth) to a Markdown doc.

Usage:
    $env:DATABASE_URL=...; uv run python scripts/export_hanja_lexicon.py

Writes docs/hanja-lexicon.md — the human-readable "신인님 강연 한자어 사전".
Regenerate after editing terms in the DB; never edit the .md by hand.
"""
import sys
from collections import defaultdict
from pathlib import Path

from sqlmodel import select

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jamak.db import HanjaTerm, get_session  # noqa: E402

OUT = ROOT / "docs" / "hanja-lexicon.md"


def main() -> None:
    with get_session() as s:
        terms = s.exec(select(HanjaTerm)).all()
    single = sorted(
        ((t.gloss, t.reading, t.hanja, t.count) for t in terms if t.gloss),
        key=lambda x: (x[1], x[0]),
    )
    multi = [t for t in terms if not t.gloss and len(t.reading) >= 2]
    special = sorted(
        ((t.reading, t.hanja, t.count) for t in multi if t.tier == "special")
    )
    common = sorted(
        ((t.reading, t.hanja, t.count) for t in multi if t.tier != "special")
    )

    lines = [
        "# 신인님 강연 한자어 사전",
        "",
        "> **생성 문서 — 손으로 고치지 마세요.** 원본은 DB `HanjaTerm` 테이블이며,",
        "> 이 파일은 `uv run python scripts/export_hanja_lexicon.py`로 다시 만듭니다.",
        "> 출처: 검수 완료 대본(오늘의 신인님 txt + 검수 DB)의 기존 병기 패턴 채굴.",
        "",
        "『漢 한자 채우기』 도구의 사전입니다. 목표는 **흑판(칠판)에 쓰면서 강연한",
        "한자만 병기**하는 것 — 불교·유교 같은 일상 한자어는 병기하지 않습니다.",
        "",
        f"## 1. 흑판 특수어 — 자동 병기 대상 ({len(special)}개)",
        "",
        "검수자가 대본에서 거의 항상 병기해 둔 표현 (병기 비율 ≥ 50%) + 만트라·",
        "건강 팔소다류 수동 승격. 채우기 도구가 이 목록만 자막에 제안합니다.",
        "",
        "| 표기 | 한자 | 출처 빈도 |",
        "|---|---|---|",
    ]
    lines += [f"| {r} | {h} | {c} |" for r, h, c in special]
    lines += [
        "",
        f"## 2. 단일자 — 「뜻 음 자」 풀이 전용 ({len(single)}개)",
        "",
        '자막이 "얼굴 안 자"처럼 글자를 풀어 말할 때만 그 자리에서 병기합니다',
        "(뜻+음 짝이 일치해야 하므로 동음이의자에 안전: 얼굴 안=顔, 편안할 안=安).",
        "",
        "| 뜻 | 음 | 한자 | 출처 빈도 |",
        "|---|---|---|---|",
    ]
    lines += [f"| {g} | {r} | {h} | {c} |" for g, r, h, c in single]
    lines += [
        "",
        f"## 3. 일반 한자어 — 사전 보존, 자동 병기 제외 ({len(common)}개)",
        "",
        "강연 어딘가에서 한두 번 병기된 적은 있으나 평소 말에도 흔히 쓰이는 단어",
        "(무시·다정·자체·수면 등 동형어 위험 포함). 기록으로 남기되 채우기 도구는",
        "건드리지 않습니다.",
        "",
        "| 표기 | 한자 | 출처 빈도 |",
        "|---|---|---|",
    ]
    lines += [f"| {r} | {h} | {c} |" for r, h, c in common]
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(special)} special / {len(single)} single / {len(common)} common)")


if __name__ == "__main__":
    main()
