"""Ouroboros bootstrap: import past human-reviewed .srt files.

These files are finished work — the loop's initial fuel. From them we extract:
  1. glossary candidates: domain-specific vocabulary (proper nouns, jargon)
  2. correction pairs: only possible when a matching machine draft exists,
     so on first import we mainly seed the glossary; pairs accrue later
     from the review workflow.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import srt
from sqlmodel import select

from .db import GlossaryTerm, get_session

# Words that appear in reviewed subtitles but are rare in generic Korean text.
# Simple heuristic for a first pass: 2+ char Korean nouns that repeat often.
_TOKEN_RE = re.compile(r"[가-힣]{2,}")

# generic words to skip — high frequency in any Korean speech
_STOPWORDS = {
    "그리고", "그런데", "그래서", "하지만", "그러면", "여러분", "우리가", "이제",
    "지금", "하나", "사람", "생각", "말씀", "때문", "정도", "얘기", "그거",
    "이거", "저거", "그게", "이게", "무슨", "어떤", "이런", "그런", "저런",
    "해서", "하는", "있는", "없는", "같은", "번째",
}

MIN_COUNT = 5  # a term must recur this often across the corpus to be a candidate


def import_seeds(directory: Path) -> dict:
    files = sorted(directory.glob("**/*.srt"))
    counter: Counter[str] = Counter()

    for f in files:
        try:
            subs = list(srt.parse(f.read_text(encoding="utf-8")))
        except Exception:
            subs = list(srt.parse(f.read_text(encoding="cp949")))
        for sub in subs:
            for token in _TOKEN_RE.findall(sub.content):
                if token not in _STOPWORDS:
                    counter[token] += 1

    candidates = [(term, n) for term, n in counter.most_common() if n >= MIN_COUNT]

    added = 0
    with get_session() as session:
        for term, n in candidates:
            existing = session.exec(
                select(GlossaryTerm).where(GlossaryTerm.term == term)
            ).first()
            if existing:
                continue
            session.add(
                GlossaryTerm(
                    term=term,
                    category="자동추출",
                    note=f"검수 자막 {len(files)}개에서 {n}회 등장",
                    confidence=min(1.0, n / 50),
                    # auto-extracted terms start unapproved; /glossary-review
                    # promotes the real vocabulary and deletes noise
                    approved=False,
                )
            )
            added += 1
        session.commit()

    return {"files": len(files), "terms": added, "pairs": 0}
