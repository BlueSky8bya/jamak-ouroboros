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
# [WH-CHANGE v0.9.57 | FEAT | 2026-07-17 | CHG-20260717-085]
# Reason: ADR-0011 1층. 사전에 있는 용어인데도 STT가 띄어쓰기를 흔들어 놓으면
#   (무유지등야 → "오도무유지 등야") 2층(漢 채우기)의 단어 경계 정규식이 못
#   잡는다. 실패 원인이 "사전에 없음"만이 아니라는 것 — 사용자 지적. 병기는
#   결정적 치환이라 API가 필요 없고, API가 필요한 건 "이게 그 용어인가" 판단뿐
#   → 1층(맞춤법)이 표기를 정규화하고 2층이 그 결과를 공짜로 채운다.
# Related: ADR-0011, CHANGELOG CHG-20260717-085.
PROMPT_VERSION = "v4"  # bump to invalidate the spell cache (v4: 고유어 분절 정규화)

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
        },
        # [WH-CHANGE v0.9.95 | FEAT | 2026-07-17 | CHG-20260717-135]
        # Reason: ADR-0015 — 병기 후보 기록. 텍스트는 안 바꾸고(fixes와 별개),
        #   이 줄 문맥에서 강조 한자로 병기하면 좋을 낱말만 (idx, 음, 한자)로
        #   남긴다. 漢 채우기가 이걸 참고해 API 없이 문맥 병기한다.
        # Related: ADR-0015, CHANGELOG CHG-20260717-135.
        "hanja": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "reading": {"type": "string"},
                    "hanja": {"type": "string"},
                    # [WH-CHANGE v0.9.98 | FEAT | 2026-07-18 | CHG-20260718-138]
                    # Reason: ADR-0016 P2 — 사전 밖 발굴. discovered=true면 목록에
                    #   없던 한자어를 API가 발굴한 것(hanja=최상위 추천, alt=대안).
                    #   자동 병기 안 하고 관리자 검증 대상. false면 목록 매칭(확정).
                    # Related: ADR-0016, CHANGELOG CHG-20260718-138.
                    "discovered": {"type": "boolean"},
                    "alt": {"type": "array", "items": {"type": "string"}},
                    # 단일자 발굴은 동음 구분용 뜻(訓) — 등록 시 (뜻,음)→한자 키.
                    # 다자어는 빈 문자열.
                    "gloss": {"type": "string"},
                },
                "required": ["idx", "reading", "hanja", "discovered"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["fixes", "hanja"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 한국어 자막의 맞춤법 검사기입니다. 입력은 검수가 끝난 강연 자막 줄 목록입니다.

작업 규칙:
1. 명백한 맞춤법 오류, 띄어쓰기 오류, 오타만 고친다.
2. **구어체, 사투리, 반복, 감탄사는 절대 고치지 않는다.** 이것은 발화 그대로를 담는 자막이다. 표준어로 다듬거나 문장을 매끄럽게 만들지 않는다.
2-1. **화자는 경상도(진주) 출신이라 경상도 사투리가 발화 그대로다. 사투리 어미는 오타가 아니다.** 예: '부족해가'를 '부족해서'로, '있어가'를 '있어서'로, '했어예'를 '했어요'로 바꾸지 않는다. '-해가/-어가/-가꼬/-아이가/-니더/-데이' 같은 어미는 그대로 둔다.
3. 단어를 바꾸거나 내용을 더하거나 빼지 않는다. 문장 부호 취향 교정도 하지 않는다.
4. 고유명사·종교/한자 용어는 철자가 명백히 틀린 경우가 아니면 건드리지 않는다.
5. **고칠 것이 있는 줄만 fixes에 포함한다.** 이상 없는 줄은 응답에 포함하지 않는다.
6. 확신이 없으면 고치지 않는다. 과잉 교정보다 미교정이 낫다.
7. **아래 '이 강연의 고유 용어'는 정확한 표기다. 이 단어들을 다른 말로 바꾸거나 숫자로 정규화하지 않는다.** 특히 등급·단위를 나타내는 숫자+용어 표기(예: '5백궁'은 백궁의 5등급 — '500궁'으로 바꾸지 말 것, '백궁'을 '100궁'으로 바꾸지 말 것, '레벨 700무'의 '무'를 지우지 말 것)를 임의로 고치지 않는다.
8. **고유 용어가 음성인식 때문에 끊기거나 붙은 것은 원래 표기로 되돌린다.** 아래 목록에 있는 용어가 중간에 띄어쓰기로 쪼개졌으면(예: '오도무유지 등야' → '오도무유지등야', '일시 무시일' → '일시무시일') 목록의 표기대로 붙여 쓴다. 반대로 두 용어가 붙어버렸으면 띄어 쓴다. **목록에 있는 용어에만 적용한다** — 목록에 없는 말의 띄어쓰기는 규칙 1의 일반 맞춤법으로만 다룬다.
9. **이미 병기된 한자는 그대로 둔다.** '해탈(解脫)'처럼 괄호 안에 한자가 붙어 있으면 괄호와 한자를 지우거나 바꾸지 않는다.
10. **[한자 병기 후보 — 텍스트는 절대 바꾸지 않는다]** 이 줄에 한자를 병기하면 좋을 낱말이 있으면, 텍스트는 그대로 두고 `hanja`에만 기록한다. 두 경로가 있다:
  **(a) 목록 매칭** — 아래 '강조 한자어' 목록의 낱말이 이 줄에 **바로 그 뜻으로** 쓰였으면 `{idx, reading, hanja, discovered:false}`. reading·hanja는 목록 그대로. 같은 소리 다른 뜻이면(‘탐험’의 ‘탐’은 貪 아님) 기록 안 함.
  **(b) 발굴** — 목록에 **없어도**, 이 강연에서 **흑판에 적어 강조하거나 한자로 적어야 뜻이 사는 한자어**(불교·교리·고사성어·전문 한자어)라고 판단되면 `{idx, reading, hanja, discovered:true, alt:[다른 후보…], gloss:"뜻"}`. hanja는 문맥상 가장 맞는 표준 한자, alt는 동음 대안(없으면 빈 배열), **gloss는 한 글자 한자어일 때 그 뜻(訓)**(예: 貪이면 "탐할"; 두 글자 이상이면 빈 문자열). **관리자가 검증할 후보다** — 확실하지 않아도 후보로 남길 수 있으나, 아래를 지킨다:
    - **일상어·순우리말·고유명사는 발굴하지 않는다.** ‘사랑’·‘마음’ 같은 흔한 말, 사람·지명·단체명 제외.
    - **한 줄에 최대 2개.** 남발 금지. 애매하면 발굴 안 함(과잉보다 미발굴).
    - 환각 금지 — 실재하지 않는 한자를 지어내지 않는다. 모르면 발굴 안 함.
  **공통**: `fixes`(텍스트)는 어느 경로든 절대 바꾸지 않는다. 괄호 병기를 넣지 않는다. `hanja`는 오직 기록이다."""


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
    # 규칙 10용 병기 후보 목록: gloss 있는 special 단일자만(貪·嗔·癡 등). 이것이
    # 사전만으론 문맥을 몰라 못 채우던 낱말이다. 목록이 바뀌면 프롬프트가 바뀌어
    # (system_prompt가 캐시 salt) 자동 재검사된다. (ADR-0015)
    emph = _emphasis_hanja_block()
    if emph:
        parts.append(f"\n[강조 한자어 — 위 규칙 10 적용]\n{emph}")
    if len(parts) == 1:
        return SYSTEM_PROMPT
    return "".join(parts)


# 힌트 목록에 넣을 최소 등장 횟수. 자동 채굴은 1글자 낱말을 잘못 잘라 앞 문맥
# 조각을 gloss로 오인한 쓰레기를 다수 만든다(gloss "한 미"·"자기 처"·"전부 사").
# 이런 오검은 대부분 count=2(한 번 채굴)다. 진짜 강조어는 여러 번 병기돼 count가
# 높다(貪99·心18·辰14·女10·王8·高6). 하한으로 걸러 프롬프트를 강조어로 좁힌다 —
# gloss 형태로 완벽 분류가 불가능해(부사·대명사 무한 변형) count 신호가 더 견고.
# count<하한의 진짜 강조어는 다음 검수에서 재채굴돼 count가 오르면 자동 포함된다
# (우로보로스 — 손실이 아니라 지연). tier 강등(ADR-0016 청소)과 이중 방어.
MIN_HINT_COUNT = 4


def _emphasis_hanja_block(max_terms: int = 200) -> str:
    """규칙 10 병기 후보 목록: `한자(뜻 음)` 줄들. gloss 있는 special 단일자 중
    count >= MIN_HINT_COUNT (자주 병기된 진짜 강조어)만.

    다자어는 fill_hanja가 단어 경계로 이미 잘 잡으므로 뺀다 — 문맥 판단이
    필요한 건 동음 많은 단일자다(사용자 결정: 오병기 최소).
    """
    from ..db import HanjaTerm, get_session

    with get_session() as session:
        rows = session.exec(
            select(HanjaTerm).where(HanjaTerm.tier == "special")
        ).all()
    seen: set[tuple[str, str]] = set()
    lines: list[str] = []
    for t in sorted(rows, key=lambda r: -r.count):  # 자주 병기된 것 우선
        if not t.gloss or len(t.reading) != 1 or t.count < MIN_HINT_COUNT:
            continue  # 단일자 + 뜻 + 충분히 병기된 것만
        key = (t.reading, t.hanja)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{t.hanja}({t.gloss} {t.reading})")
        if len(lines) >= max_terms:
            break
    return ", ".join(lines)


def _hash(text: str, salt: str = "") -> str:
    return hashlib.sha256(
        f"{PROMPT_VERSION}\x1f{salt}\x1f{text}".encode("utf-8")
    ).hexdigest()[:20]


def spellcheck_lines(
    lines: list[tuple[int, str]], limit: int = 0
) -> tuple[dict[int, str], dict[int, list[dict]], dict]:
    """Check (key, text) lines; return ({key: fixed_text} for changed lines,
    {key: [hanja hint]} for lines with 병기 후보, stats). Keys are opaque to
    this function (the caller passes segment ids). Cached per exact text —
    unchanged lines from a previous run cost nothing (hints restored too).

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
    hints: dict[int, list[dict]] = {}  # {key: [{"reading","hanja"}]} (ADR-0015)
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
                if cached.hanja:
                    try:
                        h = json.loads(cached.hanja)
                        if h:
                            hints[key] = h
                    except Exception:
                        pass
            else:
                todo.append((key, t))

    if limit and len(todo) > limit:
        stats["remaining"] = len(todo) - limit
        todo = todo[:limit]

    if not todo:
        return fixes, hints, stats

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
            parsed = json.loads(text_block)
            fixed_by_pos = {f["idx"]: f["text"] for f in parsed["fixes"]}
            # 병기 후보를 위치별로 모은다 (idx는 청크 내 위치).
            # (a) 목록 매칭 {reading, hanja} + (b) 발굴 {reading, hanja, discovered, alt}
            hanja_by_pos: dict[int, list[dict]] = {}
            for h in parsed.get("hanja", []):
                r, hz = (h.get("reading") or "").strip(), (h.get("hanja") or "").strip()
                if not (r and hz):
                    continue
                item = {"reading": r, "hanja": hz}
                if h.get("discovered"):
                    item["discovered"] = True
                    alt = [a.strip() for a in (h.get("alt") or []) if a and a.strip()]
                    if alt:
                        item["alt"] = alt
                    g = (h.get("gloss") or "").strip()
                    if g:
                        item["gloss"] = g
                hanja_by_pos.setdefault(h["idx"], []).append(item)
            for pos, (key, t) in enumerate(chunk):
                fixed = fixed_by_pos.get(pos)
                changed = bool(fixed and fixed.strip() and fixed.strip() != t)
                if changed:
                    fixes[key] = fixed.strip()
                cell_hints = hanja_by_pos.get(pos, [])
                if cell_hints:
                    hints[key] = cell_hints
                cache_key = _hash(t, gloss_salt)
                if cache_key in written:
                    continue
                written.add(cache_key)
                session.add(
                    LlmCache(
                        kind="spell",
                        source_hash=cache_key,
                        text=fixes.get(key, ""),
                        changed=changed,
                        hanja=json.dumps(cell_hints, ensure_ascii=False)
                        if cell_hints
                        else "",
                    )
                )
        session.commit()

    return fixes, hints, stats
