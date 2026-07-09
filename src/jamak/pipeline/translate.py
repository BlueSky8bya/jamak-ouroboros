"""Stage 6 (optional) — Translate: Korean subtitles -> target language.

Context-aware translation via Claude: chunks carry surrounding lines so
pronouns, religious terms, and running jokes stay coherent. Results are
cached per (segment, lang, source-text hash), so re-export is free and
editing the Korean invalidates only the touched segments.
"""

from __future__ import annotations

import hashlib
import json

from sqlmodel import select

from ..config import TRANSLATE_MODEL
from ..db import Translation, get_session

# display order = rough global usage order (user-facing list)
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


def _system_prompt(lang: str) -> str:
    return "\n".join(
        [
            f"당신은 한국어 강연 자막을 {LANGUAGES[lang]}(으)로 옮기는 전문 자막 번역가입니다.",
            "",
            "번역 대상: 허경영 강연 (구어체, 종교/철학 주제, 청중과의 문답 포함).",
            "",
            "규칙:",
            "1. 문맥에 맞게 자연스럽게 번역한다. 직역보다 강연의 말맛과 의미 전달 우선.",
            "2. 자막이다 — 한 세그먼트의 번역이 원문보다 크게 길어지지 않게 간결히.",
            "3. 고유명사(허경영, 하늘궁 등)는 표준 로마자/현지 표기로 일관되게 옮기고,",
            "   처음 등장 시 필요하면 짧은 의미 병기를 허용한다.",
            "4. 성경/불교/유교 용어는 해당 언어권의 통용 표현을 쓴다 (예: 에스더 → Esther).",
            "5. 존댓말/구어 어투는 대상 언어의 자연스러운 강연체로.",
            "6. 모든 세그먼트를 translations에 포함한다. idx는 입력 그대로.",
            "7. 내용을 창작하거나 요약하지 않는다.",
        ]
    )


def translate_texts(
    items: list[tuple[int, str]], lang: str, console=None
) -> dict[int, str]:
    """[(idx, korean)] -> {idx: translated}. One Claude call per chunk."""
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
            lines.extend(f"  {t}" for _, t in context)
            lines.append("")
        lines.append("### 번역 대상 세그먼트:")
        lines.extend(f"[{i}] {t}" for i, t in chunk)

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


def translate_segments(seg_dicts: list[dict], text_key: str, lang: str, console=None) -> dict[int, str]:
    """Translate segments (given stage text) with per-segment cache.

    Returns {segment_id: translated_text}.
    """
    sources = {
        d["id"]: (d.get(text_key) or "").strip() for d in seg_dicts if (d.get(text_key) or "").strip()
    }

    result: dict[int, str] = {}
    todo: list[tuple[int, str]] = []

    with get_session() as session:
        for seg_id, text in sources.items():
            h = _hash(text)
            cached = session.exec(
                select(Translation).where(
                    Translation.segment_id == seg_id,
                    Translation.lang == lang,
                    Translation.source_hash == h,
                )
            ).first()
            if cached:
                result[seg_id] = cached.text
            else:
                todo.append((seg_id, text))

    if todo:
        translated = translate_texts(todo, lang, console=console)
        with get_session() as session:
            for seg_id, text in todo:
                if seg_id not in translated:
                    continue
                # replace any stale cache rows for this segment+lang
                for old in session.exec(
                    select(Translation).where(
                        Translation.segment_id == seg_id, Translation.lang == lang
                    )
                ).all():
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
