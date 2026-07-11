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
    return await call_next(request)


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
        jobs = session.exec(select(Job).order_by(Job.created_at.desc())).all()
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


class RestoreSegmentsBody(BaseModel):
    segments: list[SegmentSnapshot]


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


@app.post("/api/jobs/{video_id}/segments/restore")
def restore_segments(video_id: str, body: RestoreSegmentsBody, lang: str = "ko") -> list[dict]:
    """Restore one editor undo snapshot for ONE track's segment list."""
    if not body.segments:
        raise HTTPException(400, "empty segment snapshot")
    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            raise HTTPException(404, f"no job for {video_id}")

        # Translations of ids the snapshot KEEPS stay valid (reinserted with the
        # same id) — do not touch those, so a ko structural undo never wipes
        # reviewed translation work. But translations of ids the undo DROPS must
        # be deleted, not orphaned: Segment.id is a reused rowid, so a later
        # insert would reattach the dead translation to an unrelated cue and
        # export it (same protection as merge_next/delete_segment).
        current_ids = set(
            session.exec(
                select(Segment.id).where(
                    Segment.job_id == job.id, Segment.lang == lang
                )
            ).all()
        )
        surviving_ids = {s.id for s in body.segments if s.id is not None}
        dropped_ids = current_ids - surviving_ids
        if dropped_ids:
            session.exec(
                sql_delete(Translation).where(Translation.segment_id.in_(dropped_ids))
            )
        session.exec(
            sql_delete(Segment).where(Segment.job_id == job.id, Segment.lang == lang)
        )

        for i, snap in enumerate(sorted(body.segments, key=lambda s: s.idx)):
            session.add(
                Segment(
                    id=snap.id,
                    job_id=job.id,
                    lang=lang,
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
        session.add(
            Segment(
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

        if which == "start":
            hi = seg.end - 0.1  # can't cross this cue's own end
            t = min(body.time, hi)
            prev = _previous_segment(session, seg)
            if prev is not None and t < prev.end:
                # crossed into the previous cue — push its end back with us
                t = round(min(max(t, prev.start + 0.1), hi), 3)
                prev.end = t
                session.add(prev)
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
            else:
                t = round(t, 3)  # free in the gap after this end
            seg.end = t

        session.add(seg)
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
    try:
        translated = translate_segments(seg_dicts, "ko", lang)
    except HTTPException:
        raise
    except Exception as e:  # API/auth/network error -> clean JSON, not a 500
        raise HTTPException(502, f"번역 API 오류: {e}")
    return {"lang": lang, "translated": len(translated), "segments": len(seg_dicts)}


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


@app.post("/api/jobs/{video_id}/repair-stt")
def repair_stt(request: Request, video_id: str) -> dict:
    """Recover segments where whisper hallucinated its initial_prompt.

    Works on segments already in the DB (e.g. videos processed before the
    crosscheck-time echo filter existed). Zero API cost: where the segment
    text is a prompt echo and a YouTube caption exists for that span, we
    replace the working text with the YouTube caption and re-open it for
    review. Segments with no caption are left for the human. Admin-only.
    """
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
            covered = [(s.start, s.end) for s in live]
            for row in youtube_gap_rows(covered, caps):
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
