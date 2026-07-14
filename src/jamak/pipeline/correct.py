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
from ..glossary import fewshot_corrections, glossary_block, glossary_surface_forms
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
        # [WH-CHANGE v0.6.2 | FIX | 2026-07-14 | CHG-20260714-012]
        # Reason: CER 분석에서 교정이 이웃 세그먼트의 문장을 현재 큐에 이어붙여
        #   길이를 늘리는 사례 다수 (자막이 실제 발화 구간을 벗어남 → 검수자가
        #   도로 잘라내야 함). 문맥은 판단 근거로만 쓰게 명시.
        # Related: CHANGELOG CHG-20260714-012.
        "9. 각 세그먼트의 text는 그 세그먼트에서 들린 말만 담는다. 앞뒤 세그먼트의 "
        "문장을 끌어와 늘리지 않는다 (문맥은 판단 근거일 뿐, 복사 재료가 아님).",
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


def _needs_llm(d: dict, surface_forms: set[str]) -> bool:
    """Does this segment plausibly need Claude, or would the LLM no-op it?

    The correction prompt only ever *changes* misrecognized words and returns
    changed segments only (rule 6). So a segment with no misrecognition risk is
    pure wasted spend. Skip when:
      - the whisper text is empty (gap/noise) — nothing to correct; the
        YouTube-seeded working text stays as-is;
      - whisper and YouTube agree (not flagged) AND the segment carries no
        domain vocabulary — two independent engines concurring on ordinary
        words is high-confidence, and there's no glossary term to mis-hear.
    Everything else (disagreement, or any domain term/variant present) still
    goes to the LLM, so correction quality is unchanged where it matters.
    """
    base = d["base_text"].strip()
    if not base:
        return False
    if d["flagged"]:
        return True
    hay = base + " " + (d["text_youtube"] or "")
    return any(form in hay for form in surface_forms)


def _normalize_ko(text: str) -> str:
    import re

    return re.sub(r"[^\w가-힣]", "", text or "")


def _words_ko(text: str) -> list[str]:
    import re

    return [
        w
        for w in (re.sub(r"[^\w가-힣]", "", p) for p in (text or "").split())
        if w
    ]


def _contig_sublist(short: list[str], long: list[str]) -> bool:
    """`short`가 `long` 안에 연속된 단어열로 들어 있는가."""
    n = len(short)
    if not n or n > len(long):
        return False
    return any(long[i : i + n] == short for i in range(len(long) - n + 1))


def clamp_neighbor_extensions(
    ordered: list[dict], results: dict[int, tuple[str, bool]]
) -> int:
    """Deterministic rule-9 backstop. Returns #rows clamped.

    [WH-CHANGE v0.8.7 | FIX | 2026-07-15 | CHG-20260715-028]
    Reason: 프롬프트 규칙 9("그 세그먼트에서 들린 말만")에도 불구하고, whisper가
      문장을 중간에서 끊은 행을 LLM이 유튜브 참고 자막의 완전한 문장으로 통째
      교체하는 사례 재발 (이전 행과 중복 자막). 교정 결과 확정 후 결정적으로
      검사한다: 인접 두 행의 교정 텍스트가 포함 관계인데 whisper 원문끼리는
      겹치지 않으면(실제 발화 반복이 아니라 문맥 복사) 더 많이 불어난 쪽을
      whisper 원문(base_text)으로 되돌리고 uncertain=True로 올린다.

    [WH-CHANGE v0.9.19 | FIX | 2026-07-15 | CHG-20260715-040]
    Reason: 이전 판은 글자 substring + 6자 미만 무시였는데, 유튜브 롤링 자막이
      토막말을 누적하며("그런데"→"그런데 이렇게"→"그런데 이렇게 짧게 끊긴 말은")
      3글자 이웃('이렇게')이 6자 가드에 걸려 확장을 통째 놓쳤다 (연습 4). 포함
      판정을 **단어 경계 연속 포함**으로 바꿔 짧은 토막말도 잡되, 우연한 부분
      문자열 겹침(다↔다음)은 단어가 달라 걸리지 않는다. 6자 가드 제거, 대신
      짧은 쪽 단어열이 ≥2글자여야 한다(단음절 감탄사 오탐 방지).
    Related: CHANGELOG CHG-20260715-028, CHG-20260715-040.
    """
    clamped = 0
    rows = [d for d in ordered if d["id"] in results]
    for a, b in zip(rows, rows[1:]):
        wa_words = _words_ko(results[a["id"]][0])
        wb_words = _words_ko(results[b["id"]][0])
        if not wa_words or not wb_words:
            continue
        short_w, long_w = (
            (wa_words, wb_words)
            if len(wa_words) <= len(wb_words)
            else (wb_words, wa_words)
        )
        if not _contig_sublist(short_w, long_w):
            continue
        if len("".join(short_w)) < 2:
            continue  # 단음절(네·아·그) 우연 일치 방지
        wa, wb = _normalize_ko(a["base_text"]), _normalize_ko(b["base_text"])
        if wa and wb and (wa in wb or wb in wa):
            continue  # the speaker really repeated it — leave alone
        # the offender is the row that grew furthest past its own whisper text;
        # gap rows (base_text="") carry legitimately YouTube-seeded text — never
        # clamped.
        na, nb = "".join(wa_words), "".join(wb_words)
        ratio_a = len(na) / max(len(wa), 1) if wa else 0.0
        ratio_b = len(nb) / max(len(wb), 1) if wb else 0.0
        offender = a if ratio_a >= ratio_b else b
        if ratio_a <= 1.2 and ratio_b <= 1.2:
            continue  # neither meaningfully grew — containment is coincidental
        if not _normalize_ko(offender["base_text"]):
            continue
        results[offender["id"]] = (offender["base_text"], True)
        clamped += 1
    return clamped


def correct_job(job_id: int, console=None) -> int:
    """Run correction over every segment of a job. Returns #changed."""
    import anthropic

    prepass_pairs = load_prepass_pairs()

    with get_session() as session:
        # only the Korean source track — correction is ko-only; forked
        # translation tracks (lang != "ko") have their own text (ADR-0006)
        segments = session.exec(
            select(Segment)
            .where(Segment.job_id == job_id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segments]

    # ---- tier 1: free pre-pass from learned pairs
    for d in seg_dicts:
        d["base_text"] = apply_prepass(d["text_whisper"], prepass_pairs)
        d["hash"] = _hash(PROMPT_VERSION, d["base_text"], d["text_youtube"])

    # ---- tier 1.5: skip segments the LLM would leave unchanged (free)
    surface_forms = glossary_surface_forms()

    # ---- tier 2: cache lookup
    # results are keyed by segment id (idx can shift if the user edits
    # structure in the web app while the LLM is running)
    results: dict[int, tuple[str, bool]] = {}  # segment id -> (text, uncertain)
    todo: list[dict] = []
    skipped = 0
    with get_session() as session:
        for d in seg_dicts:
            if not _needs_llm(d, surface_forms):
                # low-risk: trust whisper (post pre-pass), or the YouTube-seeded
                # text for gap segments — no API call
                text = d["base_text"] if d["base_text"].strip() else d["text_youtube"]
                results[d["id"]] = (text, False)
                skipped += 1
                continue
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
        cache_hits = len(seg_dicts) - skipped - len(todo)
        console.print(
            f"  pre-pass pairs: {len(prepass_pairs)} | skipped (low-risk): {skipped} | "
            f"cache hits: {cache_hits} | to LLM: {len(todo)}/{len(seg_dicts)}"
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
            written: set[str] = set()  # one cache row per source_hash per run
            for d in todo:
                if d["idx"] in changed_by_idx:
                    text, unc = changed_by_idx[d["idx"]]
                    changed = text != d["base_text"]
                else:
                    text, unc, changed = d["base_text"], False, False
                results[d["id"]] = (text, unc)
                if d["hash"] in written:
                    continue  # identical source already cached this run — no dup row
                written.add(d["hash"])
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

    # ---- deterministic rule-9 backstop (covers LLM, cache and skip paths)
    n_clamped = clamp_neighbor_extensions(seg_dicts, results)
    if console and n_clamped:
        console.print(f"  neighbor-extension clamp: {n_clamped} row(s) reverted to whisper")

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
