"""Review web app — FastAPI backend.

Serves the built frontend (frontend/dist) and a small JSON API over the
ouroboros DB. Saving a segment writes text_final; the M4 feedback step
diffs text_final against the machine draft to grow corrections/glossary.
"""

from __future__ import annotations

import subprocess
import sys
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
    running = _running_ids()
    with get_session() as session:
        jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
        out = []
        seen = set()
        for j in jobs:
            seen.add(j.video_id)
            n_total = len(
                session.exec(select(Segment.id).where(Segment.job_id == j.id)).all()
            )
            n_reviewed = len(
                session.exec(
                    select(Segment.id).where(
                        Segment.job_id == j.id, Segment.reviewed == True  # noqa: E712
                    )
                ).all()
            )
            out.append(
                {
                    "video_id": j.video_id,
                    "title": j.title,
                    "duration_seconds": j.duration_seconds,
                    "status": j.status,
                    "segments": n_total,
                    "reviewed": n_reviewed,
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
                    "running": True,
                },
            )
        return out


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


class SegmentUpdate(BaseModel):
    text_final: str | None = None
    start: float | None = None
    end: float | None = None
    reviewed: bool | None = None


@app.put("/api/segments/{segment_id}")
def update_segment(segment_id: int, body: SegmentUpdate) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        if body.text_final is not None:
            seg.text_final = body.text_final
        if body.start is not None:
            seg.start = body.start
        if body.end is not None:
            seg.end = body.end
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
        nxt = session.exec(
            select(Segment).where(
                Segment.job_id == seg.job_id, Segment.idx == seg.idx + 1
            )
        ).first()
        if nxt is None:
            raise HTTPException(400, "no next segment to merge")

        seg.text_final = f"{_display_text(seg)} {_display_text(nxt)}".strip()
        seg.text_whisper = f"{seg.text_whisper} {nxt.text_whisper}".strip()
        seg.text_youtube = f"{seg.text_youtube} {nxt.text_youtube}".strip()
        seg.text_llm = f"{seg.text_llm} {nxt.text_llm}".strip()
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
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]
        title = job.title

    # exporting IS the end of a review pass — absorb feedback automatically
    # so the ouroboros loop never gets skipped (harness rule 1)
    from ..feedback import absorb_job

    absorb_job(video_id)

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
        filename=f"{_safe_filename(title)}_자막_{lang}.srt",
    )


@app.get("/api/languages")
def languages() -> list[dict]:
    from ..pipeline.translate import LANGUAGES

    return [{"code": "ko", "label": "한국어 (원문)"}] + [
        {"code": c, "label": l} for c, l in LANGUAGES.items()
    ]


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
