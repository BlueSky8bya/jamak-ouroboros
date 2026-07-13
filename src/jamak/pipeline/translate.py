"""Stage 6 (optional) — Translate: Korean subtitles -> target language.

Context-aware translation via Claude: chunks carry surrounding lines so
pronouns, religious terms, and running jokes stay coherent. Results are
cached per (segment, lang, source-text hash), so re-export is free and
editing the Korean invalidates only the touched segments.
"""

from __future__ import annotations

import hashlib
import json

from sqlmodel import or_, select

from ..config import TRANSLATE_MODEL
from ..db import Segment, Translation, get_session

# display order = rough global usage order (user-facing list)
# English labels here are the translation TARGET names given to the model.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "ja": "Japanese (日本語)",
    "zh-Hans": "Simplified Chinese (简体中文)",
    "zh-Hant": "Traditional Chinese (繁體中文)",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "it": "Italian (Italiano)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
}

# short Korean names for the UI (badges, dropdowns)
LANG_KO: dict[str, str] = {
    "ko": "한국어",
    "en": "영어",
    "ja": "일본어",
    "zh-Hans": "중국어(간체)",
    "zh-Hant": "중국어(번체)",
    "es": "스페인어",
    "fr": "프랑스어",
    "it": "이탈리아어",
    "de": "독일어",
    "pt": "포르투갈어",
    "ru": "러시아어",
}

CHUNK_SIZE = 60
CONTEXT_OVERLAP = 4

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
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
    "required": ["translations"],
    "additionalProperties": False,
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def translation_examples(lang: str, max_pairs: int = 14) -> list[tuple[str, str]]:
    """Human-reviewed/edited (Korean, translation) pairs for this language.

    Cross-video: as reviewers confirm translations, these become few-shot
    examples that teach terminology and tone to future translations —
    the same ouroboros loop the Korean correction stage uses.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    with get_session() as session:
        # non-forked tracks: the reviewed/edited Translation rows joined to ko
        rows = session.exec(
            select(Translation, Segment)
            .join(Segment, Translation.segment_id == Segment.id)
            .where(
                Translation.lang == lang,
                or_(Translation.reviewed == True, Translation.edited == True),  # noqa: E712
            )
        ).all()
        for t, seg in rows:
            ko = (seg.text_final or seg.text_llm or seg.text_whisper).strip()
            tx = t.text.strip()
            if ko and tx and ko not in seen:
                seen.add(ko)
                out.append((ko, tx))

        # forked tracks: after a fork the Translation rows are deleted and the
        # reviewed translation lives in Segment.text_final (lang != "ko"). Match
        # each to its Korean source by time overlap (idx diverges after a fork).
        forked = session.exec(
            select(Segment).where(
                Segment.lang == lang, Segment.reviewed == True  # noqa: E712
            )
        ).all()
        if forked:
            ko_by_job: dict[int, list[Segment]] = {}
            for k in session.exec(
                select(Segment).where(
                    Segment.job_id.in_({s.job_id for s in forked}),
                    Segment.lang == "ko",
                )
            ).all():
                ko_by_job.setdefault(k.job_id, []).append(k)
            for fs in forked:
                tx = (fs.text_final or "").strip()
                if not tx:
                    continue
                fs_dur = max(0.001, fs.end - fs.start)
                overlaps = [
                    k
                    for k in ko_by_job.get(fs.job_id, [])
                    if k.start < fs.end and k.end > fs.start
                ]
                # only emit a near-1:1 pair. After a real fork the track is
                # re-split, so one forked cue may span 2-3 ko cues; concatenating
                # them would teach the model a wrong many-to-one alignment. Accept
                # exactly one overlap, or a single ko cue that dominates (>=80% of
                # the forked cue's span); otherwise skip (quality over quantity).
                if len(overlaps) == 1:
                    k = overlaps[0]
                elif overlaps:
                    dominant = max(
                        overlaps,
                        key=lambda k: min(k.end, fs.end) - max(k.start, fs.start),
                    )
                    cover = (
                        min(dominant.end, fs.end) - max(dominant.start, fs.start)
                    ) / fs_dur
                    k = dominant if cover >= 0.8 else None
                else:
                    k = None
                if k is None:
                    continue
                ko = (k.text_final or k.text_llm or k.text_whisper).strip()
                if ko and ko not in seen:
                    seen.add(ko)
                    out.append((ko, tx))

    # Selection: the loop exists to propagate consistent per-language spelling
    # of domain terms (허경영, 하늘궁, 축지법…), which live in LONGER sentences —
    # so shortest-first truncation would drop exactly those. Prioritise pairs
    # whose Korean carries an approved glossary term, then fill the remainder
    # with a length-STRATIFIED sample (not shortest-only) for tone/length variety.
    from ..glossary import glossary_surface_forms

    forms = glossary_surface_forms()

    def has_term(ko: str) -> bool:
        return any(f in ko for f in forms)

    term_pairs = [p for p in out if has_term(p[0])]
    other = sorted((p for p in out if not has_term(p[0])), key=lambda p: len(p[0]))

    selected = term_pairs[:max_pairs]
    if len(selected) < max_pairs and other:
        remainder = max_pairs - len(selected)
        step = max(1, len(other) // remainder)  # spread across short..long
        selected += other[::step][:remainder]
    return selected[:max_pairs]


def _system_prompt(lang: str) -> str:
    parts = [
        f"당신은 한국어 강연 자막을 {LANGUAGES[lang]}(으)로 옮기는 전문 자막 번역가입니다.",
        "",
        "번역 대상: 허경영 강연 (구어체, 종교/철학 주제, 청중과의 문답 포함).",
        "",
        "규칙:",
        "1. 문맥에 맞게 자연스럽게 번역한다. 직역보다 강연의 말맛과 의미 전달 우선.",
        "2. 자막이다 — 각 세그먼트는 화면 표시 시간에 맞춰 읽을 수 있어야 한다. 세그먼트마다 권장 글자수(≤N자)를 함께 주니 그 안에서 간결히 옮겨라. 넘칠 것 같으면 군더더기를 줄이고, 정 길면 짧은 두 줄로 나눠도 좋다 (내용 삭제는 금지). 권장 글자수가 매우 작으면(≤12자) 의미 핵심만 남긴 최단 표현을 택한다 (예: \"뭐라고?\"→\"What?\", \"혹시 아는가?\"→\"Know it?\"). 원문이 짧은데 대상 언어가 길어지는 경우 정중한 군말(please, happen to, do you 등)을 먼저 버린다.",
        "3. 고유명사(허경영, 하늘궁 등)는 표준 로마자/현지 표기로 일관되게 옮기고,",
        "   처음 등장 시 필요하면 짧은 의미 병기를 허용한다.",
        "4. 성경/불교/유교 용어는 해당 언어권의 통용 표현을 쓴다 (예: 에스더 → Esther).",
        "5. 존댓말/구어 어투는 대상 언어의 자연스러운 강연체로.",
        "6. 모든 세그먼트를 translations에 포함한다. idx는 입력 그대로.",
        "7. 내용을 창작하거나 요약하지 않는다.",
    ]
    examples = translation_examples(lang)
    if examples:
        parts += [
            "",
            "## 과거 검수에서 사람이 확정한 번역 (용어·표기·어투를 이대로 따를 것)",
        ]
        for ko, tx in examples:
            parts.append(f'- "{ko}" → "{tx}"')
    return "\n".join(parts)


def translate_texts(
    items: list[tuple[int, str, int]], lang: str, console=None
) -> dict[int, str]:
    """[(idx, korean, char_budget)] -> {idx: translated}. One Claude call per chunk."""
    import anthropic

    if lang not in LANGUAGES:
        raise ValueError(f"unsupported language: {lang}")

    client = anthropic.Anthropic()
    system_prompt = _system_prompt(lang)
    out: dict[int, str] = {}
    usage = {"input": 0, "cached": 0, "output": 0}

    for start in range(0, len(items), CHUNK_SIZE):
        chunk = items[start : start + CHUNK_SIZE]
        context = items[max(0, start - CONTEXT_OVERLAP) : start]
        lines = []
        if context:
            lines.append("### 직전 문맥 (번역 대상 아님):")
            lines.extend(f"  {t}" for _, t, _b in context)
            lines.append("")
        lines.append("### 번역 대상 세그먼트 (idx, 권장 최대 글자수, 원문):")
        lines.extend(f"[{i}] (≤{b}자) {t}" for i, t, b in chunk)

        response = client.messages.create(
            model=TRANSLATE_MODEL,
            max_tokens=16000,
            thinking={"type": "disabled"},  # mechanical task, see correct.py
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
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
        for t in json.loads(text)["translations"]:
            out[t["idx"]] = t["text"]
        if console:
            console.print(f"  {lang} chunk {start // CHUNK_SIZE + 1}: {len(chunk)}")

    if console and (usage["input"] or usage["output"]):
        cost = (usage["input"] * 2 + usage["cached"] * 0.2 + usage["output"] * 10) / 1_000_000
        console.print(
            f"  {lang} tokens: in {usage['input']:,} (+{usage['cached']:,} cached) / "
            f"out {usage['output']:,}  ~ ${cost:.3f}"
        )

    return out


def retranslate_span(
    items: list[tuple[int, str, int]],
    context_before: list[str],
    context_after: list[str],
    lang: str,
) -> dict[int, str]:
    """Re-translate a small CONTIGUOUS run of cues with context on both sides.

    Used by the editor's "다시 번역": after the reviewer re-splits/retimes the
    Korean, a cluster of neighbouring cues ends up stale or empty — translating
    them together (one Claude call) keeps the sentence flow coherent across the
    new cue boundaries, which per-cue re-translation can't do.

    items: [(key, korean, char_budget)] in track order (keys are opaque —
    the caller passes segment ids). Returns {key: translated}.
    """
    import anthropic

    if lang not in LANGUAGES:
        raise ValueError(f"unsupported language: {lang}")
    items = [(k, t.strip(), b) for k, t, b in items if t.strip()]
    if not items:
        return {}

    client = anthropic.Anthropic()
    lines: list[str] = []
    if context_before:
        lines.append("### 앞 문맥 (번역 대상 아님):")
        lines.extend(f"  {t}" for t in context_before if t.strip())
        lines.append("")
    lines.append("### 번역 대상 세그먼트 (idx, 권장 최대 글자수, 원문):")
    lines.extend(f"[{i}] (≤{b}자) {t}" for i, (_, t, b) in enumerate(items))
    if context_after:
        lines.append("")
        lines.append("### 뒤 문맥 (번역 대상 아님):")
        lines.extend(f"  {t}" for t in context_after if t.strip())

    response = client.messages.create(
        model=TRANSLATE_MODEL,
        max_tokens=4000,
        thinking={"type": "disabled"},
        system=[
            {
                "type": "text",
                "text": _system_prompt(lang),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    by_pos = {t["idx"]: t["text"] for t in json.loads(text)["translations"]}
    return {
        key: by_pos[i].strip()
        for i, (key, _, _) in enumerate(items)
        if by_pos.get(i, "").strip()
    }


def translate_segments(seg_dicts: list[dict], text_key: str, lang: str, console=None) -> dict[int, str]:
    """Translate segments (given stage text) with per-segment cache.

    Returns {segment_id: translated_text}.
    """
    sources = {
        d["id"]: (d.get(text_key) or "").strip() for d in seg_dicts if (d.get(text_key) or "").strip()
    }
    # per-cue readable char budget (~17 chars/sec of on-screen time), so the
    # model keeps a translation that inherits the Korean timing readable
    dur = {d["id"]: max(0.5, float(d.get("end", 0)) - float(d.get("start", 0))) for d in seg_dicts}

    result: dict[int, str] = {}
    todo: list[tuple[int, str]] = []

    with get_session() as session:
        for seg_id, text in sources.items():
            h = _hash(text)
            existing = session.exec(
                select(Translation).where(
                    Translation.segment_id == seg_id, Translation.lang == lang
                )
            ).all()
            # Only EDITED (human-authored) text is a hard lock, never re-translated.
            # `reviewed` means "a human confirmed the translation of THIS Korean
            # text" — it is not a permanent lock: if the Korean later changes, the
            # confirmation is stale and the row must fall through to the source_hash
            # check below and re-translate (per the module/schema docstrings). An
            # empty row is never protected (would export blank and never refill).
            protected = next(
                (t for t in existing if t.edited and t.text.strip()),
                None,
            )
            # a reviewed row whose hash still matches the current Korean is fresh
            # and kept; a reviewed row whose Korean changed is NOT fresh -> todo.
            fresh = next(
                (t for t in existing if t.source_hash == h and t.text.strip()), None
            )
            if protected is not None:
                result[seg_id] = protected.text
            elif fresh is not None:
                result[seg_id] = fresh.text
            else:
                todo.append((seg_id, text))

    if todo:
        budgeted = [
            (sid, txt, max(10, int(17 * dur.get(sid, 3.0)))) for sid, txt in todo
        ]
        translated = translate_texts(budgeted, lang, console=console)
        missing = [sid for sid, _ in todo if sid not in translated]
        if missing:
            # the model dropped these idx from its JSON output. Fall back to the
            # Korean source so the cue is never a silent blank in the .srt, and
            # do NOT cache it (source_hash unwritten) so a later export retries.
            if console:
                console.print(
                    f"  {lang}: {len(missing)} segment(s) dropped by model — "
                    "using Korean source as fallback (will retry on re-export)"
                )
            for sid in missing:
                result[sid] = sources.get(sid, "")
        with get_session() as session:
            for seg_id, text in todo:
                if seg_id not in translated:
                    continue
                # replace stale cache rows for this segment+lang. Only EDITED
                # rows are kept (hard lock); a stale reviewed row is deleted and
                # replaced with the fresh translation (its confirmation was for
                # the OLD Korean, now superseded).
                for old in session.exec(
                    select(Translation).where(
                        Translation.segment_id == seg_id, Translation.lang == lang
                    )
                ).all():
                    if old.edited:
                        continue
                    session.delete(old)
                session.add(
                    Translation(
                        segment_id=seg_id,
                        lang=lang,
                        text=translated[seg_id],
                        source_hash=_hash(text),
                    )
                )
                result[seg_id] = translated[seg_id]
            session.commit()

    return result
