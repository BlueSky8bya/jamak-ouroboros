"""Review web app — FastAPI backend.

Serves the built frontend (frontend/dist) and a small JSON API over the
ouroboros DB. Saving a segment writes text_final; the M4 feedback step
diffs text_final against the machine draft to grow corrections/glossary.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import select

from ..config import JOBS_DIR
from ..db import Job, Segment, get_session, utcnow
from ..pipeline.assemble import to_srt

app = FastAPI(title="jamak-ouroboros review")


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    with get_session() as session:
        jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
        out = []
        for j in jobs:
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
                }
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


@app.get("/api/jobs/{video_id}/export")
def export_srt(video_id: str, stage: str = "best"):
    key_map = {"whisper": "text_whisper", "llm": "text_llm", "final": "text_final"}
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]

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

    out_dir = JOBS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = to_srt(seg_dicts, key, out_dir / f"{video_id}.{stage}.srt")
    return FileResponse(
        path, media_type="text/plain", filename=f"{video_id}.{stage}.srt"
    )


@app.get("/api/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


# static frontend (built by `npm run build` in src/jamak/web/frontend)
_dist = Path(__file__).parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
