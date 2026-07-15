"""Korean spelling/spacing check over finished subtitle text (ADR-0009 follow-up).

Runs AFTER human review, before export: the pipeline's correction stage already
fixes the machine draft, so what's left for this pass are typos the reviewer
introduced while typing. Suggestions only — nothing is applied here; the web UI
shows a diff list and the reviewer picks what to accept.

Cost shape mirrors correct.py: results are cached in LlmCache (kind="spell")
keyed by the exact text, so re-checking a video re-bills only edited lines.
No reliable local Korean spellchecker library exists (the public checkers are
web-scraping wrappers that break often and sit in a ToS gray zone), so this
uses the Claude API the project already depends on.
"""

from __future__ import annotations

import hashlib
import json

from sqlmodel import select

from ..config import SPELL_MODEL
from ..db import LlmCache, get_session

CHUNK_SIZE = 80  # subtitle lines per request (short lines — bigger chunks ok)
PROMPT_VERSION = "v2"  # bump to invalidate the spell cache (v2: glossary + 숫자형 보호)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["idx", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["fixes"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 한국어 자막의 맞춤법 검사기입니다. 입력은 검수가 끝난 강연 자막 줄 목록입니다.

작업 규칙:
1. 명백한 맞춤법 오류, 띄어쓰기 오류, 오타만 고친다.
2. **구어체, 사투리, 반복, 감탄사는 절대 고치지 않는다.** 이것은 발화 그대로를 담는 자막이다. 표준어로 다듬거나 문장을 매끄럽게 만들지 않는다.
3. 단어를 바꾸거나 내용을 더하거나 빼지 않는다. 문장 부호 취향 교정도 하지 않는다.
4. 고유명사·종교/한자 용어는 철자가 명백히 틀린 경우가 아니면 건드리지 않는다.
5. **고칠 것이 있는 줄만 fixes에 포함한다.** 이상 없는 줄은 응답에 포함하지 않는다.
6. 확신이 없으면 고치지 않는다. 과잉 교정보다 미교정이 낫다.
7. **아래 '이 강연의 고유 용어'는 정확한 표기다. 이 단어들을 다른 말로 바꾸거나 숫자로 정규화하지 않는다.** 특히 등급·단위를 나타내는 숫자+용어 표기(예: '5백궁'은 백궁의 5등급 — '500궁'으로 바꾸지 말 것, '백궁'을 '100궁'으로 바꾸지 말 것, '레벨 700무'의 '무'를 지우지 말 것)를 임의로 고치지 않는다."""


def _domain_block(max_terms: int = 250) -> str:
    """Approved glossary terms as a protected-vocabulary block for the prompt.

    [WH-CHANGE v0.9.30 | FEAT | 2026-07-16 | CHG-20260716-052]
    Reason: 맞춤법기가 강연 고유어를 일반어로 오교정하는 문제 — 특히 '5백궁'을
      '500궁'으로 정규화(사용자 실제 목격). glossary 승인 용어를 프롬프트에
      주입해 보호한다. correct.py는 이미 glossary_block을 쓰지만 spellcheck는
      안 썼다. 변형(오인식 예)도 함께 넣어 잘못된 형태를 바른 형태로 돌린다.
    Related: CHANGELOG CHG-20260716-052.
    """
    from ..glossary import glossary_block, hanja_domain_readings

    # glossary가 429종으로 커져 250 상한으론 잘림 — 보호는 넉넉히 (프롬프트는
    # 청크 간 ephemeral 캐시되어 첫 청크만 비용)
    block = glossary_block(max_terms=max(max_terms, 500))
    # 검증된 흑판 한자어도 고유 용어 — 맞춤법이 일반어로 바꾸지 않게 함께 보호
    # (v0.9.34: glossary와 한자 사전이 갈라져 특수어 412종이 새던 문제)
    hanja = hanja_domain_readings()
    parts = [SYSTEM_PROMPT]
    if block:
        parts.append(f"\n[이 강연의 고유 용어 — 위 규칙 7 적용]\n{block}")
    if hanja:
        parts.append(f"\n[강연 한자어 (표기 유지)]\n{', '.join(hanja)}")
    if len(parts) == 1:
        return SYSTEM_PROMPT
    return "".join(parts)


def _hash(text: str, salt: str = "") -> str:
    return hashlib.sha256(
        f"{PROMPT_VERSION}\x1f{salt}\x1f{text}".encode("utf-8")
    ).hexdigest()[:20]


def spellcheck_lines(
    lines: list[tuple[int, str]], limit: int = 0
) -> tuple[dict[int, str], dict]:
    """Check (key, text) lines; return ({key: fixed_text} for changed lines,
    stats). Keys are opaque to this function (the caller passes segment ids).
    Cached per exact text — unchanged lines from a previous run cost nothing.

    [WH-CHANGE v0.9.25 | FIX | 2026-07-15 | CHG-20260715-046]
    Reason: 2시간 영상은 미캐시 2천여 줄 = 청크 ~28개를 한 요청에 처리 —
      진행률이 안 보이고(사용자 요청) 프록시 타임아웃 위험(번역 502와 동일
      패턴). `limit` > 0이면 미캐시 줄을 그 수까지만 API로 처리하고 나머지는
      stats["remaining"]으로 알린다 — 프론트가 짧은 요청을 반복하며 진행률
      표시. 캐시 조회는 항상 전체(무료).
    Related: CHANGELOG CHG-20260715-046.
    """
    stats = {"checked": 0, "cached": 0, "sent": 0, "remaining": 0}
    fixes: dict[int, str] = {}
    todo: list[tuple[int, str]] = []

    # glossary content is part of the prompt → part of the cache key, so editing
    # the glossary re-checks lines instead of serving stale pre-glossary fixes
    system_prompt = _domain_block()
    gloss_salt = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:8]

    with get_session() as session:
        for key, text in lines:
            t = text.strip()
            if not t:
                continue
            stats["checked"] += 1
            cached = session.exec(
                select(LlmCache).where(
                    LlmCache.kind == "spell",
                    LlmCache.source_hash == _hash(t, gloss_salt),
                )
            ).first()
            if cached is not None:
                stats["cached"] += 1
                if cached.changed and cached.text.strip() != t:
                    fixes[key] = cached.text
            else:
                todo.append((key, t))

    if limit and len(todo) > limit:
        stats["remaining"] = len(todo) - limit
        todo = todo[:limit]

    if not todo:
        return fixes, stats

    import anthropic

    client = anthropic.Anthropic()
    stats["sent"] = len(todo)

    with get_session() as session:
        written: set[str] = set()
        for start in range(0, len(todo), CHUNK_SIZE):
            chunk = todo[start : start + CHUNK_SIZE]
            body = "\n".join(f"[{i}] {t}" for i, (_, t) in enumerate(chunk))
            response = client.messages.create(
                model=SPELL_MODEL,
                max_tokens=16000,
                # mechanical proofreading — thinking would add cost, not quality
                thinking={"type": "disabled"},
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},  # stable across chunks
                    }
                ],
                output_config={
                    "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
                },
                messages=[{"role": "user", "content": body}],
            )
            text_block = next(b.text for b in response.content if b.type == "text")
            fixed_by_pos = {
                f["idx"]: f["text"] for f in json.loads(text_block)["fixes"]
            }
            for pos, (key, t) in enumerate(chunk):
                fixed = fixed_by_pos.get(pos)
                changed = bool(fixed and fixed.strip() and fixed.strip() != t)
                if changed:
                    fixes[key] = fixed.strip()
                h = _hash(t, gloss_salt)
                if h in written:
                    continue
                written.add(h)
                session.add(
                    LlmCache(
                        kind="spell",
                        source_hash=h,
                        text=fixes.get(key, ""),
                        changed=changed,
                    )
                )
        session.commit()

    return fixes, stats
