"""Mine a curated glossary from a hand-reviewed transcript corpus.

The 1-year human-reviewed corpus already contains the *correct* spellings of
every domain term (고유어휘/종교 용어/한자어/인명/지명). We can't derive
correction PAIRS from it (no machine draft to diff against), but we can fill
the glossary + hotwords richly:

  1. deterministic candidate extraction (frequency, no API)
  2. ONE cheap Claude pass that keeps only genuine domain vocabulary, assigns
     a category, and adds likely misrecognition variants

This is a deliberate one-time API spend (a few cents over a word list, not the
full corpus) that pays off forever: every future video's whisper hotwords /
prompt + Claude correction improve, cutting per-video correction cost.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import seed  # reuse the transcript readers + tokenizer

from .config import CORRECT_MODEL
from .db import GlossaryTerm, get_session

MAX_CANDIDATES = 1500  # deterministic recall pool sent to Claude for curation
CHUNK = 200  # candidates per API call (small — just a word list)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term": {"type": "string"},
                    "category": {"type": "string"},
                    "variants": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["term", "category", "variants"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["terms"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = "\n".join(
    [
        "당신은 허경영 강연 자막의 용어사전을 만드는 한국어 전문가입니다.",
        "",
        "입력: 검수 완료된 강연 전사에서 빈도순으로 뽑은 단어 후보 목록.",
        "",
        "작업: 자막 정확도에 도움이 되는 '도메인 고유 어휘'만 선별한다.",
        "- 포함: 허경영 고유어휘(신인, 축지법, 공중부양, 하늘궁 등), 종교 용어",
        "  (불교/유교/기독교: 에스더, 수가성, 아멘 등), 한자어, 인명, 지명, 사상·정책 용어.",
        "- 제외: 일반 명사·동사·부사, 조사·어미, 흔한 구어체, 대명사, 애매한 조각.",
        "각 선별 term에:",
        "- category: 고유어휘 / 불교 / 유교 / 기독교 / 한자어 / 인명 / 지명 / 정책 중 하나.",
        "- variants: 음성인식이 헷갈릴 만한 한국어 동음이의 오인식 표기 0~3개",
        "  (예: 축지법→축제법, 수가성→수화성). 확실하지 않으면 빈 배열.",
        "일반어가 대부분이면 terms를 짧게 반환한다. 억지로 채우지 않는다.",
    ]
)


def extract_candidates(directory: Path, top: int = MAX_CANDIDATES) -> list[tuple[str, int]]:
    """Frequency-ranked domain-word candidates from the seed corpus (no API)."""
    files = sorted(list(directory.glob("**/*.txt")) + list(directory.glob("**/*.srt")))
    counter: Counter[str] = Counter()
    for f in files:
        texts, _ = (
            seed._texts_from_srt(f) if f.suffix == ".srt" else seed._texts_from_txt(f)
        )
        for text in texts:
            for token in seed._TOKEN_RE.findall(text):
                if token not in seed._STOPWORDS:
                    counter[token] += 1
    # need a couple of repeats to be worth a glossary slot
    return [(t, n) for t, n in counter.most_common(top) if n >= 3]


# [WH-CHANGE v0.6.4 | FEAT | 2026-07-14 | CHG-20260714-015]
# Reason: the file-corpus miner can't see what whisper actually misheard.
#   Reviewed DB segments carry BOTH the machine draft (text_whisper) and the
#   human truth (text_final) — token-aligning them yields real
#   (misrecognition -> correct) pairs, the highest-value glossary signal
#   (variants drive correction accuracy). User-directed design.
# Related: CHANGELOG CHG-20260714-015.
def extract_db_candidates(
    top: int = MAX_CANDIDATES,
) -> tuple[list[tuple[str, int]], list[tuple[str, str, int]]]:
    """(frequency candidates, (correct, misheard, count) pairs) from reviewed
    non-practice DB segments. Deterministic, no API."""
    import difflib

    from sqlmodel import select

    from .db import Job, Segment

    counter: Counter[str] = Counter()
    pair_counter: Counter[tuple[str, str]] = Counter()
    with get_session() as session:
        rows = session.exec(
            select(Segment.text_final, Segment.text_whisper)
            .join(Job, Segment.job_id == Job.id)
            .where(
                Segment.lang == "ko",
                Segment.reviewed == True,  # noqa: E712
                Job.practice == False,  # noqa: E712
            )
        ).all()
    for final, whisper in rows:
        f_tokens = [
            t for t in seed._TOKEN_RE.findall(final or "") if t not in seed._STOPWORDS
        ]
        for t in f_tokens:
            counter[t] += 1
        if not whisper or whisper == final:
            continue
        w_tokens = seed._TOKEN_RE.findall(whisper)
        f_all = seed._TOKEN_RE.findall(final or "")
        sm = difflib.SequenceMatcher(None, w_tokens, f_all, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            # only clean 1:1 token substitutions — same count both sides keeps
            # the pairing unambiguous (echo trims/splits show up as insert/delete)
            if op == "replace" and (i2 - i1) == (j2 - j1):
                for wrong, right in zip(w_tokens[i1:i2], f_all[j1:j2]):
                    if (
                        wrong != right
                        and len(right) >= 2
                        and right not in seed._STOPWORDS
                        and wrong not in seed._STOPWORDS
                    ):
                        pair_counter[(right, wrong)] += 1
    freq = [(t, n) for t, n in counter.most_common(top) if n >= 3]
    pairs = [
        (right, wrong, n)
        for (right, wrong), n in pair_counter.most_common(400)
        if n >= 2  # a one-off mistake isn't a pattern
    ]
    return freq, pairs


def _curate_chunk(
    client, chunk: list[tuple[str, int]], usage: dict, extra: str = ""
) -> list[dict]:
    lines = [f"{t} ({n}회)" for t, n in chunk]
    response = client.messages.create(
        model=CORRECT_MODEL,
        max_tokens=8000,
        thinking={"type": "disabled"},  # classification — no thinking tokens
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # stable across chunks
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": extra + "단어 후보:\n" + "\n".join(lines)}],
    )
    u = response.usage
    usage["input"] += u.input_tokens + (u.cache_creation_input_tokens or 0)
    usage["cached"] += u.cache_read_input_tokens or 0
    usage["output"] += u.output_tokens
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["terms"]


def mine_glossary(directory: Path | None, console=None) -> dict:
    """Extract + curate + upsert an approved glossary.

    directory=None mines the reviewed DB segments instead of a file corpus —
    frequency candidates plus real (misheard -> correct) diff pairs."""
    import anthropic

    diff_pairs: list[tuple[str, str, int]] = []
    if directory is None:
        candidates, diff_pairs = extract_db_candidates()
    else:
        candidates = extract_candidates(directory)
    if console:
        console.print(
            f"candidates extracted (no API): {len(candidates)}"
            + (f", diff pairs: {len(diff_pairs)}" if directory is None else "")
        )
    if not candidates and not diff_pairs:
        return {"candidates": 0, "kept": 0, "updated": 0}

    client = anthropic.Anthropic()
    usage = {"input": 0, "cached": 0, "output": 0}
    curated: dict[str, dict] = {}
    for start in range(0, len(candidates), CHUNK):
        chunk = candidates[start : start + CHUNK]
        extra = ""
        if start == 0 and diff_pairs:
            # the strongest evidence goes in front of the first chunk: these
            # words were ACTUALLY misrecognized in this corpus
            pair_lines = [f"{r} ← 오인식: {w} ({n}회)" for r, w, n in diff_pairs[:150]]
            extra = (
                "## 실제 오인식 기록 (검수자가 이렇게 고침 — variants에 반영):\n"
                + "\n".join(pair_lines)
                + "\n\n"
            )
        for t in _curate_chunk(client, chunk, usage, extra):
            term = t["term"].strip()
            if term:
                curated[term] = t
        if console:
            console.print(
                f"  chunk {start // CHUNK + 1}: {len(curated)} terms kept so far"
            )

    kept = 0
    updated = 0
    with get_session() as session:
        from sqlmodel import select

        for term, t in curated.items():
            variants = ", ".join(v.strip() for v in t.get("variants", []) if v.strip())
            existing = session.exec(
                select(GlossaryTerm).where(GlossaryTerm.term == term)
            ).first()
            if existing:
                existing.category = t.get("category", existing.category)
                if variants:
                    existing.variants = variants
                existing.approved = True
                existing.confidence = 1.0
                session.add(existing)
                updated += 1
            else:
                session.add(
                    GlossaryTerm(
                        term=term,
                        category=t.get("category", ""),
                        variants=variants,
                        approved=True,
                        confidence=1.0,
                    )
                )
                kept += 1
        session.commit()

    if console and (usage["input"] or usage["output"]):
        cost = (usage["input"] * 2 + usage["cached"] * 0.2 + usage["output"] * 10) / 1_000_000
        console.print(
            f"tokens: in {usage['input']:,} (+{usage['cached']:,} cached) / "
            f"out {usage['output']:,}  ~ ${cost:.3f}"
        )

    return {"candidates": len(candidates), "kept": kept, "updated": updated}
