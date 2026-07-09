"""Stage 4 — LLM correction: Claude fixes what whisper misheard.

Cost structure (cheapest first):
  1. pre-pass: learned correction pairs (count >= PREPASS_MIN_COUNT) are
     applied as plain string replacement — zero API cost, grows with
     every review the ouroboros absorbs
  2. cache: segments whose source text was corrected before reuse the
     stored answer (re-running a video costs nothing)
  3. LLM: only the remainder goes to Claude, and Claude returns ONLY the
     segments it changed — output tokens scale with mistakes, not with
     transcript length

The prompt is assembled ouroboros-style:
  system = task + glossary (from DB) + few-shot correction pairs (from DB)
and is cached across chunks via prompt caching.
"""

from __future__ import annotations

import hashlib
import json
import re

from sqlmodel import select

from ..config import CORRECT_MODEL, PREPASS_MIN_COUNT
from ..db import Correction, LlmCache, Segment, get_session
from ..glossary import fewshot_corrections, glossary_block
from ..learned_pairs import is_safe_correction_pair

CHUNK_SIZE = 50  # segments per request
CONTEXT_OVERLAP = 5  # trailing segments repeated as read-only context
PROMPT_VERSION = "v3"  # bump to invalidate the correction cache

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


def _hash(*parts: str) -> str:
    joined = "\x1f".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def load_prepass_pairs() -> list[tuple[str, str]]:
    """Learned pairs confirmed often enough to apply deterministically."""
    with get_session() as session:
        rows = session.exec(
            select(Correction)
            .where(Correction.count >= PREPASS_MIN_COUNT)
            .order_by(Correction.count.desc())
        ).all()
    return [
        (c.wrong, c.right)
        for c in rows
        if is_safe_correction_pair(c.wrong, c.right)
    ]


def apply_prepass(text: str, pairs: list[tuple[str, str]]) -> str:
    """Word-boundary replacement of learned pairs — free corrections."""
    for wrong, right in pairs:
        if not is_safe_correction_pair(wrong, right):
            continue
        pattern = r"(?<![\w가-힣])" + re.escape(wrong) + r"(?![\w가-힣])"
        text = re.sub(pattern, right, text)
    return text


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
        "3. 구어체와 사투리는 유지한다. 표준어로 다듬지 않는다.",
        "4. 명백한 잡음/박수 구간 텍스트는 text를 빈 문자열로 만든다.",
        "5. 확신이 없는 교정은 uncertain=true로 표시한다 (사람이 우선 검토).",
        "6. **수정이 필요한 세그먼트만 corrections에 포함한다.** 이상 없는 세그먼트는"
        " 응답에 포함하지 않는다 (미포함 = 원문 유지로 처리됨).",
        "7. 두 자막 소스가 다르면 문맥상 더 그럴듯한 쪽을 선택하거나 조합한다.",
        "8. 대명사/지시어(예: 그 여자, 그 사람, 그분)는 들린 그대로 둔다. "
        "앞뒤 문맥만 보고 고유명사로 풀어쓰지 않는다.",
    ]

    if glossary:
        parts += ["", "## 용어사전 (이 어휘들이 자주 나옴 — 오인식 주의)", glossary]

    if pairs:
        parts += ["", "## 과거 검수에서 확정된 교정 사례 (오인식 → 정답)"]
        for wrong, right, context in pairs:
            ctx = f" (문맥: {context})" if context else ""
            parts.append(f'- "{wrong}" → "{right}"{ctx}')

    return "\n".join(parts)


def correct_chunk(
    client, system_prompt: str, chunk: list[dict], context_before: list[str], usage: dict
) -> list[dict]:
    """One API call: chunk of segments in, changed segments out."""
    lines = []
    if context_before:
        lines.append("### 직전 문맥 (교정 대상 아님):")
        lines.extend(f"  {t}" for t in context_before)
        lines.append("")
    lines.append("### 교정 대상 세그먼트:")
    for seg in chunk:
        yt = f' | 자동자막: "{seg["text_youtube"]}"' if seg["text_youtube"] else ""
        flag = " [불일치]" if seg["flagged"] else ""
        lines.append(f'[{seg["idx"]}] whisper: "{seg["base_text"]}"{yt}{flag}')

    response = client.messages.create(
        model=CORRECT_MODEL,
        max_tokens=16000,
        # mechanical correction task — adaptive thinking would bill large
        # invisible output tokens for no quality gain here
        thinking={"type": "disabled"},
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
    u = response.usage
    usage["input"] += u.input_tokens + (u.cache_creation_input_tokens or 0)
    usage["cached"] += u.cache_read_input_tokens or 0
    usage["output"] += u.output_tokens
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["corrections"]


def correct_job(job_id: int, console=None) -> int:
    """Run correction over every segment of a job. Returns #changed."""
    import anthropic

    prepass_pairs = load_prepass_pairs()

    with get_session() as session:
        segments = session.exec(
            select(Segment).where(Segment.job_id == job_id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segments]

    # ---- tier 1: free pre-pass from learned pairs
    for d in seg_dicts:
        d["base_text"] = apply_prepass(d["text_whisper"], prepass_pairs)
        d["hash"] = _hash(PROMPT_VERSION, d["base_text"], d["text_youtube"])

    # ---- tier 2: cache lookup
    # results are keyed by segment id (idx can shift if the user edits
    # structure in the web app while the LLM is running)
    results: dict[int, tuple[str, bool]] = {}  # segment id -> (text, uncertain)
    todo: list[dict] = []
    with get_session() as session:
        for d in seg_dicts:
            cached = session.exec(
                select(LlmCache).where(
                    LlmCache.kind == "correct", LlmCache.source_hash == d["hash"]
                )
            ).first()
            if cached is not None:
                text = cached.text if cached.changed else d["base_text"]
                results[d["id"]] = (text, cached.uncertain)
            else:
                todo.append(d)

    if console:
        console.print(
            f"  pre-pass pairs: {len(prepass_pairs)} | "
            f"cache hits: {len(seg_dicts) - len(todo)}/{len(seg_dicts)} | "
            f"to LLM: {len(todo)}"
        )

    # ---- tier 3: LLM for the remainder (returns changed segments only)
    usage = {"input": 0, "cached": 0, "output": 0}
    if todo:
        client = anthropic.Anthropic()
        system_prompt = build_system_prompt()
        changed_by_idx: dict[int, tuple[str, bool]] = {}

        for start in range(0, len(todo), CHUNK_SIZE):
            chunk = todo[start : start + CHUNK_SIZE]
            first_idx = chunk[0]["idx"]
            context_before = [
                d["base_text"]
                for d in seg_dicts
                if d["idx"] < first_idx and first_idx - d["idx"] <= CONTEXT_OVERLAP
            ]
            corrections = correct_chunk(client, system_prompt, chunk, context_before, usage)
            for c in corrections:
                changed_by_idx[c["idx"]] = (c["text"], c["uncertain"])
            if console:
                console.print(
                    f"  chunk {start // CHUNK_SIZE + 1}: {len(chunk)} sent, "
                    f"{len(corrections)} changed"
                )

        # fill results + write cache (idx maps back to id via this run's
        # own snapshot, so concurrent structure edits can't shift rows)
        with get_session() as session:
            for d in todo:
                if d["idx"] in changed_by_idx:
                    text, unc = changed_by_idx[d["idx"]]
                    changed = text != d["base_text"]
                else:
                    text, unc, changed = d["base_text"], False, False
                results[d["id"]] = (text, unc)
                session.add(
                    LlmCache(
                        kind="correct",
                        source_hash=d["hash"],
                        text=text,
                        changed=changed,
                        uncertain=unc,
                    )
                )
            session.commit()

    if console and (usage["input"] or usage["output"]):
        # sonnet-5 intro pricing: $2/M input, $10/M output (cache read $0.2/M)
        cost = (
            usage["input"] * 2 + usage["cached"] * 0.2 + usage["output"] * 10
        ) / 1_000_000
        console.print(
            f"  tokens: in {usage['input']:,} (+{usage['cached']:,} cached) / "
            f"out {usage['output']:,}  ~ ${cost:.3f}"
        )

    # ---- persist by id (segments deleted mid-run are skipped safely)
    n_changed = 0
    with get_session() as session:
        for seg_id, (text, uncertain) in results.items():
            seg = session.get(Segment, seg_id)
            if seg is None:
                continue
            seg.text_llm = text
            seg.llm_uncertain = uncertain
            if text.strip() != seg.text_whisper.strip():
                n_changed += 1
            session.add(seg)
        session.commit()

    return n_changed
