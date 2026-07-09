"""Review web app — FastAPI backend.

Serves the built frontend (frontend/dist) and a small JSON API over the
ouroboros DB. Saving a segment writes text_final; the M4 feedback step
diffs text_final against the machine draft to grow corrections/glossary.
"""

from __future__ import annotations

import subprocess
import sys
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import delete as sql_delete, select

from ..config import JOBS_DIR, PROJECT_ROOT
from ..db import Job, Segment, Translation, get_session, utcnow
from ..pipeline.assemble import to_srt

app = FastAPI(title="jamak-ouroboros review")

# video_id -> running pipeline process (started from the web UI)
_running: dict[str, subprocess.Popen] = {}


def _running_ids() -> set[str]:
    dead = [vid for vid, p in _running.items() if p.poll() is not None]
    for vid in dead:
        _running.pop(vid, None)
    return set(_running.keys())


class JobCreate(BaseModel):
    url: str


@app.post("/api/jobs")
def create_job(body: JobCreate) -> dict:
    """Kick off the full pipeline for a YouTube URL (background process)."""
    from ..pipeline.ingest import extract_video_id

    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if video_id in _running_ids():
        return {"video_id": video_id, "status": "running"}

    # a re-run replaces all segments — never silently destroy review work
    with get_session() as session:
        existing = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if existing is not None:
            raise HTTPException(
                409,
                "이미 등록된 영상입니다. 재처리하려면 CLI에서 실행하세요: "
                f"uv run jamak run <url> (검수 내용이 초기화됩니다)",
            )

    proc = subprocess.Popen(
        ["uv", "run", "jamak", "run", body.url],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _running[video_id] = proc
    return {"video_id": video_id, "status": "starting"}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    from collections import defaultdict

    from ..pipeline.translate import LANG_KO

    running = _running_ids()
    with get_session() as session:
        jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
        out = []
        seen = set()
        for j in jobs:
            seen.add(j.video_id)
            seg_ids = list(
                session.exec(select(Segment.id).where(Segment.job_id == j.id)).all()
            )
            n_total = len(seg_ids)
            n_reviewed = len(
                session.exec(
                    select(Segment.id).where(
                        Segment.job_id == j.id, Segment.reviewed == True  # noqa: E712
                    )
                ).all()
            )
            ko_complete = n_total > 0 and n_reviewed == n_total

            # per-language completion: a language is "done" when every segment
            # has a human-reviewed translation
            langs: list[dict] = []
            if seg_ids:
                trs = session.exec(
                    select(Translation).where(Translation.segment_id.in_(seg_ids))
                ).all()
                by_lang: dict[str, list] = defaultdict(list)
                for t in trs:
                    by_lang[t.lang].append(t)
                for code, rows in by_lang.items():
                    reviewed = sum(1 for r in rows if r.reviewed)
                    langs.append(
                        {
                            "code": code,
                            "label": LANG_KO.get(code, code),
                            "translated": len(rows),
                            "reviewed": reviewed,
                            "complete": reviewed == n_total,
                        }
                    )
                langs.sort(key=lambda x: x["code"])

            out.append(
                {
                    "video_id": j.video_id,
                    "title": j.title,
                    "duration_seconds": j.duration_seconds,
                    "status": j.status,
                    "segments": n_total,
                    "reviewed": n_reviewed,
                    "ko_complete": ko_complete,
                    "languages": langs,
                    "created_at": j.created_at.isoformat(),
                    "upload_date": j.upload_date,
                    "running": j.video_id in running,
                }
            )
        # pipeline just launched, no DB row yet — show a placeholder card
        for vid in running - seen:
            out.insert(
                0,
                {
                    "video_id": vid,
                    "title": "",
                    "duration_seconds": 0,
                    "status": "starting",
                    "segments": 0,
                    "reviewed": 0,
                    "ko_complete": False,
                    "languages": [],
                    "created_at": "",
                    "upload_date": "",
                    "running": True,
                },
            )
        return out


class SegmentUpdate(BaseModel):
    text_final: str | None = None
    start: float | None = None
    end: float | None = None
    reviewed: bool | None = None


class SegmentSnapshot(BaseModel):
    id: int | None = None
    idx: int
    start: float
    end: float
    text_whisper: str = ""
    text_youtube: str = ""
    text_llm: str = ""
    text_final: str = ""
    flagged: bool = False
    llm_uncertain: bool = False
    reviewed: bool = False


class RestoreSegmentsBody(BaseModel):
    segments: list[SegmentSnapshot]


@app.get("/api/jobs/{video_id}/segments")
def get_segments(video_id: str) -> list[dict]:
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        return [s.model_dump() for s in segs]


@app.post("/api/jobs/{video_id}/segments/restore")
def restore_segments(video_id: str, body: RestoreSegmentsBody) -> list[dict]:
    """Restore one editor undo snapshot for a job's segment list."""
    if not body.segments:
        raise HTTPException(400, "empty segment snapshot")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")

        current_ids = session.exec(
            select(Segment.id).where(Segment.job_id == job.id)
        ).all()
        if current_ids:
            session.exec(
                sql_delete(Translation).where(Translation.segment_id.in_(current_ids))
            )
        session.exec(sql_delete(Segment).where(Segment.job_id == job.id))

        for i, snap in enumerate(sorted(body.segments, key=lambda s: s.idx)):
            session.add(
                Segment(
                    id=snap.id,
                    job_id=job.id,
                    idx=i,
                    start=round(max(0.0, snap.start), 3),
                    end=round(max(snap.start + 0.1, snap.end), 3),
                    text_whisper=snap.text_whisper,
                    text_youtube=snap.text_youtube,
                    text_llm=snap.text_llm,
                    text_final=snap.text_final,
                    flagged=snap.flagged,
                    llm_uncertain=snap.llm_uncertain,
                    reviewed=snap.reviewed,
                )
            )
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()

        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        return [s.model_dump() for s in segs]


@app.put("/api/segments/{segment_id}")
def update_segment(segment_id: int, body: SegmentUpdate) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        if body.text_final is not None:
            seg.text_final = body.text_final
        if body.start is not None:
            start = round(max(0.0, body.start), 3)
            if start >= seg.end:
                start = round(max(0.0, seg.end - 0.1), 3)
            seg.start = start
            prev = _previous_segment(session, seg)
            if prev is not None and prev.end > start:
                prev.end = start
                session.add(prev)
        if body.end is not None:
            end = round(max(seg.start + 0.1, body.end), 3)
            seg.end = end
            nxt = _next_segment(session, seg)
            if nxt is not None and nxt.start < end:
                nxt.start = end
                session.add(nxt)
        if body.reviewed is not None:
            seg.reviewed = body.reviewed
        session.add(seg)
        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
        session.refresh(seg)
        return seg.model_dump()


def _display_text(seg: Segment) -> str:
    return seg.text_final or seg.text_llm or seg.text_whisper


def _join_dedup(left: str, right: str) -> str:
    """Join adjacent subtitle text while removing repeated overlap."""
    left = left.strip()
    right = right.strip()
    if not left:
        return right
    if not right:
        return left

    left_tokens = left.split()
    right_tokens = right.split()
    for n in range(min(len(left_tokens), len(right_tokens)), 0, -1):
        if left_tokens[-n:] == right_tokens[:n]:
            return " ".join(left_tokens + right_tokens[n:]).strip()

    # Korean subtitles are mostly space-separated, but keep a small character
    # fallback for punctuation-adjacent duplicate fragments.
    for n in range(min(len(left), len(right), 30), 1, -1):
        if left[-n:] == right[:n] and not left[-n:].isspace():
            return f"{left}{right[n:]}".strip()
    return f"{left} {right}".strip()


def _text_weight(text: str) -> int:
    tokens = re.findall(r"[\w가-힣]+|[^\s]", text)
    return max(1, sum(len(t) for t in tokens))


def _weighted_boundary(start: float, end: float, left_text: str, right_text: str) -> float:
    duration = max(0.0, end - start)
    if duration <= 0.2:
        return round(start + duration / 2, 3)
    left_weight = _text_weight(left_text)
    right_weight = _text_weight(right_text)
    ratio = left_weight / (left_weight + right_weight)
    mid = start + duration * ratio
    return round(min(max(mid, start + 0.1), end - 0.1), 3)


def _next_segment(session, seg: Segment) -> Segment | None:
    return session.exec(
        select(Segment).where(
            Segment.job_id == seg.job_id,
            Segment.idx == seg.idx + 1,
        )
    ).first()


def _previous_segment(session, seg: Segment) -> Segment | None:
    return session.exec(
        select(Segment).where(
            Segment.job_id == seg.job_id,
            Segment.idx == seg.idx - 1,
        )
    ).first()


class SplitBody(BaseModel):
    position: int  # char offset in the segment's display text


@app.post("/api/segments/{segment_id}/split")
def split_segment(segment_id: int, body: SplitBody) -> dict:
    """Cut one segment in two at a text position; timing is interpolated
    by character ratio (human can nudge afterwards)."""
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        text = _display_text(seg)
        left, right = text[: body.position].strip(), text[body.position :].strip()
        if not left or not right:
            raise HTTPException(400, "split position leaves an empty side")

        ratio = body.position / max(1, len(text))
        mid = round(seg.start + (seg.end - seg.start) * ratio, 3)

        # shift the tail to make room at idx+1
        tail = session.exec(
            select(Segment).where(
                Segment.job_id == seg.job_id, Segment.idx > seg.idx
            )
        ).all()
        for t in tail:
            t.idx += 1
            session.add(t)

        old_end = seg.end
        seg.text_final = left
        seg.end = mid
        session.add(seg)
        session.add(
            Segment(
                job_id=seg.job_id,
                idx=seg.idx + 1,
                start=mid,
                end=old_end,
                # machine texts stay on the left piece; diff-noise from the
                # split is filtered by feedback.extract_pairs' size cap
                text_final=right,
                flagged=seg.flagged,
                llm_uncertain=seg.llm_uncertain,
            )
        )
        # stale translations regenerate via source_hash on next export
        session.commit()
    return {"ok": True}


@app.post("/api/segments/{segment_id}/merge-next")
def merge_next(segment_id: int) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        nxt = _next_segment(session, seg)
        if nxt is None:
            raise HTTPException(400, "no next segment to merge")

        seg.text_final = _join_dedup(_display_text(seg), _display_text(nxt))
        seg.text_whisper = _join_dedup(seg.text_whisper, nxt.text_whisper)
        seg.text_youtube = _join_dedup(seg.text_youtube, nxt.text_youtube)
        seg.text_llm = _join_dedup(seg.text_llm, nxt.text_llm)
        seg.end = nxt.end
        seg.flagged = seg.flagged or nxt.flagged
        seg.llm_uncertain = seg.llm_uncertain or nxt.llm_uncertain
        seg.reviewed = False
        session.add(seg)

        session.exec(sql_delete(Translation).where(Translation.segment_id == nxt.id))
        session.delete(nxt)
        tail = session.exec(
            select(Segment).where(
                Segment.job_id == seg.job_id, Segment.idx > seg.idx + 1
            )
        ).all()
        for t in tail:
            t.idx -= 1
            session.add(t)
        session.commit()
    return {"ok": True}


class BoundaryBody(BaseModel):
    time: float


@app.post("/api/segments/{segment_id}/boundary-prev")
def boundary_prev(segment_id: int, body: BoundaryBody) -> dict:
    """Move the boundary between the previous segment and this one together."""
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        prev = _previous_segment(session, seg)

        hi = seg.end - 0.1
        if prev is None:
            t = round(min(max(body.time, 0.0), hi), 3)
            seg.start = t
            session.add(seg)
        else:
            lo = prev.start + 0.1
            if hi <= lo:
                raise HTTPException(400, "segments are too short to move boundary")
            t = round(min(max(body.time, lo), hi), 3)
            prev.end = t
            seg.start = t
            session.add(prev)
            session.add(seg)

        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
    return {"ok": True}


@app.post("/api/segments/{segment_id}/boundary-next")
def boundary_next(segment_id: int, body: BoundaryBody) -> dict:
    """Move the boundary between this segment and the next one together."""
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        nxt = _next_segment(session, seg)
        lo = seg.start + 0.1

        if nxt is None:
            t = round(max(body.time, lo), 3)
            seg.end = t
            session.add(seg)
        else:
            hi = nxt.end - 0.1
            if hi <= lo:
                raise HTTPException(400, "segments are too short to move boundary")
            t = round(min(max(body.time, lo), hi), 3)
            seg.end = t
            nxt.start = t
            session.add(seg)
            session.add(nxt)
        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
    return {"ok": True}


@app.post("/api/segments/{segment_id}/redistribute-next")
def redistribute_next(segment_id: int) -> dict:
    """Split this+next combined time span by current text lengths."""
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        nxt = _next_segment(session, seg)
        if nxt is None:
            raise HTTPException(400, "no next segment")

        mid = _weighted_boundary(seg.start, nxt.end, _display_text(seg), _display_text(nxt))
        seg.end = mid
        nxt.start = mid
        session.add(seg)
        session.add(nxt)
        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
    return {"ok": True}


@app.delete("/api/segments/{segment_id}")
def delete_segment(segment_id: int) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        job_id, idx = seg.job_id, seg.idx
        session.exec(sql_delete(Translation).where(Translation.segment_id == seg.id))
        session.delete(seg)
        tail = session.exec(
            select(Segment).where(Segment.job_id == job_id, Segment.idx > idx)
        ).all()
        for t in tail:
            t.idx -= 1
            session.add(t)
        session.commit()
    return {"ok": True}


def _safe_filename(title: str) -> str:
    bad = '\\/:*?"<>|'
    cleaned = "".join(c for c in title if c not in bad).strip().rstrip(".")
    return cleaned[:80] or "untitled"


@app.get("/api/jobs/{video_id}/export")
def export_srt(video_id: str, stage: str = "best", lang: str = "ko"):
    key_map = {"whisper": "text_whisper", "llm": "text_llm", "final": "text_final"}

    # Exporting is the end of a review pass. Absorb first, then read segments
    # so any same-video propagation is included in the downloaded file.
    from ..feedback import absorb_job

    try:
        absorb_job(video_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]
        title = job.title

    if stage == "best":
        # per-segment best: final > llm > whisper, so a half-reviewed job
        # still exports every segment
        for d in seg_dicts:
            d["text_export"] = d["text_final"] or d["text_llm"] or d["text_whisper"]
        key = "text_export"
    elif stage in key_map:
        key = key_map[stage]
    else:
        raise HTTPException(400, f"unknown stage {stage}")

    if lang != "ko":
        from ..pipeline.translate import LANGUAGES, translate_segments

        if lang not in LANGUAGES:
            raise HTTPException(400, f"unsupported language {lang}")
        translated = translate_segments(seg_dicts, key, lang)
        for d in seg_dicts:
            d["text_export_t"] = translated.get(d["id"], "")
        key = "text_export_t"

    out_dir = JOBS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = to_srt(seg_dicts, key, out_dir / f"{video_id}.{stage}.{lang}.srt")
    return FileResponse(
        path,
        media_type="application/x-subrip",
        filename=f"{lang}_{_safe_filename(title)}_자막.srt",
    )


@app.get("/api/languages")
def languages() -> list[dict]:
    from ..pipeline.translate import LANG_KO, LANGUAGES

    return [{"code": "ko", "label": "한국어 (원문)"}] + [
        {"code": c, "label": LANG_KO.get(c, l)} for c, l in LANGUAGES.items()
    ]


def _best_ko(seg: Segment) -> str:
    return seg.text_final or seg.text_llm or seg.text_whisper


@app.post("/api/jobs/{video_id}/translate")
def make_translations(video_id: str, lang: str) -> dict:
    """Generate (context-aware, cached) translations for every segment.

    Gated on the Korean review being complete — translating a draft wastes
    API cost and forces re-translation after the Korean is fixed.
    """
    from ..pipeline.translate import LANGUAGES, translate_segments

    if lang == "ko" or lang not in LANGUAGES:
        raise HTTPException(400, f"unsupported language {lang}")

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        total = len(segs)
        reviewed = sum(1 for s in segs if s.reviewed)
        if total == 0:
            raise HTTPException(400, "no segments")
        if reviewed < total:
            raise HTTPException(
                409,
                f"한국어 검수를 먼저 끝내주세요 ({reviewed}/{total} 확인됨). "
                "번역은 원문 검수가 끝난 뒤에 시작할 수 있습니다.",
            )
        seg_dicts = [s.model_dump() for s in segs]

    for d in seg_dicts:
        d["ko"] = d["text_final"] or d["text_llm"] or d["text_whisper"]
    translated = translate_segments(seg_dicts, "ko", lang)
    return {"lang": lang, "translated": len(translated), "segments": len(seg_dicts)}


@app.get("/api/jobs/{video_id}/translations")
def get_translations(video_id: str, lang: str) -> list[dict]:
    """KO + translation per segment, for the translation review view."""
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        rows = session.exec(
            select(Translation).where(Translation.lang == lang)
        ).all()
        by_seg = {t.segment_id: t for t in rows}
        out = []
        for s in segs:
            t = by_seg.get(s.id)
            out.append(
                {
                    "segment_id": s.id,
                    "idx": s.idx,
                    "start": s.start,
                    "end": s.end,
                    "ko": _best_ko(s),
                    "text": t.text if t else "",
                    "reviewed": t.reviewed if t else False,
                    "has_translation": t is not None,
                }
            )
        return out


class TranslationUpdate(BaseModel):
    text: str | None = None
    reviewed: bool | None = None


@app.put("/api/translations/{segment_id}")
def update_translation(segment_id: int, lang: str, body: TranslationUpdate) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        t = session.exec(
            select(Translation).where(
                Translation.segment_id == segment_id, Translation.lang == lang
            )
        ).first()
        if t is None:
            t = Translation(
                segment_id=segment_id, lang=lang, text="", source_hash=""
            )
        if body.text is not None and body.text != t.text:
            t.text = body.text
            t.edited = True
        if body.reviewed is not None:
            t.reviewed = body.reviewed
        session.add(t)
        session.commit()
        session.refresh(t)
        return {"segment_id": segment_id, "text": t.text, "reviewed": t.reviewed}


@app.post("/api/jobs/{video_id}/repair-stt")
def repair_stt(video_id: str) -> dict:
    """Recover segments where whisper hallucinated its initial_prompt.

    Works on segments already in the DB (e.g. videos processed before the
    crosscheck-time echo filter existed). Zero API cost: where the segment
    text is a prompt echo and a YouTube caption exists for that span, we
    replace the working text with the YouTube caption and re-open it for
    review. Segments with no caption are left for the human.
    """
    from ..glossary import whisper_prompt
    from ..pipeline.noise import is_prompt_echo

    prompt = whisper_prompt()
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        repaired = 0
        no_caption = 0
        for seg in segs:
            base = seg.text_final or seg.text_llm or seg.text_whisper
            if not is_prompt_echo(base, prompt):
                continue
            yt = seg.text_youtube.strip()
            if yt:
                seg.text_final = yt
                seg.flagged = True
                seg.reviewed = False
                session.add(seg)
                repaired += 1
            else:
                no_caption += 1
        if repaired:
            job.status, job.updated_at = "reviewing", utcnow()
            session.add(job)
        session.commit()
    return {"repaired": repaired, "no_caption": no_caption}


@app.post("/api/jobs/{video_id}/absorb")
def absorb(video_id: str) -> dict:
    """Ouroboros feedback: pull reviewed diffs into the corrections DB."""
    from ..feedback import absorb_job

    try:
        return absorb_job(video_id)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


# static frontend (built by `npm run build` in src/jamak/web/frontend)
_dist = Path(__file__).parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
