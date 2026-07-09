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
MAX_CANDIDATES = 500  # cap so the review queue stays tractable

# lecture-transcript .txt format:
#   [2024.11.11] title...
#   (19분 59초)
#   01:14
#   text paragraph...
_HEADER_RE = re.compile(r"^\[\d{4}\.\d{2}\.\d{2}\]")
_TIMECODE_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?\s*$")
_DURATION_RE = re.compile(r"^\(\d+분(\s*\d+초)?\)\s*$")


def _read_text(f: Path) -> str:
    try:
        return f.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f.read_text(encoding="cp949")


def _texts_from_srt(f: Path) -> tuple[list[str], int]:
    subs = list(srt.parse(_read_text(f)))
    return [s.content for s in subs], 1


def _texts_from_txt(f: Path) -> tuple[list[str], int]:
    """Strip headers/timecodes; count lecture documents by [date] headers."""
    lines = _read_text(f).splitlines()
    n_docs = 0
    texts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if _HEADER_RE.match(line):
            n_docs += 1
            continue
        if _TIMECODE_RE.match(line) or _DURATION_RE.match(line):
            continue
        texts.append(line)
    return texts, max(n_docs, 1)


def import_seeds(directory: Path) -> dict:
    files = sorted(list(directory.glob("**/*.srt")) + list(directory.glob("**/*.txt")))
    counter: Counter[str] = Counter()
    n_docs = 0

    for f in files:
        texts, docs = (
            _texts_from_srt(f) if f.suffix == ".srt" else _texts_from_txt(f)
        )
        n_docs += docs
        for text in texts:
            for token in _TOKEN_RE.findall(text):
                if token not in _STOPWORDS:
                    counter[token] += 1

    candidates = [
        (term, n) for term, n in counter.most_common(MAX_CANDIDATES) if n >= MIN_COUNT
    ]

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
                    note=f"검수 자막 {n_docs}개 문서에서 {n}회 등장",
                    confidence=min(1.0, n / 50),
                    # auto-extracted terms start unapproved; /glossary-review
                    # promotes the real vocabulary and deletes noise
                    approved=False,
                )
            )
            added += 1
        session.commit()

    return {"files": len(files), "docs": n_docs, "terms": added, "pairs": 0}
