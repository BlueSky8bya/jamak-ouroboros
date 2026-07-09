"""Stage 4 — LLM correction: Claude fixes what whisper misheard.

The prompt is assembled ouroboros-style:
  system = task + glossary (from DB) + few-shot correction pairs (from DB)
The system prompt is stable across chunks, so it's cached (prompt caching)
and each chunk request only pays for the segments themselves.
"""

from __future__ import annotations

import json

from sqlmodel import select

from ..config import CLAUDE_MODEL
from ..db import Segment, get_session
from ..glossary import fewshot_corrections, glossary_block

CHUNK_SIZE = 50  # segments per request
CONTEXT_OVERLAP = 5  # trailing segments repeated as read-only context

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "text": {"type": "string"},
                    "uncertain": {"type": "boolean"},
                },
                "required": ["idx", "text", "uncertain"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["corrections"],
    "additionalProperties": False,
}


def build_system_prompt() -> str:
    glossary = glossary_block()
    pairs = fewshot_corrections()

    parts = [
        "당신은 허경영 강연 영상의 한국어 자막 교정 전문가입니다.",
        "",
        "입력: 음성인식(STT) 결과 세그먼트 목록. 각 세그먼트는 idx, whisper 텍스트, "
        "유튜브 자동자막 텍스트(참고용, 없을 수 있음)를 가집니다.",
        "",
        "작업 규칙:",
        "1. 오인식된 단어를 문맥에 맞게 교정한다 (아래 용어사전과 과거 교정 사례 참고).",
        "2. 발화 내용을 절대 창작하거나 요약하지 않는다. 들린 대로, 다만 정확한 단어로.",
        "3. 구어체는 유지한다. 사투리는 알아들을 수 있는 선에서 유지한다.",
        "4. 명백한 잡음/박수 구간 텍스트는 빈 문자열로 만든다.",
        "5. 확신이 없는 교정은 uncertain=true로 표시한다 (사람이 우선 검토).",
        "6. 변경이 필요 없는 세그먼트도 corrections에 포함한다 (원문 그대로).",
        "7. 두 자막 소스가 다르면 문맥상 더 그럴듯한 쪽을 선택하거나 조합한다.",
    ]

    if glossary:
        parts += ["", "## 용어사전 (이 어휘들이 자주 나옴 — 오인식 주의)", glossary]

    if pairs:
        parts += ["", "## 과거 검수에서 확정된 교정 사례 (오인식 → 정답)"]
        for wrong, right, context in pairs:
            ctx = f" (문맥: {context})" if context else ""
            parts.append(f'- "{wrong}" → "{right}"{ctx}')

    return "\n".join(parts)


def correct_chunk(client, system_prompt: str, chunk: list[dict], context_before: list[str]) -> list[dict]:
    """One API call: chunk of segments in, corrected texts out."""
    lines = []
    if context_before:
        lines.append("### 직전 문맥 (교정 대상 아님):")
        lines.extend(f"  {t}" for t in context_before)
        lines.append("")
    lines.append("### 교정 대상 세그먼트:")
    for seg in chunk:
        yt = f' | 자동자막: "{seg["text_youtube"]}"' if seg["text_youtube"] else ""
        flag = " [불일치]" if seg["flagged"] else ""
        lines.append(f'[{seg["idx"]}] whisper: "{seg["text_whisper"]}"{yt}{flag}')

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},  # stable across chunks
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["corrections"]


def correct_job(job_id: int, console=None) -> int:
    """Run Claude correction over every segment of a job. Returns #changed."""
    import anthropic

    client = anthropic.Anthropic()
    system_prompt = build_system_prompt()

    with get_session() as session:
        segments = session.exec(
            select(Segment).where(Segment.job_id == job_id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segments]

    n_changed = 0
    results: dict[int, tuple[str, bool]] = {}

    for start in range(0, len(seg_dicts), CHUNK_SIZE):
        chunk = seg_dicts[start : start + CHUNK_SIZE]
        context_before = [
            d["text_whisper"] for d in seg_dicts[max(0, start - CONTEXT_OVERLAP) : start]
        ]
        corrections = correct_chunk(client, system_prompt, chunk, context_before)
        for c in corrections:
            results[c["idx"]] = (c["text"], c["uncertain"])
        if console:
            console.print(f"  chunk {start // CHUNK_SIZE + 1}: {len(corrections)} segments")

    with get_session() as session:
        segments = session.exec(
            select(Segment).where(Segment.job_id == job_id)
        ).all()
        for seg in segments:
            if seg.idx in results:
                text, uncertain = results[seg.idx]
                seg.text_llm = text
                seg.llm_uncertain = uncertain
                if text.strip() != seg.text_whisper.strip():
                    n_changed += 1
                session.add(seg)
        session.commit()

    return n_changed
