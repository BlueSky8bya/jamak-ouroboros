"""Review web app — FastAPI backend.

Serves the built frontend (frontend/dist) and a small JSON API over the
ouroboros DB. Saving a segment writes text_final; the M4 feedback step
diffs text_final against the machine draft to grow corrections/glossary.
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
import re
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import delete as sql_delete, select

from ..config import JOBS_DIR, PROJECT_ROOT

from ..db import (
    Job,
    Segment,
    Track,
    Translation,
    get_session,
    load_stt_blob,
    utcnow,
)
from ..pipeline.assemble import to_srt

app = FastAPI(title="jamak-ouroboros review")


def _load_stt(video_id: str, session=None) -> "list | None":
    """Parsed per-word STT for a video: DB blob first (works on a cloud host
    with no job files, ADR-0007 path B), local stt.json file as fallback (local
    dev / videos stored before the blob existed). None if neither has it."""
    import json as _json

    def _from_db(sess) -> "list | None":
        job = sess.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None or job.id is None:
            return None
        blob = load_stt_blob(sess, job.id)
        return _json.loads(blob) if blob else None

    raw = _from_db(session) if session is not None else None
    if raw is None and session is None:
        with get_session() as s:
            raw = _from_db(s)
    if raw is not None:
        return raw
    stt_path = JOBS_DIR / video_id / "stt.json"
    if stt_path.exists():
        return _json.loads(stt_path.read_text(encoding="utf-8"))
    return None


# Auth for deployment. A styled in-app login form (not the browser Basic prompt)
# posts to /api/login and gets a signed session cookie; the middleware checks the
# cookie on API calls. Off by default (local single-user).
#
# Role is decided by WHICH shared password matches, NOT by a name allowlist:
#   JAMAK_ADMIN_PASSWORD  -> admin  (run the GPU pipeline + everything)
#   JAMAK_PASSWORD        -> reviewer (review/translate/export only)
#   neither matches       -> rejected
# The typed name is only a display label for the "who's online" chip, so adding a
# reviewer = just share the reviewer password (no env edit / redeploy needed).
# Legacy per-user JAMAK_AUTH="user:pw,..." still works (role = admin if the name
# is in JAMAK_ADMINS, else reviewer).
import hashlib
import hmac

from fastapi.responses import JSONResponse


def _load_auth() -> dict[str, str]:
    raw = os.environ.get("JAMAK_AUTH", "").strip()
    creds: dict[str, str] = {}
    for pair in raw.split(","):
        user, sep, pw = pair.partition(":")
        if sep and user.strip():
            creds[user.strip()] = pw.strip()
    return creds


_AUTH_CREDS = _load_auth()
_REVIEWER_PW = os.environ.get("JAMAK_PASSWORD", "").strip()
_ADMIN_PW = os.environ.get("JAMAK_ADMIN_PASSWORD", "").strip()
# admin names only matter for the legacy JAMAK_AUTH fallback; the password-based
# roles below ignore names entirely.
_ADMINS = {n.strip() for n in os.environ.get("JAMAK_ADMINS", "").split(",") if n.strip()}
_AUTH_ON = bool(_ADMIN_PW or _REVIEWER_PW or _AUTH_CREDS)
# session-cookie signing key. Persist JAMAK_SECRET so logins survive a restart.
_SECRET = (os.environ.get("JAMAK_SECRET") or secrets.token_hex(32)).encode()
_SEP = "\x1f"  # unit separator between role and display name inside the cookie


def _auth_role(name: str, pw: str) -> str:
    """Role this password grants: 'admin', 'reviewer', or '' (reject).

    Admin is checked first so the admin password always wins even if the two
    passwords were (mis)configured to the same value.
    """
    if _ADMIN_PW and secrets.compare_digest(pw, _ADMIN_PW):
        return "admin"
    if _REVIEWER_PW and secrets.compare_digest(pw, _REVIEWER_PW):
        return "reviewer"
    expected = _AUTH_CREDS.get(name.strip())  # legacy JAMAK_AUTH fallback
    if expected is not None and secrets.compare_digest(pw, expected):
        return "admin" if name.strip() in _ADMINS else "reviewer"
    return ""


def _sign(role: str, name: str) -> str:
    payload = f"{role}{_SEP}{name}"
    b = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_SECRET, b.encode(), hashlib.sha256).hexdigest()
    return f"{b}.{sig}"


def _verify_cookie(val: str) -> tuple[str, str]:
    """(role, display_name) from a valid signed cookie, else ('', '')."""
    try:
        b, sig = val.split(".", 1)
        good = hmac.new(_SECRET, b.encode(), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, good):
            return "", ""
        payload = base64.urlsafe_b64decode(b).decode()
        role, _, name = payload.partition(_SEP)
        if role not in ("admin", "reviewer"):
            return "", ""
        return role, name
    except Exception:
        return "", ""


def _current_user(request: Request) -> str:
    return getattr(request.state, "user", "") or ""


def _current_role(request: Request) -> str:
    return getattr(request.state, "role", "") or ""


def _is_admin(request: Request) -> bool:
    # auth off -> local dev, everyone is admin
    if not _AUTH_ON:
        return True
    return _current_role(request) == "admin"


def _require_admin(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(403, "관리자만 자막 생성(파이프라인)을 실행할 수 있습니다")


# API paths reachable without a session (so the SPA can show the login form)
_PUBLIC_API = {"/api/login", "/api/logout", "/api/me", "/api/version"}


def _deploy_version() -> str:
    """Short identifier of the running build, shown in the UI so you can tell at
    a glance whether the site is the just-pushed version. On Railway this is the
    deployed commit (RAILWAY_GIT_COMMIT_SHA, injected automatically); locally it
    falls back to the current git SHA (the .git dir is excluded from the Docker
    image, so the env var is what the cloud uses)."""
    v = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("JAMAK_VERSION")
    if v:
        return v[:7]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "dev"


_VERSION = _deploy_version()


@app.get("/api/version")
def version() -> dict:
    return {"version": _VERSION}


@app.middleware("http")
async def _session_auth(request: Request, call_next):
    request.state.user = ""
    request.state.role = ""
    if _AUTH_ON:
        role, name = _verify_cookie(request.cookies.get("jamak_session", ""))
        request.state.role = role
        request.state.user = name
        path = request.url.path
        if path.startswith("/api/") and path not in _PUBLIC_API and not role:
            return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)
    resp = await call_next(request)
    # never cache index.html (the SPA shell) — otherwise a new deploy's hashed
    # JS/CSS aren't picked up until a hard refresh (the version badge, a live
    # /api call, would show the new build while the running code is stale). The
    # content-hashed asset files stay cacheable.
    if "text/html" in resp.headers.get("content-type", ""):
        resp.headers["Cache-Control"] = "no-cache, must-revalidate"
    return resp


class LoginBody(BaseModel):
    name: str = ""  # optional display label; role comes from the password
    password: str


@app.post("/api/login")
def login(body: LoginBody) -> Response:
    name = body.name.strip()
    if not _AUTH_ON:
        return JSONResponse({"name": name, "is_admin": True, "authed": True})
    role = _auth_role(name, body.password)
    if not role:
        raise HTTPException(401, "비밀번호가 맞지 않습니다")
    resp = JSONResponse({"name": name, "is_admin": role == "admin", "authed": True})
    resp.set_cookie(
        "jamak_session",
        _sign(role, name),
        httponly=True,
        samesite="lax",
        secure=True,  # served over HTTPS (Railway / Cloudflare)
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@app.post("/api/logout")
def logout() -> Response:
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("jamak_session")
    return resp

# --- Pipeline requests (ADR-0008 path B) --------------------------------------
# The web app NEVER runs the GPU pipeline itself — the cloud host has no GPU.
# Creating a video only records a JobRequest here; a `jamak worker` on the local
# GPU machine polls for pending requests and processes them ONE AT A TIME (a
# single 8 GB GPU can't transcribe two videos at once). The DB is the single
# queue shared by the cloud app (records requests) and the local worker (drains).
from ..db import JobRequest


def _request_job(video_id: str, url: str, fresh: bool = False) -> str:
    """Record a pipeline request (deduped by video_id). Returns queue status."""
    with get_session() as session:
        existing = session.exec(
            select(JobRequest).where(
                JobRequest.video_id == video_id,
                JobRequest.status.in_(("pending", "processing")),
            )
        ).first()
        if existing is not None:
            return existing.status
        session.add(JobRequest(video_id=video_id, url=url, fresh=fresh))
        session.commit()
    return "pending"


def _running_ids() -> set[str]:
    """video_ids the worker is currently processing (marks job.running)."""
    with get_session() as session:
        rows = session.exec(
            select(JobRequest.video_id).where(JobRequest.status == "processing")
        ).all()
    return set(rows)


def _queue_state() -> list[dict]:
    """Pending / processing / errored requests for the queue banner."""
    with get_session() as session:
        rows = session.exec(
            select(JobRequest)
            .where(JobRequest.status.in_(("pending", "processing", "error")))
            .order_by(JobRequest.created_at)
        ).all()
    now = utcnow()

    def _age(r) -> int:
        # seconds since the last heartbeat (updated_at). A large value while
        # "processing" means the run likely stalled.
        ts = r.updated_at
        if ts is not None and ts.tzinfo is None:
            from datetime import timezone

            ts = ts.replace(tzinfo=timezone.utc)
        return int((now - ts).total_seconds()) if ts is not None else 0

    out: list[dict] = []
    for r in rows:
        if r.status == "processing":
            out.append(
                {
                    "video_id": r.video_id,
                    "status": "processing",
                    "note": r.note or "처리 중",
                    "age": _age(r),
                }
            )
    pos = 0
    for r in rows:
        if r.status == "pending":
            pos += 1
            out.append({"video_id": r.video_id, "status": "queued", "position": pos})
    for r in rows:
        if r.status == "error":
            out.append({"video_id": r.video_id, "status": "error", "note": r.note})
    return out


class JobCreate(BaseModel):
    url: str


@app.get("/api/me")
def whoami(request: Request) -> dict:
    """Who is logged in + may they run the pipeline (admin)? Drives the UI."""
    if not _AUTH_ON:
        return {
            "name": "",
            "is_admin": True,
            "authed": True,
            "auth_on": False,
            "can_ingest": True,
        }
    role = _current_role(request)
    return {
        "name": _current_user(request),
        "is_admin": role == "admin",
        "authed": bool(role),
        "auth_on": True,
        # admins can request a video from anywhere (the local worker does the GPU
        # work); the cloud app just records the request.
        "can_ingest": role == "admin",
    }


@app.post("/api/jobs")
def create_job(request: Request, body: JobCreate) -> dict:
    """Request subtitles for a YouTube URL.

    Admin-only. Records a request in the DB; the `jamak worker` on the local GPU
    machine picks it up and runs the pipeline (one at a time). Works from the
    cloud app — no GPU is needed here.
    """
    _require_admin(request)
    from ..pipeline.ingest import extract_video_id

    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if video_id in _running_ids():
        return {"video_id": video_id, "status": "processing"}

    # a re-run replaces all segments — never silently destroy review work
    with get_session() as session:
        existing = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if existing is not None:
            raise HTTPException(
                409,
                "이미 등록된 영상입니다. 재처리하려면 카드의 '다시 인식'을 쓰세요 "
                "(검수 내용이 초기화됩니다).",
            )

    status = _request_job(video_id, body.url)
    return {"video_id": video_id, "status": status}


class SrtOnlyCreate(BaseModel):
    url: str
    content: str
    filename: str = ""


@app.post("/api/jobs/srt-only")
def create_job_srt_only(request: Request, body: SrtOnlyCreate) -> dict:
    """Register a video straight from an already-reviewed .srt — NO pipeline.

    [WH-CHANGE v0.9.21 | FEAT | 2026-07-15 | CHG-20260715-042]
    Reason: 자막이 이미 있는 영상은 STT·Claude 교정·GPU 워커가 전부 불필요 —
      영상만 올리고 .srt를 그대로 붙이면 된다 (사용자 요청, 컴퓨팅 최소화).
      순수 파싱+삽입만 하고 어떤 모델/API도 호출하지 않는다. 등록된 자막은
      사람이 검수한 결과물이므로 reviewed=True, timing_done=True(=완료).
    Related: CHANGELOG CHG-20260715-042.

    Admin-only. Distinct from /import-srt (그건 기존 Job의 자막을 교체).
    """
    _require_admin(request)
    import srt as _srtlib

    from ..pipeline.ingest import extract_video_id, fetch_title

    try:
        video_id = extract_video_id(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        subs = [s for s in _srtlib.parse(body.content) if s.content.strip()]
    except Exception as e:
        raise HTTPException(400, f".srt 파싱 실패: {e}")
    if not subs:
        raise HTTPException(400, ".srt에 자막이 없습니다.")

    # Korean-source guard (same as import_srt): a translation belongs to its
    # own track, never the ko source.
    joined = " ".join(s.content for s in subs)
    hangul = sum(1 for ch in joined if "가" <= ch <= "힣")
    latin = sum(1 for ch in joined if "a" <= ch.lower() <= "z")
    if hangul + latin > 0 and hangul < latin:
        raise HTTPException(400, "한국어 자막(.srt)만 올릴 수 있어요.")

    cues = sorted(
        (
            (s.start.total_seconds(), s.end.total_seconds(), " ".join(s.content.split()))
            for s in subs
        ),
        key=lambda c: c[0],
    )
    with get_session() as session:
        if session.exec(select(Job).where(Job.video_id == video_id)).first():
            raise HTTPException(
                409,
                "이미 등록된 영상입니다. 자막을 바꾸려면 카드에 .srt를 끌어다 놓으세요.",
            )
        job = Job(
            video_id=video_id,
            url=body.url,
            title=fetch_title(video_id),  # oEmbed(가벼운 GET) — 실패 시 빈값
            duration_seconds=round(cues[-1][1], 3) if cues else 0.0,
            status="reviewing",
            timing_done=True,  # .srt는 사람 타이밍을 담고 있다
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        for i, (st, en, txt) in enumerate(cues):
            session.add(
                Segment(
                    job_id=job.id,
                    lang="ko",
                    idx=i,
                    start=st,
                    end=en,
                    text_whisper="",
                    text_youtube="",
                    text_llm=txt,
                    text_final=txt,
                    flagged=False,
                    reviewed=True,
                )
            )
        session.commit()
    return {"video_id": video_id, "applied": len(cues)}


@app.get("/api/queue")
def queue_state() -> list[dict]:
    """Pipeline queue: the video processing now + any waiting behind it."""
    return _queue_state()


@app.delete("/api/queue/{video_id}")
def cancel_request(request: Request, video_id: str) -> dict:
    """Drop a request (admin) — pending, errored, or stuck-'processing'.

    A worker that dies mid-run (Ctrl+C) leaves the request stuck at 'processing'
    with no live worker; deleting the row clears it. (If a worker is actually
    running it, the run finishes on its own — only the queue entry is removed.)
    """
    _require_admin(request)
    with get_session() as session:
        rows = session.exec(
            select(JobRequest).where(
                JobRequest.video_id == video_id,
                JobRequest.status.in_(("pending", "error", "processing")),
            )
        ).all()
        for r in rows:
            session.delete(r)
        session.commit()
    return {"cancelled": len(rows)}


@app.post("/api/jobs/{video_id}/retranscribe")
def retranscribe(request: Request, video_id: str) -> dict:
    """Re-roll STT for an existing video with the *current* glossary/hotwords.

    The glossary grows as the corpus is mined and reviews accrue; a richer
    hotword set can make whisper hear domain vocabulary it missed before. This
    re-runs `jamak run <url>` (STT -> crosscheck -> correction), replacing all
    segments. Blocked once Korean review is complete so finished work is never
    destroyed; partial review is guarded by a frontend confirm. Admin-only (GPU).
    """
    _require_admin(request)
    if video_id in _running_ids():
        return {"video_id": video_id, "status": "running"}

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        seg_ids = list(
            session.exec(
                select(Segment.id).where(
                    Segment.job_id == job.id, Segment.lang == "ko"
                )
            ).all()
        )
        n_total = len(seg_ids)
        n_reviewed = len(
            session.exec(
                select(Segment.id).where(
                    Segment.job_id == job.id,
                    Segment.lang == "ko",
                    Segment.reviewed == True,  # noqa: E712
                )
            ).all()
        )
        if n_total > 0 and n_reviewed == n_total:
            raise HTTPException(
                409, "한국어 검수가 완료된 영상은 재인식할 수 없습니다."
            )
        url = job.url

    if not url:
        raise HTTPException(400, "URL 정보가 없어 재인식할 수 없습니다.")

    # --fresh re-roll goes through the same DB request queue (worker, one-at-a-time)
    status = _request_job(video_id, url, fresh=True)
    return {"video_id": video_id, "status": status}


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    from collections import defaultdict

    from ..pipeline.translate import LANG_KO

    running = _running_ids()
    with get_session() as session:
        from ..db import SrtBackup

        # practice-session clones are per-user working copies — never listed
        jobs = session.exec(
            select(Job)
            .where(Job.clone_of == None)  # noqa: E711
            .order_by(Job.created_at.desc())
        ).all()
        # video_ids that have an undoable .srt import snapshot (one query)
        srt_undo_ids = set(session.exec(select(SrtBackup.video_id)).all())
        out = []
        seen = set()
        for j in jobs:
            seen.add(j.video_id)
            # dashboard counts reflect the Korean source track
            seg_ids = list(
                session.exec(
                    select(Segment.id).where(
                        Segment.job_id == j.id, Segment.lang == "ko"
                    )
                ).all()
            )
            n_total = len(seg_ids)
            n_reviewed = len(
                session.exec(
                    select(Segment.id).where(
                        Segment.job_id == j.id,
                        Segment.lang == "ko",
                        Segment.reviewed == True,  # noqa: E712
                    )
                ).all()
            )
            ko_complete = n_total > 0 and n_reviewed == n_total

            # per-language completion (ADR-0006). A forked language has its own
            # segments (own reviewed state); a non-forked one inherits Korean and
            # is tracked via Translation rows keyed to the ko segments.
            langs: list[dict] = []
            if seg_ids:
                # per-(job,lang) timing-done lives on Track (forked tracks are
                # retimed independently of the Korean timing_done)
                track_timing = {
                    t.lang: bool(t.timing_done)
                    for t in session.exec(
                        select(Track).where(Track.job_id == j.id)
                    ).all()
                }
                forked: dict[str, list[bool]] = defaultdict(list)
                for lg, rv in session.exec(
                    select(Segment.lang, Segment.reviewed).where(
                        Segment.job_id == j.id, Segment.lang != "ko"
                    )
                ).all():
                    forked[lg].append(bool(rv))
                for code, revs in forked.items():
                    reviewed = sum(1 for r in revs if r)
                    langs.append(
                        {
                            "code": code,
                            "label": LANG_KO.get(code, code),
                            "translated": len(revs),
                            "reviewed": reviewed,
                            "complete": len(revs) > 0 and reviewed == len(revs),
                            "forked": True,
                            "timing_done": track_timing.get(code, False),
                        }
                    )
                # project only the two columns the counts need — not the full
                # Translation ORM object (which drags the per-cue text blob over
                # for every language on every dashboard poll, pure read waste).
                by_lang: dict[str, list[bool]] = defaultdict(list)
                for t_lang, t_reviewed in session.exec(
                    select(Translation.lang, Translation.reviewed).where(
                        Translation.segment_id.in_(seg_ids)
                    )
                ).all():
                    if t_lang not in forked:  # a forked track overrides its rows
                        by_lang[t_lang].append(t_reviewed)
                for code, revs_list in by_lang.items():
                    reviewed = sum(1 for r in revs_list if r)
                    langs.append(
                        {
                            "code": code,
                            "label": LANG_KO.get(code, code),
                            "translated": len(revs_list),
                            "reviewed": reviewed,
                            "complete": reviewed == n_total,
                            "forked": False,
                            "timing_done": False,
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
                    "timing_done": j.timing_done,
                    "languages": langs,
                    "created_at": j.created_at.isoformat(),
                    "upload_date": j.upload_date,
                    "running": j.video_id in running,
                    "srt_undo": j.video_id in srt_undo_ids,
                    "assignee": j.assignee,
                    "practice": j.practice,
                    "practice_course": j.practice_course,
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
                    "timing_done": False,
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
    # "" = clear, "hold" = 잘 안 들림/보류 (ADR-0009)
    review_flag: str | None = None


class ReplaceBody(BaseModel):
    find: str
    replace: str = ""
    apply: bool = False  # False = preview count only


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
    edited: bool = False
    low_conf: str = ""
    review_flag: str = ""


class RestoreRowsBody(BaseModel):
    """One editor undo step: put these rows back exactly as they were, and
    delete the rows the undone operation created."""

    upsert: list[SegmentSnapshot]
    delete_ids: list[int] = []


def _work_text(seg: Segment) -> str:
    return (seg.text_final or seg.text_llm or seg.text_whisper).strip()


# reading-speed limit. Comfortable subtitle reading is ~12-17 chars/sec across
# languages (Netflix 17, BBC ~15; Korean similar). Above this the viewer starts
# missing dialogue or the picture — flag so the reviewer splits or lengthens it.
TOO_FAST_CPS = 17.0


def _cps(seg: Segment) -> float:
    """Characters-per-second of the working text (reading speed)."""
    text = re.sub(r"\s+", "", _work_text(seg))
    dur = max(0.1, seg.end - seg.start)
    return len(text) / dur


def _seg_payload(seg: Segment) -> dict:
    """Segment dict for mutation responses. Mirrors get_segments' shape minus
    `safe` (needs a glossary scan — too heavy per keystroke; the client keeps
    its previous value by merging this over the old row)."""
    d = seg.model_dump()
    d["suspect"] = _suspect_words(seg)
    d["too_fast"] = _cps(seg) > TOO_FAST_CPS
    return d


def _suspect_words(seg: Segment) -> str:
    """Words worth double-checking, preferring the 2-engine disagreement signal.

    A 2025 CHI study found single-model word-confidence highlighting gives no
    measurable benefit (confidence↔correctness only weakly correlated) and
    annoys reviewers. Our edge is a *second* independent engine (YouTube): the
    words where whisper and YouTube disagree are a far stronger error signal.
    Use that when a YouTube caption exists; fall back to whisper's own low-
    probability words only when there is no second opinion.
    """
    work = _work_text(seg)
    if not work:
        return ""
    yt = (seg.text_youtube or "").strip()
    if yt:
        yt_tokens = {re.sub(r"[^\w가-힣]", "", t) for t in yt.split()}
        yt_tokens.discard("")
        out: list[str] = []
        for tok in work.split():
            norm = re.sub(r"[^\w가-힣]", "", tok)
            if len(norm) >= 2 and norm not in yt_tokens and tok not in out:
                out.append(tok)
        return ", ".join(out[:6])
    return seg.low_conf  # no second opinion — fall back to whisper confidence


def _is_safe(seg: Segment, surface_forms: set[str]) -> bool:
    """Low-risk segment the reviewer can trust at a glance (skim/bulk-confirm).

    Not flagged (both engines agreed), AI not unsure, real text present, no
    domain vocabulary (the words most prone to mis-hearing), and a comfortable
    reading speed (a too-fast subtitle needs a timing fix even if the text is
    right). Surfacing these lets the human fly past them and focus on the rest.
    """
    if seg.flagged or seg.llm_uncertain:
        return False
    text = _work_text(seg)
    if not text:
        return False
    if _cps(seg) > TOO_FAST_CPS:
        return False
    hay = text + " " + (seg.text_youtube or "")
    return not any(f in hay for f in surface_forms)


@app.post("/api/jobs/{video_id}/fork-track")
def fork_track(video_id: str, lang: str) -> dict:
    """Split a translation language off into its own independent track (ADR-0006).

    Copies the Korean segments' structure/timing into new lang segments, filled
    with the current translation text, so the reviewer can then split/merge/retime
    that language differently from Korean. No-op if the track already exists.
    Costs no API — pure copy.
    """
    if lang == "ko":
        raise HTTPException(400, "ko is the source track")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        ko_segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        if not ko_segs:
            raise HTTPException(400, "no Korean segments to fork from")
        existing = session.exec(
            select(Segment.id).where(Segment.job_id == job.id, Segment.lang == lang)
        ).first()
        if existing is not None:
            return {"video_id": video_id, "lang": lang, "forked": True, "created": 0}

        # current translation text per ko segment (inherited default)
        trs = session.exec(
            select(Translation).where(
                Translation.segment_id.in_([s.id for s in ko_segs]),
                Translation.lang == lang,
            )
        ).all()
        from ..pipeline.translate import _hash

        text_by_seg = {t.segment_id: t.text for t in trs}
        edited_by_seg = {t.segment_id: t.edited for t in trs}
        # carry the per-translation review state onto the forked segment, so
        # forking a fully-reviewed language purely to retime it does NOT reset
        # its 124/124 review progress (list_jobs then reads the forked
        # Segment.reviewed, ignoring the now-superseded Translation rows). BUT
        # only carry reviewed=True when the translation is NOT stale: a row
        # confirmed against OLD Korean (source_hash mismatch) would otherwise
        # freeze as 'done' with no stale flag left on the forked Segment.
        reviewed_by_seg = {}
        for t in trs:
            ko = next((s for s in ko_segs if s.id == t.segment_id), None)
            fresh = ko is not None and t.source_hash == _hash(_best_ko(ko).strip())
            reviewed_by_seg[t.segment_id] = bool(t.reviewed and fresh)

        created = 0
        for s in ko_segs:
            session.add(
                Segment(
                    job_id=job.id,
                    lang=lang,
                    idx=s.idx,
                    start=s.start,
                    end=s.end,
                    text_final=text_by_seg.get(s.id, ""),
                    reviewed=reviewed_by_seg.get(s.id, False),
                    edited=edited_by_seg.get(s.id, False),
                )
            )
            created += 1
        track = session.exec(
            select(Track).where(Track.job_id == job.id, Track.lang == lang)
        ).first()
        if track is None:
            track = Track(job_id=job.id, lang=lang)
        track.forked = True
        # a fresh fork owes its own timing pass — never resurrect a stale
        # timing_done from a previous fork/unfork cycle of this language.
        track.timing_done = False
        session.add(track)
        # the forked Segment rows now own this language's text/review state;
        # the source Translation rows are dead duplicates (list_jobs/export/
        # editor all read the forked segments). Delete them so they don't (a)
        # duplicate ~N rows of text per forked lang, nor (b) keep feeding
        # translation_examples() frozen pre-fork text as human-confirmed
        # few-shot examples after the reviewer edits the forked segments.
        for tr in trs:
            session.delete(tr)
        # idempotency is guaranteed by the existence check above (a re-fork
        # returns created:0 before reaching here), not a DB unique index.
        session.commit()
    return {"video_id": video_id, "lang": lang, "forked": True, "created": created}


@app.post("/api/jobs/{video_id}/unfork-track")
def unfork_track(video_id: str, lang: str) -> dict:
    """Revert a forked translation track back to the inherited (Translation) view.

    Reconstructs Translation rows from the forked Segment.text_final (matched to
    each Korean cue by time overlap — lossless for an unedited fork, best-effort
    if the track was re-split), then removes the lang Segment rows and clears the
    fork flag. This is the honest counterpart to fork_track so 'fork to try
    independent timing' is reversible without hand-retyping every line.
    """
    if lang == "ko":
        raise HTTPException(400, "cannot unfork the Korean source track")
    from ..pipeline.translate import _hash

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        fseg = session.exec(
            select(Segment).where(Segment.job_id == job.id, Segment.lang == lang)
        ).all()
        if not fseg:
            return {"video_id": video_id, "lang": lang, "forked": False, "restored": 0}
        ko_segs = session.exec(
            select(Segment).where(Segment.job_id == job.id, Segment.lang == "ko")
        ).all()
        # rebuild inherited translations: for each ko cue, the forked cue that
        # overlaps it most carries the translation text
        restored = 0
        for ko in ko_segs:
            best, best_ov = None, 0.0
            for f in fseg:
                ov = min(f.end, ko.end) - max(f.start, ko.start)
                if ov > best_ov:
                    best, best_ov = f, ov
            text = (best.text_final or "").strip() if best is not None else ""
            if not text:
                continue
            # drop any stale row for this ko cue+lang, then write the rebuilt one
            for old in session.exec(
                select(Translation).where(
                    Translation.segment_id == ko.id, Translation.lang == lang
                )
            ).all():
                session.delete(old)
            session.add(
                Translation(
                    segment_id=ko.id,
                    lang=lang,
                    text=text,
                    source_hash=_hash(_best_ko(ko).strip()),
                    reviewed=bool(best.reviewed) if best is not None else False,
                    # carry the REAL edited flag from the forked segment — do not
                    # mark all rebuilt rows edited. Copied machine text (a fork made
                    # only to retime) must stay edited=False so it (a) isn't frozen
                    # against re-translation and (b) doesn't masquerade as a human-
                    # confirmed few-shot example, which would poison the loop.
                    edited=bool(best.edited) if best is not None else False,
                )
            )
            restored += 1
        # remove the forked segments and clear the fork flag
        session.exec(
            sql_delete(Segment).where(Segment.job_id == job.id, Segment.lang == lang)
        )
        track = session.exec(
            select(Track).where(Track.job_id == job.id, Track.lang == lang)
        ).first()
        if track is not None:
            track.forked = False
            session.add(track)
        session.commit()
    return {"video_id": video_id, "lang": lang, "forked": False, "restored": restored}


@app.get("/api/jobs/{video_id}/segments")
def get_segments(video_id: str, lang: str = "ko") -> list[dict]:
    """Segments for one subtitle track (default the Korean source, ADR-0006)."""
    from ..glossary import glossary_surface_forms

    forms = glossary_surface_forms()
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.idx)
        ).all()
        out = []
        for s in segs:
            d = s.model_dump()
            d["safe"] = _is_safe(s, forms)
            d["suspect"] = _suspect_words(s)
            d["too_fast"] = _cps(s) > TOO_FAST_CPS
            out.append(d)
        return out


@app.post("/api/jobs/{video_id}/confirm-safe")
def confirm_safe(video_id: str, lang: str = "ko") -> dict:
    """Bulk-confirm every low-risk unreviewed segment (one-click skim).

    Marks the confident segments reviewed and promotes their working text to
    text_final, so the reviewer only has to look at the flagged/uncertain rest.
    Nothing destructive: each stays fully editable and un-reviewable afterward.
    """
    from ..glossary import glossary_surface_forms

    forms = glossary_surface_forms()
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id, Segment.lang == lang)
        ).all()
        confirmed = 0
        for seg in segs:
            if seg.reviewed or not _is_safe(seg, forms):
                continue
            seg.text_final = (seg.text_final or seg.text_llm or seg.text_whisper).strip()
            seg.reviewed = True
            session.add(seg)
            confirmed += 1
        if confirmed:
            job.status, job.updated_at = "reviewing", utcnow()
            session.add(job)
        session.commit()
    return {"confirmed": confirmed}


@app.post("/api/jobs/{video_id}/replace")
def replace_text(video_id: str, body: ReplaceBody, lang: str = "ko") -> dict:
    """Find & replace across every subtitle in one shot.

    A lecture repeats the same mis-hear many times; fixing them one by one is
    the biggest source of review fatigue. `apply=False` returns a match count
    for preview; `apply=True` performs the replacement on each segment's working
    text. Deterministic, no API. Review flags are left untouched.
    """
    find = body.find
    if not find:
        raise HTTPException(400, "찾을 내용을 입력하세요")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id, Segment.lang == lang)
        ).all()
        matches = 0
        seg_hits = 0
        if not segs and lang != "ko":
            # 비포크 번역 트랙: 자막 행이 없고 Translation 행에 텍스트가 산다 —
            # 번역 검수의 찾기·바꾸기도 같은 엔드포인트로 (사용자 요청)
            from ..db import Translation

            ko_ids = session.exec(
                select(Segment.id).where(Segment.job_id == job.id, Segment.lang == "ko")
            ).all()
            trs = (
                session.exec(
                    select(Translation).where(
                        Translation.segment_id.in_(ko_ids), Translation.lang == lang
                    )
                ).all()
                if ko_ids
                else []
            )
            for tr in trs:
                n = tr.text.count(find)
                if not n:
                    continue
                matches += n
                seg_hits += 1
                if body.apply:
                    tr.text = tr.text.replace(find, body.replace)
                    tr.edited = True  # 사람 손 = 자동 재번역이 못 덮게 보호
                    session.add(tr)
            if body.apply and seg_hits:
                session.commit()
            return {"matches": matches, "segments": seg_hits, "applied": body.apply}
        for seg in segs:
            work = seg.text_final or seg.text_llm or seg.text_whisper
            n = work.count(find)
            if not n:
                continue
            matches += n
            seg_hits += 1
            if body.apply:
                seg.text_final = work.replace(find, body.replace)
                session.add(seg)
        if body.apply and seg_hits:
            job.status, job.updated_at = "reviewing", utcnow()
            session.add(job)
            session.commit()
    return {"matches": matches, "segments": seg_hits, "applied": body.apply}


@app.post("/api/jobs/{video_id}/segments/restore-rows")
def restore_rows(video_id: str, body: RestoreRowsBody, lang: str = "ko") -> list[dict]:
    """Undo ONE editor operation by restoring only the rows it touched.

    Replaces the old whole-track snapshot restore: that deleted and reinserted
    every segment of the track, so one reviewer's undo silently wiped whatever
    a concurrent reviewer had just edited elsewhere in the same video. This
    endpoint upserts the operation's before-rows and deletes the rows the
    operation created — other rows are never rewritten.

    idx is then renormalized across the track (ordered by start) because
    split/merge/delete shift the tail and _next/_previous_segment require a
    dense idx sequence.
    """
    if not body.upsert and not body.delete_ids:
        raise HTTPException(400, "empty undo step")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")

        # rows created by the undone op (e.g. split's right half) — delete their
        # translations too: Segment.id is a reused rowid, an orphan would
        # reattach to an unrelated cue later (same protection as delete_segment)
        if body.delete_ids:
            own_ids = set(
                session.exec(
                    select(Segment.id).where(
                        Segment.job_id == job.id,
                        Segment.lang == lang,
                        Segment.id.in_(body.delete_ids),
                    )
                ).all()
            )
            if own_ids:
                session.exec(
                    sql_delete(Translation).where(Translation.segment_id.in_(own_ids))
                )
                session.exec(sql_delete(Segment).where(Segment.id.in_(own_ids)))

        for snap in body.upsert:
            row = session.get(Segment, snap.id) if snap.id is not None else None
            if row is not None and (row.job_id != job.id or row.lang != lang):
                raise HTTPException(400, "snapshot row belongs to another track")
            if row is None:
                # the op deleted this row (delete/merge undo) — reinsert with
                # its original id so surviving translations stay attached
                row = Segment(id=snap.id, job_id=job.id, lang=lang, idx=snap.idx)
            row.idx = snap.idx
            row.start = round(max(0.0, snap.start), 3)
            row.end = round(max(snap.start + 0.1, snap.end), 3)
            row.text_whisper = snap.text_whisper
            row.text_youtube = snap.text_youtube
            row.text_llm = snap.text_llm
            row.text_final = snap.text_final
            row.flagged = snap.flagged
            row.llm_uncertain = snap.llm_uncertain
            row.reviewed = snap.reviewed
            row.edited = snap.edited
            row.low_conf = snap.low_conf
            row.review_flag = snap.review_flag
            session.add(row)
        session.flush()

        # renormalize idx by time order (segments never overlap — every timing
        # op clamps at the neighbour, so start order == cue order)
        track = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.start, Segment.end, Segment.id)
        ).all()
        for i, s in enumerate(track):
            if s.idx != i:
                s.idx = i
                session.add(s)

        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()

        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.idx)
        ).all()
        return [s.model_dump() for s in segs]


@app.put("/api/segments/{segment_id}")
def update_segment(segment_id: int, body: SegmentUpdate) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        if body.text_final is not None:
            # on a forked translation track, a text change is a human edit —
            # record it so unfork can keep it protected (vs copied machine text)
            if seg.lang != "ko" and body.text_final.strip() != (seg.text_final or "").strip():
                seg.edited = True
            seg.text_final = body.text_final
        # independent resize (subtitle-editor convention): a dragged edge moves
        # only THIS cue and is clamped at the neighbour — never pushes it.
        # Shrinking opens a gap; growing stops at the neighbour's wall (no
        # overlap). The linked "move the shared wall" behaviour lives only in the
        # boundary-prev/next endpoints (여기서 시작/넘김 buttons).
        if body.start is not None:
            prev = _previous_segment(session, seg)
            lo = prev.end if prev is not None else 0.0
            seg.start = round(min(max(body.start, lo), seg.end - 0.1), 3)
        if body.end is not None:
            nxt = _next_segment(session, seg)
            hi = nxt.start if nxt is not None else body.end
            seg.end = round(max(min(body.end, hi), seg.start + 0.1), 3)
        if body.reviewed is not None:
            seg.reviewed = body.reviewed
            # confirming a cue resolves its 잘 안 들림/보류 marker (ADR-0009)
            if body.reviewed:
                seg.review_flag = ""
        if body.review_flag is not None:
            if body.review_flag not in ("", "hold"):
                raise HTTPException(400, "review_flag must be '' or 'hold'")
            seg.review_flag = body.review_flag
        session.add(seg)
        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
        session.refresh(seg)
        return _seg_payload(seg)


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
            Segment.lang == seg.lang,
            Segment.idx == seg.idx + 1,
        )
    ).first()


def _previous_segment(session, seg: Segment) -> Segment | None:
    return session.exec(
        select(Segment).where(
            Segment.job_id == seg.job_id,
            Segment.lang == seg.lang,
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

        # shift the tail to make room at idx+1 (same lang track only)
        tail = session.exec(
            select(Segment).where(
                Segment.job_id == seg.job_id,
                Segment.lang == seg.lang,
                Segment.idx > seg.idx,
            )
        ).all()
        for t in tail:
            t.idx += 1
            session.add(t)

        old_end = seg.end
        seg.text_final = left
        seg.end = mid
        session.add(seg)
        right_seg = Segment(
            job_id=seg.job_id,
            lang=seg.lang,
            idx=seg.idx + 1,
            start=mid,
            end=old_end,
            # machine texts stay on the left piece; diff-noise from the
            # split is filtered by feedback.extract_pairs' size cap
            text_final=right,
            flagged=seg.flagged,
            llm_uncertain=seg.llm_uncertain,
            # both halves derive from the same (possibly edited) text — carry
            # the edited flag so a forked human edit stays protected
            edited=seg.edited,
        )
        session.add(right_seg)
        # stale translations regenerate via source_hash on next export
        session.commit()
        session.refresh(seg)
        session.refresh(right_seg)
        # affected rows so the client patches locally instead of refetching the
        # whole track (also gives undo the created row's id)
        return {"segments": [_seg_payload(seg), _seg_payload(right_seg)]}


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
        seg.edited = seg.edited or nxt.edited  # preserve forked human-edit protection
        seg.reviewed = False
        session.add(seg)

        # Move nxt's translations onto the surviving segment instead of leaving
        # them as orphans. Orphans are NOT safe: Segment.id is a plain rowid with
        # no AUTOINCREMENT, so SQLite reuses nxt.id on the next insert (split/
        # fork) and the dead translation would reattach to an unrelated cue and
        # export as its translation. Re-pointing keeps reviewed work (the merged
        # Korean differs, so get_translations flags it stale for a re-check);
        # if the survivor already has that language, its own row wins.
        seg_langs = {
            t.lang
            for t in session.exec(
                select(Translation).where(Translation.segment_id == seg.id)
            ).all()
        }
        for tr in session.exec(
            select(Translation).where(Translation.segment_id == nxt.id)
        ).all():
            if tr.lang in seg_langs:
                session.delete(tr)
            else:
                tr.segment_id = seg.id
                session.add(tr)
        nxt_id = nxt.id
        session.delete(nxt)
        tail = session.exec(
            select(Segment).where(
                Segment.job_id == seg.job_id,
                Segment.lang == seg.lang,
                Segment.idx > seg.idx + 1,
            )
        ).all()
        for t in tail:
            t.idx -= 1
            session.add(t)
        session.commit()
        session.refresh(seg)
        return {"segments": [_seg_payload(seg)], "deleted_id": nxt_id}


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
        changed = [seg] if prev is None else [prev, seg]
        for s in changed:
            session.refresh(s)
        return {"segments": [_seg_payload(s) for s in changed]}


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
        changed = [seg] if nxt is None else [seg, nxt]
        for s in changed:
            session.refresh(s)
        return {"segments": [_seg_payload(s) for s in changed]}


@app.post("/api/segments/{segment_id}/edge-drag")
def edge_drag(segment_id: int, which: str, body: BoundaryBody) -> dict:
    """Drag one edge of a cue with hybrid neighbour behaviour.

    Moves the edge freely while it sits in a gap, but once it crosses the
    neighbour's wall the neighbour is PUSHED along (dragging a start earlier than
    the previous cue's end drags that end back too; dragging an end past the next
    cue's start drags that start forward). This is the timeline-strip drag: it
    unifies the independent-resize and the linked "여기서 시작/넘김" behaviours so a
    contiguous boundary is always adjustable.
    """
    if which not in ("start", "end"):
        raise HTTPException(400, "which must be 'start' or 'end'")
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")

        changed = [seg]
        if which == "start":
            hi = seg.end - 0.1  # can't cross this cue's own end
            t = min(body.time, hi)
            prev = _previous_segment(session, seg)
            if prev is not None and t < prev.end:
                # crossed into the previous cue — push its end back with us
                t = round(min(max(t, prev.start + 0.1), hi), 3)
                prev.end = t
                session.add(prev)
                changed.insert(0, prev)
            else:
                t = round(max(t, 0.0), 3)  # free in the gap before prev.end
            seg.start = t
        else:  # end
            lo = seg.start + 0.1
            t = max(body.time, lo)
            nxt = _next_segment(session, seg)
            if nxt is not None and t > nxt.start:
                # crossed into the next cue — push its start forward with us
                t = round(min(max(t, lo), nxt.end - 0.1), 3)
                nxt.start = t
                session.add(nxt)
                changed.append(nxt)
            else:
                t = round(t, 3)  # free in the gap after this end
            seg.end = t

        session.add(seg)
        job = session.get(Job, seg.job_id)
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
        for s in changed:
            session.refresh(s)
        return {"segments": [_seg_payload(s) for s in changed]}


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
        session.refresh(seg)
        session.refresh(nxt)
        return {"segments": [_seg_payload(seg), _seg_payload(nxt)]}


@app.delete("/api/segments/{segment_id}")
def delete_segment(segment_id: int) -> dict:
    with get_session() as session:
        seg = session.get(Segment, segment_id)
        if seg is None:
            raise HTTPException(404, "segment not found")
        job_id, idx, lang = seg.job_id, seg.idx, seg.lang
        # delete this segment's translations — do NOT orphan them: Segment.id is
        # a reused rowid (no AUTOINCREMENT), so a later insert would reattach the
        # dead translation to an unrelated cue. Deleting a cue drops its
        # translations (an explicit user action, unlike a merge).
        session.exec(sql_delete(Translation).where(Translation.segment_id == seg.id))
        session.delete(seg)
        tail = session.exec(
            select(Segment).where(
                Segment.job_id == job_id, Segment.lang == lang, Segment.idx > idx
            )
        ).all()
        for t in tail:
            t.idx -= 1
            session.add(t)
        session.commit()
    return {"deleted_id": segment_id}


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
        # a forked language has its own segments (own structure/timing/text);
        # otherwise fall back to the Korean track + cached translation
        forked = lang != "ko" and (
            session.exec(
                select(Segment.id).where(Segment.job_id == job.id, Segment.lang == lang)
            ).first()
            is not None
        )
        read_lang = lang if forked else "ko"
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == read_lang)
            .order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]
        title = job.title

    if stage == "best":
        # per-segment best: final > llm > whisper, so a half-reviewed job
        # still exports every segment
        for d in seg_dicts:
            d["text_export"] = d["text_final"] or d["text_llm"] or d["text_whisper"]
        key = "text_export"
    elif forked:
        # a forked track only populates text_final (no whisper/llm stages), so a
        # stage=whisper/llm request would map to an all-empty column and export a
        # blank .srt. Always read text_final for forked tracks.
        key = "text_final"
    elif stage in key_map:
        key = key_map[stage]
    else:
        raise HTTPException(400, f"unknown stage {stage}")

    if lang != "ko" and not forked:
        from ..pipeline.translate import LANGUAGES, translate_segments

        if lang not in LANGUAGES:
            raise HTTPException(400, f"unsupported language {lang}")
        # always translate from the BEST Korean text (final>llm>whisper),
        # independent of the requested export `stage`. Keying the translation
        # cache to a stage-specific text (e.g. stage=whisper) would overwrite
        # the canonical best-text translation, then read back as stale and
        # force a needless re-translation on the next best export.
        for d in seg_dicts:
            d["text_ko_best"] = d["text_final"] or d["text_llm"] or d["text_whisper"]
        translated = translate_segments(seg_dicts, "text_ko_best", lang)
        for d in seg_dicts:
            d["text_export_t"] = translated.get(d["id"], "")
        key = "text_export_t"

    out_dir = JOBS_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = to_srt(seg_dicts, key, out_dir / f"{video_id}.{stage}.{lang}.srt", lang=lang)
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


# one full-track translation at a time per (video, lang). In-memory is enough:
# the app runs as a single Railway instance, and this only guards the button.
_translate_running: set[tuple[str, str]] = set()
_translate_running_guard = threading.Lock()


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _exclusive(key: tuple[str, str], skip: bool = False):
    """긴 변이 작업의 이중 실행 방지 — 예외 포함 모든 경로에서 잠금 해제."""
    if skip:
        yield
        return
    with _translate_running_guard:
        if key in _translate_running:
            raise HTTPException(409, "같은 작업이 이미 진행 중입니다 — 잠시 후 다시 시도하세요.")
        _translate_running.add(key)
    try:
        yield
    finally:
        with _translate_running_guard:
            _translate_running.discard(key)


@app.post("/api/jobs/{video_id}/translate")
def make_translations(
    request: Request, video_id: str, lang: str, batch: int = 0
) -> dict:
    """Generate (context-aware, cached) translations for every segment.

    Admin-only: a 2h video is ~25 Claude calls, and translation is a distinct
    post-review phase — reviewers do Korean review, not translation
    (사용자 결정 2026-07-15, 비용 통제). Gated on the Korean review being
    complete — translating a draft wastes API cost and forces re-translation
    after the Korean is fixed.

    [WH-CHANGE v0.5.2 | FIX | 2026-07-14 | CHG-20260714-009]
    Reason: a 2h video (~1500 cues) is ~25 sequential Claude calls; as one
      synchronous request the Railway proxy times out with a 502 and nothing
      is committed. `batch` translates only that many uncached cues per
      request (commit included), so the frontend loops short requests and
      shows progress; a duplicate click 409s instead of double-spending.
    Related: CHANGELOG CHG-20260714-009.
    """
    from ..pipeline.translate import LANGUAGES, translate_segments

    _require_admin(request)
    if lang == "ko" or lang not in LANGUAGES:
        raise HTTPException(400, f"unsupported language {lang}")

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
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

    # translation calls the Claude API; without a key it would raise and FastAPI
    # would return a plain-text 500 that the frontend can't parse as JSON.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            503,
            "번역 기능이 이 서버에 아직 설정되지 않았습니다(ANTHROPIC_API_KEY 없음). "
            "관리자에게 문의하세요.",
        )
    key = (video_id, lang)
    with _translate_running_guard:
        if key in _translate_running:
            raise HTTPException(
                409, "이 영상의 번역이 이미 진행 중입니다 — 잠시 후 다시 시도하세요."
            )
        _translate_running.add(key)
    try:
        translated = translate_segments(
            seg_dicts, "ko", lang, limit=batch if batch > 0 else None
        )
    except HTTPException:
        raise
    except Exception as e:  # API/auth/network error -> clean JSON, not a 500
        raise HTTPException(502, f"번역 API 오류: {e}")
    finally:
        with _translate_running_guard:
            _translate_running.discard(key)
    n_sources = sum(1 for d in seg_dicts if (d["ko"] or "").strip())
    remaining = max(0, n_sources - len(translated))
    return {
        "lang": lang,
        "translated": len(translated),
        "segments": len(seg_dicts),
        "remaining": remaining,
        "done": remaining == 0,
    }


@app.get("/api/jobs/{video_id}/translations")
def get_translations(video_id: str, lang: str) -> list[dict]:
    """KO + translation per segment, for the translation review view."""
    from ..pipeline.translate import _hash

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        # scope to THIS job's segments (was scanning every video's rows for lang)
        rows = session.exec(
            select(Translation).where(
                Translation.segment_id.in_([s.id for s in segs]),
                Translation.lang == lang,
            )
        ).all()
        by_seg = {t.segment_id: t for t in rows}
        out = []
        for s in segs:
            t = by_seg.get(s.id)
            ko = _best_ko(s)
            # stale = the Korean changed after this translation was made, so the
            # translation is now for the OLD text and needs a re-translate/re-check
            stale = bool(t and t.source_hash and t.source_hash != _hash(ko.strip()))
            out.append(
                {
                    "segment_id": s.id,
                    "idx": s.idx,
                    "start": s.start,
                    "end": s.end,
                    "ko": ko,
                    "text": t.text if t else "",
                    "reviewed": t.reviewed if t else False,
                    "edited": t.edited if t else False,
                    "has_translation": t is not None,
                    "stale": stale,
                }
            )
        return out


class TranslationUpdate(BaseModel):
    text: str | None = None
    reviewed: bool | None = None


@app.put("/api/translations/{segment_id}")
def update_translation(segment_id: int, lang: str, body: TranslationUpdate) -> dict:
    # local import to match the module's convention (translate helpers are
    # imported where used); without it the text-change branch NameError'd →
    # every manual translation edit 500'd (CHG-20260714-003 during-work find)
    from ..pipeline.translate import _hash

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
            # stamp the Korean source hash so a LATER Korean edit correctly
            # surfaces stale=True. A from-scratch human translation would
            # otherwise keep source_hash="" and never flag as stale (get_
            # translations short-circuits on empty hash), silently staying
            # attached to Korean it no longer matches.
            t.source_hash = _hash(_best_ko(seg).strip())
        if body.reviewed is not None:
            t.reviewed = body.reviewed
        # never persist an empty phantom row (blank text, reviewed toggled on an
        # untranslated cue): it would count toward progress and export nothing.
        if not (t.text or "").strip():
            if t.id is not None:
                session.delete(t)
            session.commit()
            return {"segment_id": segment_id, "text": "", "reviewed": False}
        session.add(t)
        session.commit()
        session.refresh(t)
        return {"segment_id": segment_id, "text": t.text, "reviewed": t.reviewed}


# [WH-CHANGE v0.4.1 | FEAT | 2026-07-14 | CHG-20260714-003]
# Reason: 번역 후 한국어를 재분할/재타이밍하면 그 언저리 여러 셀이 한꺼번에
#         stale/빈칸이 됨 — 클릭한 셀만이 아니라 그 주변의 연속된 stale·빈
#         셀들을 묶어 한 번의 문맥 번역으로 채움 (셀별 번역은 문장 흐름이 끊김).
# Related: ADR-0006 / CHANGELOG CHG-20260714-003 (CHG-20260713-010 확장).
@app.post("/api/jobs/{video_id}/retranslate")
def retranslate_segment(request: Request, video_id: str, lang: str, segment_id: int) -> dict:
    """Re-translate the clicked cue PLUS the contiguous run of stale/empty
    neighbours around it, in one context-aware call.

    Cluster rule: starting at the clicked cue, expand left/right while the
    neighbour needs work — no translation / blank text, or stale (source_hash
    no longer matches the current Korean) and not human-edited. Human-edited
    (`edited`) and fresh rows stop the expansion; the clicked cue itself is
    always included (explicit request wins even over an edited row). Capped at
    6 cues each side. Every re-translated row is written with source_hash =
    current Korean, reviewed=False, edited=False — stale clears, 재확인 대상.
    """
    from ..pipeline.translate import LANGUAGES, _hash, retranslate_span

    _require_admin(request)  # 번역은 관리자 전용 (비용 통제, 사용자 결정 2026-07-15)
    if lang == "ko" or lang not in LANGUAGES:
        raise HTTPException(400, f"unsupported language {lang}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            503,
            "번역 기능이 이 서버에 아직 설정되지 않았습니다(ANTHROPIC_API_KEY 없음). "
            "관리자에게 문의하세요.",
        )
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        i = next((k for k, s in enumerate(segs) if s.id == segment_id), None)
        if i is None:
            raise HTTPException(404, "segment not found on the Korean track")
        if not _best_ko(segs[i]).strip():
            raise HTTPException(400, "빈 원문은 번역할 수 없습니다")

        tr_rows = session.exec(
            select(Translation).where(
                Translation.segment_id.in_([s.id for s in segs]),
                Translation.lang == lang,
            )
        ).all()
        by_seg = {t.segment_id: t for t in tr_rows}

        def needs_work(seg: Segment) -> bool:
            """빈칸이거나 stale(사람이 손대지 않은)이면 클러스터에 포함."""
            if not _best_ko(seg).strip():
                return False  # 원문이 비면 번역할 게 없음
            t = by_seg.get(seg.id)
            if t is None or not (t.text or "").strip():
                return True  # 재분할로 생긴 빈 셀
            if t.edited:
                return False  # 사람이 쓴 번역은 절대 자동으로 안 건드림
            return t.source_hash != _hash(_best_ko(seg).strip())  # stale

        lo = i
        while lo > 0 and i - (lo - 1) <= 6 and needs_work(segs[lo - 1]):
            lo -= 1
        hi = i
        while hi < len(segs) - 1 and (hi + 1) - i <= 6 and needs_work(segs[hi + 1]):
            hi += 1

        cluster = [s for s in segs[lo : hi + 1] if _best_ko(s).strip()]
        # 클릭한 셀은 항상 포함; 이웃은 손볼 필요가 있는 것만
        cluster = [s for s in cluster if s.id == segment_id or needs_work(s)]
        items = [
            (
                s.id,
                _best_ko(s).strip(),
                max(10, int(17 * max(0.5, s.end - s.start))),
            )
            for s in cluster
        ]
        ctx_before = [_best_ko(s) for s in segs[max(0, lo - 4) : lo]]
        ctx_after = [_best_ko(s) for s in segs[hi + 1 : hi + 5]]
        ko_by_id = {s.id: _best_ko(s).strip() for s in cluster}

    try:
        translated = retranslate_span(items, ctx_before, ctx_after, lang)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"번역 API 오류: {e}")
    if not translated.get(segment_id, "").strip():
        raise HTTPException(502, "번역 결과가 비어 있습니다. 다시 시도해 주세요.")

    updated: list[dict] = []
    with get_session() as session:
        for seg_id, new_text in translated.items():
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
                    text=new_text,
                    source_hash=_hash(ko_by_id[seg_id]),
                    reviewed=False,
                    edited=False,
                )
            )
            updated.append(
                {"segment_id": seg_id, "text": new_text, "reviewed": False, "stale": False}
            )
        session.commit()
    return {"updated": updated, "count": len(updated)}


@app.post("/api/jobs/{video_id}/repair-stt")
def repair_stt(request: Request, video_id: str) -> dict:
    """Recover segments where whisper hallucinated its initial_prompt.

    Works on segments already in the DB (e.g. videos processed before the
    crosscheck-time echo filter existed). Zero API cost: where the segment
    text is a prompt echo and a YouTube caption exists for that span, we
    replace the working text with the YouTube caption and re-open it for
    review. Segments with no caption are left for the human. Admin-only,
    except on practice videos: the tutorial teaches everyone to press it,
    it costs nothing (YouTube captions only), and clones are throwaway.
    """
    # [WH-CHANGE v0.9.14 | FIX | 2026-07-15 | CHG-20260715-038]
    # Reason: 연습 6 나레이션이 복구·채우기를 직접 눌러보게 하는데 관리자
    #   전용 403이 떴음 — practice job(기준본/클론)은 예외 허용.
    # Related: CHANGELOG CHG-20260715-038.
    with get_session() as _s:
        _job = _s.exec(select(Job).where(Job.video_id == video_id)).first()
        _is_practice = bool(_job and _job.practice)
    if not _is_practice:
        _require_admin(request)
    from ..glossary import whisper_prompt
    from ..pipeline.noise import (
        cascade_indices,
        is_known_prompt_leak,
        is_prompt_echo,
    )

    prompt = whisper_prompt()
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        # never alter a finished video: the human already finalized it (and may
        # have deliberately omitted spans). Inserting YouTube gap segments would
        # un-complete their review.
        if segs and all(s.reviewed for s in segs):
            raise HTTPException(
                409, "한국어 검수가 완료된 영상은 복구/보충하지 않습니다."
            )
        bases = [(s.text_final or s.text_llm or s.text_whisper) for s in segs]
        # prompt-agnostic: consecutive-duplicate cascade is the reliable
        # hallucination signature even after the live prompt changed
        cascade = cascade_indices(bases)
        repaired = 0
        no_caption = 0
        for i, seg in enumerate(segs):
            base = bases[i]
            leaked = (
                i in cascade
                or is_known_prompt_leak(base)
                or is_prompt_echo(base, prompt)
            )
            if not leaked:
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

        # gap-fill: cover time spans NO segment occupies — above all the dropped
        # opening (whisper often starts well after the speaker did). Pull those
        # spans from the YouTube captions so subtitle #1 begins where speech
        # begins, and the reviewer isn't stuck unable to prepend a cell.
        filled = 0
        cap_files = sorted((JOBS_DIR / video_id).glob("*.json3"))
        if cap_files:
            from ..pipeline.crosscheck import parse_json3_captions, youtube_gap_rows

            caps = parse_json3_captions(cap_files[0])
            live = session.exec(
                select(Segment).where(Segment.job_id == job.id, Segment.lang == "ko")
            ).all()
            existing_rows = [
                {
                    "start": s.start,
                    "end": s.end,
                    "text_llm": s.text_final or s.text_llm,
                    "text_whisper": s.text_whisper,
                }
                for s in live
            ]
            for row in youtube_gap_rows(existing_rows, caps):
                # row already carries text_whisper="" + YouTube-seeded working
                # text (honest: whisper heard nothing in this span)
                session.add(Segment(job_id=job.id, lang="ko", idx=0, reviewed=False, **row))
                filled += 1

        # renumber idx by chronological start so the first cell is the earliest
        if repaired or filled:
            session.flush()
            ordered = session.exec(
                select(Segment)
                .where(Segment.job_id == job.id, Segment.lang == "ko")
                .order_by(Segment.start)
            ).all()
            for i, s in enumerate(ordered):
                if s.idx != i:
                    s.idx = i
                    session.add(s)
            job.status, job.updated_at = "reviewing", utcnow()
            session.add(job)
        session.commit()
    return {"repaired": repaired, "no_caption": no_caption, "filled": filled}


@app.get("/api/jobs/{video_id}/words")
def get_words(video_id: str) -> dict:
    """Per-word timestamps from the cached STT run (read-only).

    Powers the editor's speech map: instead of a waveform (the YouTube iframe
    gives us no audio), we draw each recognized word as a block on a mini
    timeline so the reviewer can *see* where speech and silence are and snap
    subtitle boundaries onto real word edges. Empty list for seed-imported
    videos that never ran local STT.
    """
    import json as _json

    raw = _load_stt(video_id)
    if raw is None:
        return {"words": []}
    words = [
        {"start": float(w["start"]), "end": float(w["end"]), "word": w["word"]}
        for s in raw
        for w in s.get("words", [])
        if float(w["end"]) > float(w["start"])
    ]
    words.sort(key=lambda w: w["start"])
    return {"words": words}


@app.post("/api/jobs/{video_id}/tighten")
def tighten_timing(video_id: str) -> dict:
    """Snap every subtitle's start/end to the words actually spoken in its span.

    Trims the leading/trailing silence that made a subtitle linger on screen
    through a quiet stretch: it now appears when the speaker starts and clears
    when they stop, leaving true gaps between subtitles. Non-destructive — only
    start/end change; text, review status and segment count are untouched. Uses
    the cached per-word timestamps in stt.json, so it costs no GPU/API and is
    safe to run at any time, even on a finished video.
    """
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        raw = _load_stt(video_id, session)
        if raw is None:
            raise HTTPException(
                400,
                "이 영상은 음성인식 원본(stt.json)이 없어 타이밍을 다듬을 수 없습니다.",
            )
        words: list[tuple[float, float]] = []
        for s in raw:
            for w in s.get("words", []):
                st, en = float(w["start"]), float(w["end"])
                if en > st:
                    words.append((st, en))
        words.sort()

        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.start)
        ).all()
        tightened = 0
        min_dur = 0.30  # never collapse a cue below this so it stays readable
        for seg in segs:
            # assign each spoken word to exactly one segment by its midpoint,
            # then clamp the segment to the first/last word it actually contains
            inside = [
                (st, en) for (st, en) in words if seg.start <= (st + en) / 2 < seg.end
            ]
            if not inside:
                continue  # e.g. a YouTube gap-fill row (whisper heard nothing)
            ns = min(st for st, _ in inside)
            ne = max(en for _, en in inside)
            if ne - ns < min_dur:
                ne = ns + min_dur
            if abs(ns - seg.start) > 0.05 or abs(ne - seg.end) > 0.05:
                seg.start, seg.end = ns, ne
                session.add(seg)
                tightened += 1
        session.commit()
    return {"tightened": tightened, "total": len(segs)}


# [WH-CHANGE v0.3.0 | FEAT | 2026-07-13 | CHG-20260713-006]
# Reason: 타이밍 검수 모드의 "자동 정리" — 검수자가 손대기 전에 기계가 할 수 있는
#         타이밍 작업(발화 스냅·과길이 분할·읽기속도 연장)을 한 번에 처리.
# Related: ADR-0009 / CHANGELOG CHG-20260713-006.
@app.post("/api/jobs/{video_id}/auto-timing")
def auto_timing(video_id: str, lang: str = "ko") -> dict:
    """One-shot timing cleanup for a track (ADR-0009): snap every cue to its
    spoken words, split cues that overflow the 2-line/7s budget at their widest
    internal pause, and extend too-fast cues into the following silence.

    Deterministic, no GPU/API (uses the cached per-word timestamps). Ouroboros
    safety: absorb runs FIRST — splitting moves machine text onto the left
    piece only, so absorbing after a mass split would lose correction pairs.
    reviewed/review_flag survive a split (the words are unchanged, only the
    cut), so a text-complete video stays complete. The response carries the
    before-rows and created ids so the editor can push one undo step
    (restore-rows) — Alt+Z reverts the whole cleanup.
    """
    # [WH-CHANGE v0.9.59 | FIX | 2026-07-17 | CHG-20260717-089]
    # Reason: 자동 정리 폐지(ADR-0012). 프론트에서 버튼만 빼면 **캐시된 옛 탭**은
    #   그대로 이 엔드포인트를 부를 수 있고(실제로 옛 번들이 도는 사례 관측),
    #   그러면 검수 끝난 영상의 98%가 재작성된다. 서버에서 막는다. 연습(practice)
    #   클론은 나레이션이 아직 이 버튼을 지시하므로 재렌더 전까지 허용 —
    #   샌드박스라 실데이터에 영향 없음.
    # Related: ADR-0012, CHANGELOG CHG-20260717-089.
    from ..pipeline.retime import plan_track

    with get_session() as session:
        guard_job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if guard_job is None:
            raise HTTPException(404, f"no job for {video_id}")
        if not guard_job.practice:
            raise HTTPException(
                410,
                "타이밍 자동 정리는 없어졌습니다 — 확실하지 않은 곳까지 건드려서 "
                "쓰지 않기로 했어요. 화면을 새로고침(Ctrl+Shift+R) 해주세요. "
                "타이밍은 ✂ 무음 다듬기와 Alt+[ · Alt+] · Alt+\\ 로 손봐주세요.",
            )

    if lang == "ko":
        # learning is ko-source only; a forked translation track has no
        # machine↔final diff to absorb
        from ..feedback import absorb_job

        try:
            absorb_job(video_id)
        except ValueError as e:
            raise HTTPException(404, str(e))

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        raw = _load_stt(video_id, session)
        if raw is None:
            raise HTTPException(
                400,
                "이 영상은 음성인식 원본(stt.json)이 없어 자동 정리를 할 수 없습니다.",
            )
        words: list[tuple[float, float]] = []
        for s in raw:
            for w in s.get("words", []):
                st, en = float(w["start"]), float(w["end"])
                if en > st:
                    words.append((st, en))
        words.sort()

        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.start, Segment.end, Segment.id)
        ).all()
        if not segs:
            raise HTTPException(400, "이 트랙엔 자막이 없습니다.")

        cues = [
            {"start": s.start, "end": s.end, "text": _display_text(s)} for s in segs
        ]
        plans = plan_track(cues, words)

        before: list[dict] = []
        changed: list[Segment] = []
        created: list[Segment] = []
        tightened = split_count = 0
        for seg, pieces in zip(segs, plans):
            first = pieces[0]
            moved = abs(first.start - seg.start) > 0.01 or abs(first.end - seg.end) > 0.01
            if len(pieces) == 1 and not moved:
                continue
            before.append(seg.model_dump())
            if moved:
                tightened += 1
            seg.start, seg.end = first.start, first.end
            if len(pieces) > 1:
                split_count += 1
                # same semantics as the split endpoint: machine texts stay on
                # the left piece; each right piece carries only the final text
                seg.text_final = pieces[0].text or ""
                for p in pieces[1:]:
                    created.append(
                        Segment(
                            job_id=job.id,
                            lang=lang,
                            idx=seg.idx,  # renumbered below
                            start=p.start,
                            end=p.end,
                            text_final=p.text or "",
                            flagged=seg.flagged,
                            llm_uncertain=seg.llm_uncertain,
                            # the words were human-confirmed; only the cut is
                            # new — keep the review state so ko_complete (and
                            # the translation gate) don't regress (ADR-0009)
                            reviewed=seg.reviewed,
                            edited=seg.edited,
                            review_flag=seg.review_flag,
                        )
                    )
            session.add(seg)
            changed.append(seg)
        for row in created:
            session.add(row)
        session.flush()

        # dense idx by time order (same rule as restore_rows)
        ordered = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.start, Segment.end, Segment.id)
        ).all()
        for i, s in enumerate(ordered):
            if s.idx != i:
                s.idx = i
                session.add(s)

        if changed or created:
            job.status, job.updated_at = "reviewing", utcnow()
            session.add(job)
        session.commit()
        for s in changed + created:
            session.refresh(s)
        return {
            "segments": [_seg_payload(s) for s in changed + created],
            "created_ids": [s.id for s in created],
            "before": before,
            "tightened": tightened,
            "split": split_count,
        }


# [WH-CHANGE v0.3.2 | FEAT | 2026-07-13 | CHG-20260713-009]
# Reason: 내보내기 전 자동 점검(QC) + 선택적 AI 맞춤법 — 검수 끝났다고 믿고 받았는데
#         오탈자/빈 자막이 남는 사고 방지. QC는 순수 규칙(0원), 맞춤법만 API.
# Related: ADR-0009 / CHANGELOG CHG-20260713-009.
@app.get("/api/jobs/{video_id}/qc")
def qc_report(video_id: str, lang: str = "ko") -> dict:
    """Rule-based pre-export quality check for one track. No API cost.

    Returns per-category segment-id lists so the editor can jump straight to
    an offending cue. Categories mirror professional subtitle QC (Ooona/
    EZTitles): empty text, reading speed, 2-line char budget, implausible
    duration, doubled whitespace — plus this app's own review states
    (unreviewed, 잘 안 들림 hold).
    """
    from ..config import MAX_CHARS_PER_LINE, MAX_LINES, MAX_SEGMENT_SECONDS

    max_chars = MAX_CHARS_PER_LINE * MAX_LINES
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.idx)
        ).all()

    empty: list[int] = []
    too_fast: list[int] = []
    too_long_text: list[int] = []
    bad_duration: list[int] = []
    double_space: list[int] = []
    hold: list[int] = []
    unreviewed = 0
    for s in segs:
        text = _work_text(s)
        dur = s.end - s.start
        if not s.reviewed:
            unreviewed += 1
        if s.review_flag == "hold" and not s.reviewed:
            hold.append(s.id)
        if not text:
            empty.append(s.id)
            continue
        if _cps(s) > TOO_FAST_CPS:
            too_fast.append(s.id)
        if len(text) > max_chars:
            too_long_text.append(s.id)
        if dur < 0.35 or dur > MAX_SEGMENT_SECONDS + 0.05:
            bad_duration.append(s.id)
        if "  " in text:
            double_space.append(s.id)

    issues = (
        len(empty)
        + len(too_fast)
        + len(too_long_text)
        + len(bad_duration)
        + len(double_space)
        + len(hold)
    )
    return {
        "total": len(segs),
        "unreviewed": unreviewed,
        "issues": issues,
        "empty": empty,
        "too_fast": too_fast,
        "too_long_text": too_long_text,
        "bad_duration": bad_duration,
        "double_space": double_space,
        "hold": hold,
    }


@app.post("/api/jobs/{video_id}/spellcheck")
def spellcheck(
    request: Request, video_id: str, lang: str = "ko", batch: int = 0
) -> dict:
    """AI 맞춤법 검사 (suggestions only — nothing is written here).

    Checks each cue's working text for spelling/spacing typos the reviewer
    introduced while editing; the correction stage already handled the machine
    draft. Korean-only (the prompt is ko-specific). Results are cached per
    exact text (LlmCache kind="spell"), so re-running re-bills only edited
    lines. The client applies accepted suggestions through the normal segment
    PUT, which keeps undo working.

    [WH-CHANGE v0.9.46 | SEC | 2026-07-16 | CHG-20260716-068]
    Reason: Claude API 사용 → 관리자 전용 (비용 통제). 사용자 정책 2026-07-16:
      검수자는 API 안 쓰는 도구만, API 도구(맞춤법·번역·초안)는 관리자만.
      기존엔 검수자에게 열려 있었음(CHG-041에서 번역만 막았었음).
    Related: CHANGELOG CHG-20260716-068.
    """
    _require_admin(request)
    if lang != "ko":
        raise HTTPException(400, "맞춤법 검사는 한국어 트랙만 지원합니다")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            503,
            "맞춤법 검사가 이 서버에 아직 설정되지 않았습니다(ANTHROPIC_API_KEY 없음). "
            "관리자에게 문의하세요.",
        )
    from ..pipeline.spellcheck import spellcheck_lines

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.idx)
        ).all()
        lines = [(s.id, _work_text(s)) for s in segs]
        idx_by_id = {s.id: s.idx for s in segs}
        start_by_id = {s.id: s.start for s in segs}
        text_by_id = dict(lines)

    try:
        # batch>0: 미캐시 줄을 그만큼만 처리하고 remaining 반환 — 프론트가
        # 반복 호출하며 진행률 표시 (긴 영상 타임아웃 방지)
        fixes, stats = spellcheck_lines(lines, limit=max(0, batch))
    except HTTPException:
        raise
    except Exception as e:  # API/auth/network error -> clean JSON, not a 500
        raise HTTPException(502, f"맞춤법 API 오류: {e}")

    suggestions = [
        {
            "segment_id": seg_id,
            "idx": idx_by_id.get(seg_id, 0),
            "start": start_by_id.get(seg_id, 0.0),
            "before": text_by_id.get(seg_id, ""),
            "after": fixed,
        }
        for seg_id, fixed in sorted(
            fixes.items(), key=lambda kv: idx_by_id.get(kv[0], 0)
        )
    ]
    return {"suggestions": suggestions, **stats}


@app.post("/api/jobs/{video_id}/fill-hanja")
def fill_hanja(
    video_id: str, lang: str = "ko", batch: int = 0, offset: int = 0, dry: int = 0
) -> dict:
    """강조 한자어 병기 채우기 — "얼굴 안 자" → "얼굴 안(顔) 자".

    [WH-CHANGE v0.9.25 | FEAT | 2026-07-15 | CHG-20260715-047]
    Reason: 강연에서 특별히 풀어 설명하는 한자(뜻+음+자 패턴, 불교 용어 등)는
      한자를 병기해 달라는 요청. 검수 완료 대본에서 채굴한 HanjaTerm 사전으로
      결정적 치환만 한다 — API 0원. 단일자는 (뜻,음) 짝이 일치할 때만(동음
      안전), 다자어는 2자 이상 단어 경계 일치 시. 이미 병기된 곳은 스킵.
      되돌리기용 before 행을 돌려준다 (auto-timing 패턴).
    Related: CHANGELOG CHG-20260715-047.

    [WH-CHANGE v0.9.26 | PERF | 2026-07-15 | CHG-20260715-048]
    Reason: (1) batch/offset — 긴 영상에서 한 요청이 오래 걸리면 진행 상황이
      안 보인다는 피드백. 맞춤법과 같은 배치 루프로 진행률을 낸다. remaining을
      돌려주면 클라이언트가 offset을 올려 이어간다. (2) 다자어 900+종을 행마다
      개별 re.sub 하면 re 모듈 패턴 캐시(512개)를 넘겨 행마다 재컴파일된다 —
      통합 alternation 패턴 1개로 사전 컴파일 (긴 표현 우선 순서 유지).
    Related: CHANGELOG CHG-20260715-048.

    [WH-CHANGE v0.9.27 | FEAT | 2026-07-15 | CHG-20260715-049]
    Reason: dry=1이면 DB를 건드리지 않고 before/after 제안만 돌려준다 —
      "어디에 채웠는지 보이고, 잘못된 병기는 빼고 적용하고 싶다"는 피드백.
      맞춤법 검사와 같은 제안-확인-선택 적용 흐름 (적용은 클라이언트가
      updateSegment로). suggestions는 dry 여부와 무관하게 항상 채운다.
    Related: CHANGELOG CHG-20260715-049.
    """
    import re as _re

    from ..db import HanjaTerm

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        terms = session.exec(select(HanjaTerm)).all()
        if not terms:
            raise HTTPException(409, "한자 사전이 비어 있습니다 — 관리자에게 문의")

        # 단일자: "뜻 음 자" 패턴 전용. 다자어: 단어 경계 일치 (긴 것 먼저).
        # 다자어는 흑판 특수어(tier=special)만 — 일반 한자어(불교·일본 등)는
        # 사전에 남아 있어도 자동 병기하지 않는다 (CHG-20260715-050).
        single = {(t.gloss, t.reading): t.hanja for t in terms if t.gloss}
        multi = {
            t.reading: t.hanja
            for t in terms
            if not t.gloss and len(t.reading) >= 2 and t.tier == "special"
        }
        # [WH-CHANGE v0.9.43 | FIX | 2026-07-16 | CHG-20260716-065]
        # Reason: 규칙 B가 뒤에 한글이 오면 매칭 안 해(?![가-힣]) 조사가 붙은
        #   대부분(신언서판으로·백궁에서·오온을)을 놓쳤다. 한국어 조사는 용어
        #   뒤에 직접 붙으므로, 알려진 조사를 선택적으로 흡수하고 그 뒤가 진짜
        #   경계(비한글)일 때만 병기한다. 조사 뒤 한글이 이어지면(백궁전) 매칭
        #   안 돼 긴 단어 오분리를 막는다. 미리보기(dry-run)라 오분리도 검토서 걸러짐.
        # Related: CHANGELOG CHG-20260716-065.
        # 긴 것 먼저(교대 매칭은 좌→우) — 조사 + 서술격(이다) + 하다동사 종결형.
        # 명사 뒤에 직접 붙는 것만: 조사(을/에서/으로), 서술격(이다/입니다),
        # 하다동사(수행하다·정진하세요). 뒤가 진짜 경계일 때만 병기하므로
        # 긴 단어(백궁전)는 분리되지 않는다.
        JOSA = (
            "으로부터|에서부터|에서만|에서는|에서도|으로써|으로서|으로는|으로도"
            "|이라고|이라는|이라도|이라면|이라서|에게서|한테서|에게로|입니다|이에요"
            "|이예요|이지만|이라|이란|이나|이야|이랑|이고|이며|이지|인데|이면|이니"
            "|이다|이었|였다|께서|에서|에게|한테|으로|처럼|보다|마다|부터|까지"
            "|조차|마저|밖에|만큼|라도|라서|에는|에도|에만|로는|로도"
            "|합니다|하세요|하시는|하시고|하는|하고|하며|하지|하면|하게|하기|하여"
            "|하다|한다|해서|해야|해도|했다|했고|했는데"
            "|은|는|이|가|을|를|와|과|의|에|로|도|만|께|야|아|랑|나|인"
        )
        multi_re = None
        if multi:
            alts = "|".join(
                _re.escape(r) for r in sorted(multi, key=len, reverse=True)
            )
            multi_re = _re.compile(
                rf"(?<![가-힣])({alts})((?:{JOSA})?)(?![가-힣(])"
            )
        seg_rows = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == lang)
            .order_by(Segment.idx)
        ).all()
        total = len(seg_rows)
        remaining = 0
        if batch > 0:
            remaining = max(0, total - offset - batch)
            seg_rows = seg_rows[offset : offset + batch]

        def fill(text: str) -> str:
            # 규칙 A: "얼굴 안 자" -> "얼굴 안(顔) 자" (이미 괄호 있으면 스킵)
            def sub_glyph(m: _re.Match) -> str:
                h = single.get((m.group(1), m.group(2)))
                return f"{m.group(1)} {m.group(2)}({h}) 자" if h else m.group(0)

            out = _re.sub(r"([가-힣]+) ([가-힣]) 자(?![가-힣(])", sub_glyph, text)
            # 규칙 B: 다자어 병기 — 용어(그룹1) 뒤 조사(그룹2)는 보존, 그 사이 병기
            if multi_re:
                out = multi_re.sub(
                    lambda m: f"{m.group(1)}({multi[m.group(1)]}){m.group(2)}", out
                )
            return out

        before: list[dict] = []
        changed: list[Segment] = []
        suggestions: list[dict] = []
        for s in seg_rows:
            cur = s.text_final or s.text_llm or ""
            if not cur or "(" in cur and cur.count("(") > 6:
                continue
            new = fill(cur)
            if new == cur:
                continue
            suggestions.append(
                {
                    "segment_id": s.id,
                    "idx": s.idx,
                    "start": s.start,
                    "before": cur,
                    "after": new,
                }
            )
            if dry:
                continue
            before.append(
                {"id": s.id, "text_final": s.text_final, "reviewed": s.reviewed}
            )
            if s.text_final:
                s.text_final = new
            else:
                s.text_llm = new
            session.add(s)
            changed.append(s)
        if not dry:
            session.commit()
        return {
            "changed": len(changed),
            "total": total,
            "remaining": remaining,
            "suggestions": suggestions,
            "before": before,
            "segments": [
                {
                    "id": s.id,
                    "text_final": s.text_final,
                    "text_llm": s.text_llm,
                }
                for s in changed
            ],
        }


class TimingDoneBody(BaseModel):
    done: bool


@app.post("/api/jobs/{video_id}/timing-done")
def set_timing_done(video_id: str, body: TimingDoneBody, lang: str = "ko") -> dict:
    """Mark (or unmark) a track's timing pass as human-confirmed.

    Separate from text review: a reviewer can finish all the words and still owe
    a timing pass. Timing is per-track — the Korean source uses Job.timing_done;
    a forked translation track (retimed independently, ADR-0006) uses its Track
    row so its timing state is tracked and shown per language.
    """
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        if lang == "ko":
            job.timing_done = body.done
            job.updated_at = utcnow()
            session.add(job)
        else:
            # only a forked track (own Segment rows) has independent timing
            has_fork = session.exec(
                select(Segment.id).where(
                    Segment.job_id == job.id, Segment.lang == lang
                )
            ).first()
            if has_fork is None:
                raise HTTPException(400, f"{lang} is not a forked track")
            track = session.exec(
                select(Track).where(Track.job_id == job.id, Track.lang == lang)
            ).first()
            if track is None:
                track = Track(job_id=job.id, lang=lang, forked=True)
            track.timing_done = body.done
            session.add(track)
        session.commit()
    return {"video_id": video_id, "lang": lang, "timing_done": body.done}


@app.post("/api/jobs/{video_id}/absorb")
def absorb(video_id: str, phase: str = "all") -> dict:
    """Ouroboros feedback: pull reviewed diffs into the corrections DB.

    phase: "all" (한 번에) 또는 extract → repair → propagate 를 순서대로.
    쪼개 부르면 UI가 단계별 진행률을 보여줄 수 있다 (CHG-20260716-076).
    """
    from ..feedback import ABSORB_PHASES, absorb_job

    if phase != "all" and phase not in ABSORB_PHASES:
        raise HTTPException(400, f"unknown phase: {phase}")
    try:
        return absorb_job(video_id, phase=phase)
    except ValueError as e:
        raise HTTPException(404, str(e))


class SrtImport(BaseModel):
    content: str
    filename: str = ""
    dry_run: bool = False


@app.post("/api/jobs/{video_id}/import-srt")
def import_srt(request: Request, video_id: str, body: SrtImport) -> dict:
    """Apply a human-reviewed .srt onto this video's Korean segments (admin).

    The .srt lines are aligned to the machine segments by time overlap and
    written as text_final (reviewed=True). This both marks the video done and
    creates the machine-draft -> human-final pairs the ouroboros learns from
    (corrections/glossary) and the STT fine-tune uses. dry_run=True returns a
    preview (which video, how many matched) WITHOUT writing, so a wrong-video
    drop can be cancelled before anything changes.
    """
    _require_admin(request)
    import srt as _srtlib

    try:
        subs = [s for s in _srtlib.parse(body.content) if s.content.strip()]
    except Exception as e:
        raise HTTPException(400, f".srt 파싱 실패: {e}")
    if not subs:
        raise HTTPException(400, ".srt에 자막이 없습니다.")

    # this endpoint writes the Korean SOURCE track (lang="ko"). Reject a
    # non-Korean .srt (e.g. an English translation dropped by mistake) — a
    # translation belongs to its own track, only after the Korean is reviewed.
    joined = " ".join(s.content for s in subs)
    hangul = sum(1 for ch in joined if "가" <= ch <= "힣")
    latin = sum(1 for ch in joined if "a" <= ch.lower() <= "z")
    if hangul + latin > 0 and hangul < latin:
        raise HTTPException(
            400,
            "한국어 자막(.srt)만 올릴 수 있어요. 영어 등 번역 자막은 한국어 검수가 "
            "끝난 뒤 해당 언어 트랙에서 지원할 예정입니다.",
        )

    # [WH-CHANGE v0.8.0 | FEAT | 2026-07-15 | CHG-20260715-020]
    # Reason: 사용자 확정 — 임포트되는 .srt는 이미 검수 완료된 결과물이므로
    #   기존 기계 분할에 텍스트만 채우는 게 아니라 **.srt의 큐 구조(분할·타이밍)
    #   그대로 갈아엎는다**. 기존 번역은 (텍스트 동일 + 시간 근접) 큐에 한해
    #   이어받아 재번역 비용을 없앤다 — 2시간 영상 전체 재번역 방지.
    # Related: CHANGELOG CHG-20260715-020.
    import json as _json
    import re as _re

    from ..db import SrtBackup, Translation
    from ..pipeline.translate import _hash as _thash

    def _norm_txt(t: str) -> str:
        return _re.sub(r"[^\w가-힣]", "", t or "")

    new_cues = sorted(
        (
            (s.start.total_seconds(), s.end.total_seconds(), " ".join(s.content.split()))
            for s in subs
        ),
        key=lambda c: c[0],
    )

    with _exclusive((video_id, "__srt_import__"), skip=body.dry_run), get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        segs = session.exec(
            select(Segment)
            .where(Segment.job_id == job.id, Segment.lang == "ko")
            .order_by(Segment.idx)
        ).all()
        if not segs:
            raise HTTPException(400, "이 영상엔 세그먼트가 없습니다.")

        old_ids = [s.id for s in segs]
        old_trans = session.exec(
            select(Translation).where(Translation.segment_id.in_(old_ids))
        ).all()
        # norm text -> lang -> 후보들(시각, 번역). 딕셔너리 직조회 —
        # (풀 전체 × 새 큐) 정규화 반복은 2천×1.5천에서 수십 초였음.
        seg_by_id = {s.id: s for s in segs}
        carry_pool: dict[str, dict[str, list]] = {}
        for tr in old_trans:
            src = seg_by_id.get(tr.segment_id)
            if src is None or not tr.text.strip():
                continue
            ntxt = _norm_txt(src.text_final or src.text_llm or src.text_whisper)
            if ntxt:
                carry_pool.setdefault(ntxt, {}).setdefault(tr.lang, []).append(
                    (src.start, tr)
                )

        # 이어받기 예측/실행 공용: 새 큐 -> (lang, Translation) 목록 (O(1) 조회)
        def match_carry(ns: float, ntext: str) -> list:
            by_lang = carry_pool.get(_norm_txt(ntext))
            if not by_lang:
                return []
            found = []
            for lang, cands in by_lang.items():
                best = min(cands, key=lambda c: abs(c[0] - ns))
                if abs(best[0] - ns) <= 20.0:  # 같은 문장이 반복돼도 시간으로 구분
                    found.append((lang, best[1]))
            return found

        carry_count = sum(1 for s0, _e0, t0 in new_cues if match_carry(s0, t0))
        total = len(segs)

        if body.dry_run:
            # 미리보기: 같은 시간대 기존 텍스트와 나란히
            sample = []
            for s0, e0, t0 in new_cues[:6]:
                near = min(segs, key=lambda x: abs(x.start - s0))
                sample.append(
                    {
                        "idx": near.idx,
                        "old": (near.text_final or near.text_llm or near.text_whisper)[:50],
                        "new": t0[:50],
                    }
                )
            return {
                "title": job.title,
                "video_id": video_id,
                "srt_count": len(new_cues),
                "matched": len(new_cues),
                "total": total,
                "already_reviewed": sum(1 for s in segs if s.reviewed),
                "replace": True,
                "carry": carry_count,
                "sample": sample,
            }

        # 전체 스냅샷 (구조 교체는 텍스트 스냅샷으로 못 되돌림 — 행+번역 전부)
        snap = _json.dumps(
            {
                "v": 2,
                "segments": [
                    {k: v for k, v in s.model_dump().items() if k != "id"}
                    | {"_old_id": s.id}
                    for s in segs
                ],
                "translations": [
                    t.model_dump() | {"_old_seg_id": t.segment_id} for t in old_trans
                ],
            },
            ensure_ascii=False,
            default=str,
        )
        bk = session.exec(
            select(SrtBackup).where(SrtBackup.video_id == video_id)
        ).first()
        if bk is None:
            session.add(SrtBackup(video_id=video_id, filename=body.filename, data=snap))
        else:
            bk.filename, bk.data, bk.created_at = body.filename, snap, utcnow()
            session.add(bk)

        # 기계 참조(whisper/llm/유튜브)는 시간 겹침으로 이관 — 우로보로스 diff
        # (absorb·학습쌍)가 새 구조에서도 대략적 초안을 갖게
        def overlapping_join(field: str, s0: float, e0: float) -> str:
            parts = []
            for s in segs:
                if s.start < e0 and s.end > s0:
                    v = (getattr(s, field) or "").strip()
                    if v and (not parts or parts[-1] != v):
                        parts.append(v)
            return " ".join(parts)

        # 갈아엎기: 기존 ko 행 + 그 번역을 벌크 삭제 -> srt 구조로 재생성.
        # 행 단위 delete/flush는 클라우드 PG에서 수천 왕복 = 프록시 타임아웃
        # (2231행 실사용에서 실증) — 벌크 2문 + flush 1회로.
        session.exec(sql_delete(Translation).where(Translation.segment_id.in_(old_ids)))
        session.exec(sql_delete(Segment).where(Segment.id.in_(old_ids)))
        session.flush()

        staged: list[tuple[Segment, list, str]] = []
        for i, (s0, e0, t0) in enumerate(new_cues):
            row = Segment(
                job_id=job.id,
                lang="ko",
                idx=i,
                start=round(s0, 3),
                end=round(e0, 3),
                text_whisper=overlapping_join("text_whisper", s0, e0),
                text_youtube=overlapping_join("text_youtube", s0, e0),
                text_llm=overlapping_join("text_llm", s0, e0),
                text_final=t0,
                reviewed=True,
            )
            session.add(row)
            staged.append((row, match_carry(s0, t0), t0))
        session.flush()  # executemany 한 번에 — 전 행 id 일괄 부여

        carried = 0
        for row, carries, t0 in staged:
            for lang, tr in carries:
                session.add(
                    Translation(
                        segment_id=row.id,
                        lang=lang,
                        text=tr.text,
                        reviewed=tr.reviewed,
                        edited=tr.edited,
                        source_hash=_thash(t0.strip()),
                    )
                )
                carried += 1
        job.status, job.updated_at = "reviewing", utcnow()
        session.add(job)
        session.commit()
        matched = len(new_cues)

    # ouroboros: diff the freshly-applied finals against the machine draft
    absorbed = {}
    try:
        from ..feedback import absorb_job

        absorbed = absorb_job(video_id)
    except Exception:
        pass
    return {
        "applied": matched,
        "total": total,
        "absorbed": absorbed,
        "carried_translations": carried,
    }


@app.post("/api/jobs/{video_id}/undo-srt")
def undo_srt(request: Request, video_id: str) -> dict:
    """Revert the last .srt import — restore each segment's previous text_final /
    reviewed from the snapshot taken at import time (admin)."""
    _require_admin(request)
    import json as _json

    from ..db import SrtBackup

    with get_session() as session:
        bk = session.exec(
            select(SrtBackup).where(SrtBackup.video_id == video_id)
        ).first()
        if bk is None:
            raise HTTPException(404, "되돌릴 .srt 적용 내역이 없습니다.")
        data = _json.loads(bk.data)
        restored = 0
        if isinstance(data, dict) and data.get("v") == 2:
            # 구조 교체(v2) 되돌리기: 현재 ko 행+번역을 지우고 스냅샷 재삽입
            from ..db import Translation

            job = session.exec(select(Job).where(Job.video_id == video_id)).first()
            cur = session.exec(
                select(Segment).where(Segment.job_id == job.id, Segment.lang == "ko")
            ).all()
            cur_ids = [s.id for s in cur]
            if cur_ids:
                for tr in session.exec(
                    select(Translation).where(Translation.segment_id.in_(cur_ids))
                ).all():
                    session.delete(tr)
            for s in cur:
                session.delete(s)
            session.flush()
            id_map: dict[int, int] = {}
            for row in data["segments"]:
                old_id = row.pop("_old_id")
                for drop in ("created_at", "updated_at"):
                    row.pop(drop, None)
                seg = Segment(**row)
                session.add(seg)
                session.flush()
                id_map[old_id] = seg.id
                restored += 1
            for trow in data["translations"]:
                old_seg = trow.pop("_old_seg_id")
                trow.pop("id", None)
                trow.pop("segment_id", None)
                for drop in ("created_at", "updated_at"):
                    trow.pop(drop, None)
                if old_seg in id_map:
                    session.add(Translation(segment_id=id_map[old_seg], **trow))
        else:
            # v1 스냅샷 (텍스트만 채우던 시절): 텍스트·검수 상태 복원
            for row in data:
                seg = session.get(Segment, row["id"])
                if seg is not None and seg.lang == "ko":
                    seg.text_final = row["text_final"]
                    seg.reviewed = row["reviewed"]
                    session.add(seg)
                    restored += 1
        session.delete(bk)
        session.commit()
    return {"restored": restored}


class PracticeBody(BaseModel):
    on: bool
    # tutorial course to bind this video to ("" unbinds; None = don't touch).
    # Binding forces practice=True and plants that course's deterministic
    # defects once (PLAN v4 §4.1/§4.3).
    course: str | None = None


_COURSE_IDS = {"basic", "playback", "fast", "structure", "timing", "finish"}


@app.post("/api/jobs/{video_id}/practice")
def set_practice(request: Request, video_id: str, body: PracticeBody) -> dict:
    """Mark (or unmark) a video as the 연습용 tutorial sandbox (admin).

    Practice videos are for tour lessons: reviewers can edit freely, and
    absorb_job skips them so drills never feed corrections/glossary.

    [WH-CHANGE v0.6.0 | FEAT | 2026-07-14 | CHG-20260714-010]
    Reason: course binding (one video per course, partial unique index) +
      bind-time defect injection — P5 rehearsal showed whisper hotwords beat
      every scripted bait, so defects are planted deterministically instead.
    Related: docs/tutorial/PLAN.md v4 §4.1/§4.3.
    """
    from ..practice import inject_course_defects

    _require_admin(request)
    if body.course is not None and body.course and body.course not in _COURSE_IDS:
        raise HTTPException(400, f"unknown course {body.course!r}")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        if job.clone_of is not None:
            raise HTTPException(400, "연습 세션 복제본에는 지정할 수 없습니다")
        injected = 0
        if body.course is not None:
            if body.course and body.course != job.practice_course:
                # one video per course: release the previous holder in the same
                # transaction (the partial unique index backstops races)
                for other in session.exec(
                    select(Job).where(
                        Job.practice_course == body.course, Job.id != job.id
                    )
                ).all():
                    other.practice_course = ""
                    other.updated_at = utcnow()
                    session.add(other)
                injected = inject_course_defects(session, job, body.course)
            job.practice_course = body.course
            if body.course:
                job.practice = True
            # unbinding a course does NOT clear practice (synthetic tutorial
            # videos stay excluded from learning forever — PLAN §4.1)
        else:
            job.practice = body.on
            if not body.on:
                job.practice_course = ""
        job.updated_at = utcnow()
        session.add(job)
        session.commit()
        return {
            "video_id": video_id,
            "practice": job.practice,
            "practice_course": job.practice_course,
            "defects_injected": injected,
        }


class PracticeSessionBody(BaseModel):
    key: str  # the browser's per-user session UUID (localStorage)
    reset: bool = False  # discard the existing clone first ("start over")


@app.post("/api/jobs/{video_id}/practice-session")
def practice_session(request: Request, video_id: str, body: PracticeSessionBody) -> dict:
    """Get (or create / reset) this browser's own clone of a practice video.

    Every reviewer practices on their own deep copy of the frozen baseline, so
    A/B/C can run the same course in parallel and each starts pristine
    (PLAN v4 §4.3 — user-mandated isolation)."""
    from ..practice import get_or_create_practice_session

    try:
        return get_or_create_practice_session(video_id, body.key, reset=body.reset)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tutorials")
def list_tutorials() -> dict:
    """course id -> baseline video_id (server-computed, one per course)."""
    with get_session() as session:
        rows = session.exec(
            select(Job).where(
                Job.practice_course != "",  # noqa: E712
                Job.clone_of == None,  # noqa: E711
            )
        ).all()
    return {j.practice_course: j.video_id for j in rows}


class AssigneeBody(BaseModel):
    name: str = ""


@app.post("/api/jobs/{video_id}/assignee")
def set_assignee(video_id: str, body: AssigneeBody) -> dict:
    """Set (or clear, with '') the reviewer assigned to this video. Any logged-in
    reviewer can claim/reassign — the team is small and trust-based."""
    name = body.name.strip()[:60]
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")
        job.assignee = name
        job.updated_at = utcnow()
        session.add(job)
        session.commit()
    return {"video_id": video_id, "assignee": name}


@app.get("/api/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


# static frontend (built by `npm run build` in src/jamak/web/frontend)
_dist = Path(__file__).parent / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
