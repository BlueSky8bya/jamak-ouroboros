"""Ouroboros data store: jobs, segments, corrections, glossary.

The DB is the single source of truth for everything the loop has learned.
Markdown exports (e.g. glossary snapshots) are views, never the original.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .config import DB_PATH, ensure_dirs


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(SQLModel, table=True):
    """One YouTube video going through the pipeline."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(index=True, unique=True)
    url: str
    title: str = ""
    channel: str = ""
    duration_seconds: float = 0.0
    upload_date: str = ""  # YouTube upload date YYYYMMDD ('' if unknown)
    # pending -> ingested -> transcribed -> corrected -> reviewing -> done
    status: str = Field(default="pending", index=True)
    # text review (per-segment `reviewed`) and timing review are separate passes:
    # finishing the words doesn't mean the cue times are done. This flags the
    # human-confirmed timing pass for the whole video.
    timing_done: bool = False
    # display name of the reviewer who claimed this video ('' = unassigned).
    # Reviewers log in with a free-form name (password-based roles), so this is
    # just that name — no fixed roster needed.
    assignee: str = ""
    # 연습용 영상 (tutorial sandbox): reviewers practice the tour lessons here
    # without fear. Its edits never feed the ouroboros (absorb is a no-op) so
    # practice typos can't pollute corrections/glossary.
    practice: bool = False
    # dedicated tutorial course this video teaches ("" = none). One active
    # video per course — enforced by a partial unique index (_ensure_columns).
    # Unbinding a course never clears `practice`: synthetic tutorial videos
    # stay excluded from learning forever.
    practice_course: str = Field(default="")
    # per-user practice sandbox (PLAN v4 §4.3): a clone Job deep-copied from a
    # baseline practice job so every reviewer starts from the same pristine
    # state in parallel. clone_of = the baseline job id; session_key = the
    # browser's UUID. A clone's video_id is "<base_video_id>~<session_key>",
    # which lets every video_id-keyed endpoint work on clones unchanged (the
    # player strips the "~..." suffix to embed the real YouTube video).
    clone_of: Optional[int] = Field(default=None, index=True)
    session_key: str = Field(default="")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Segment(SQLModel, table=True):
    """One subtitle segment with every stage's text preserved.

    Keeping all stages side by side is what makes the ouroboros diff possible:
    machine draft vs human final is computed per segment, not per file.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True, foreign_key="job.id")
    # subtitle track this segment belongs to: "ko" = source, or a target
    # language ("en", "ja", ...) that has its own independent structure/timing
    # (ADR-0006). Existing rows migrate to "ko".
    # per-job lookups use ix_segment_job_id; the few cross-job lang-scoped scans
    # (translation_examples forked branch, split budget) are served by the
    # composite ix_segment_lang_reviewed created in _ensure_columns. idx is never
    # queried without job_id and is renumbered often, so it carries no index.
    lang: str = Field(default="ko")
    idx: int  # order within the job (per lang track)
    start: float
    end: float
    text_whisper: str = ""  # raw faster-whisper output
    text_youtube: str = ""  # aligned YouTube auto-caption text (may be empty)
    text_llm: str = ""  # Claude-corrected draft
    text_final: str = ""  # human-reviewed final
    # crosscheck flag: whisper and youtube disagree here -> review priority
    flagged: bool = False
    llm_uncertain: bool = False  # Claude marked this segment as uncertain
    reviewed: bool = False
    # human authored/changed this segment's text (used on a forked translation
    # track to tell hand-edited text from copied machine text — ADR-0006). ko
    # segments track edits via text_final vs stage text, so this is translation-side.
    edited: bool = False
    low_conf: str = ""  # whisper's least-confident words here (comma-sep) — review hint
    # human review marker (ADR-0009): "" = none, "hold" = 잘 안 들림/보류 — the
    # reviewer couldn't confirm this segment yet and wants to come back to it.
    # Cleared automatically when the segment is confirmed (reviewed=True).
    review_flag: str = ""


class Track(SQLModel, table=True):
    """One subtitle track = (job, lang). ADR-0006.

    Korean is the source track. A translation lang inherits the Korean
    structure/timing by default (stored only as Translation rows — no
    duplication); `forked=True` means the reviewer split it into its own
    independent Segment rows (lang != "ko") for language-specific splits/timing.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True, foreign_key="job.id")
    lang: str = Field(index=True)
    forked: bool = False
    timing_done: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Correction(SQLModel, table=True):
    """A learned pair: what the machine wrote -> what the human fixed it to."""

    id: Optional[int] = Field(default=None, primary_key=True)
    wrong: str = Field(index=True)
    right: str
    context: str = ""  # surrounding sentence for few-shot quality
    source_job_id: Optional[int] = None
    count: int = 1  # how many times this exact fix recurred
    created_at: datetime = Field(default_factory=utcnow)


class LlmCache(SQLModel, table=True):
    """Cache of LLM outputs keyed by input content hash.

    kind='correct': key = hash(pre-passed whisper text | youtube text),
    value = corrected text ('' = no change needed). Re-running a video
    costs zero API calls unless the source text changed.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    kind: str = Field(index=True)
    source_hash: str = Field(index=True)
    text: str = ""  # the resulting text (may legitimately be '' for noise)
    changed: bool = False  # False = model left the source text as-is
    uncertain: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Translation(SQLModel, table=True):
    """Cached translation of one segment into one language.

    source_hash ties the cache to the exact Korean text it was made from —
    when a human edits the Korean after translating, the stale entry is
    ignored and that segment is re-translated on next export.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    segment_id: int = Field(index=True, foreign_key="segment.id")
    lang: str = Field(index=True)  # en, ja, zh-Hans, zh-Hant, es, fr, it, ...
    text: str
    source_hash: str
    reviewed: bool = False  # human checked this translation
    edited: bool = False  # human changed the text (protect from re-translate)
    created_at: datetime = Field(default_factory=utcnow)


class GlossaryTerm(SQLModel, table=True):
    """Domain vocabulary: 신인, 축지법, 하늘궁, 불교/유교/기독교 용어, 한자어..."""

    id: Optional[int] = Field(default=None, primary_key=True)
    term: str = Field(index=True, unique=True)
    variants: str = ""  # comma-separated common misrecognitions
    category: str = ""  # e.g. 고유어휘/불교/유교/기독교/한자어/사투리
    note: str = ""
    confidence: float = 1.0  # 1.0 = human-approved, <1.0 = auto-extracted candidate
    approved: bool = True


class SttBlob(SQLModel, table=True):
    """Raw per-word STT output (the contents of the job's stt.json), kept in the
    DB so the cloud review app can serve the word-map (/words) and tighten
    timing (/tighten) without the local job files.

    STT runs on the admin's local GPU; when it writes the DB it also stores this
    blob, so a cloud-hosted app (ADR-0007 path B) with no filesystem copy still
    has the per-word timestamps. `data` is the same JSON text stt.py caches to
    disk. One row per job.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True, unique=True, foreign_key="job.id")
    data: str = ""  # json.dumps of the stt segment list (per-word timestamps)
    created_at: datetime = Field(default_factory=utcnow)


class JobRequest(SQLModel, table=True):
    """A pending 'make subtitles for this URL' request (ADR-0008 path B).

    The cloud web app has no GPU, so 'create' from the site only records a
    request here; a `jamak worker` running on the admin's local GPU machine
    polls for pending requests and runs the pipeline one at a time. This is the
    DB-backed queue (source of truth for both the cloud app and the worker).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(index=True)
    url: str
    fresh: bool = False  # True = re-transcribe (ignore cached STT)
    # pending -> processing -> (row deleted on success) / error
    status: str = Field(default="pending", index=True)
    note: str = ""  # error detail when status == "error"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class HanjaTerm(SQLModel, table=True):
    """강조 한자어 병기 사전 — "얼굴 안 자" → "얼굴 안(顔) 자" 채우기의 원본.

    검수 완료 대본(txt·DB)의 기존 병기 패턴에서 채굴한다 (학습 데이터는 DB가
    원본 — 코드 하드코딩 금지 규칙). 단일자는 동음이 많아 문맥 뜻 단어(gloss)와
    짝으로 저장한다: (얼굴, 안)→顔 vs (편안할, 안)→安.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    reading: str = Field(index=True)  # 한글 표기 (안, 무상, 용맹정진)
    gloss: str = Field(default="")  # 단일자 구분용 뜻 단어 ('' = 다자어)
    hanja: str  # 채워 넣을 한자 (顔, 無常, 勇猛精進)
    count: int = 1  # 채굴 출처에서의 등장 횟수 (충돌 시 다수결 근거)
    created_at: datetime = Field(default_factory=utcnow)


class SrtBackup(SQLModel, table=True):
    """Pre-import snapshot of a video's Korean segments, so applying a .srt is
    undoable (in case the wrong file was dropped). One row per job (the last
    import); `data` is a JSON list of {id, text_final, reviewed}."""

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(index=True, unique=True)
    filename: str = ""
    data: str = ""  # json.dumps([{"id","text_final","reviewed"}, ...])
    created_at: datetime = Field(default_factory=utcnow)


_engine = None


def _db_url() -> Optional[str]:
    """Postgres URL for cloud hosting (path B), normalized for the psycopg
    driver. None -> fall back to the local SQLite file. Accepts the
    `postgres://` / `postgresql://` forms Railway/Neon/etc. hand out."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return None
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _ensure_columns(engine) -> None:
    """Lightweight additive migration for SQLite (create_all won't add
    columns to an existing table). Adds any missing nullable columns."""
    from sqlalchemy import inspect, text

    # Postgres wants BOOLEAN DEFAULT false, not 0. (On a fresh cloud DB every
    # column is created by create_all, so these ALTERs never fire — this only
    # migrates an existing SQLite file — but keep the DDL valid for both.)
    bt = "false" if engine.dialect.name == "postgresql" else "0"
    wanted = {
        "translation": {
            "reviewed": f"BOOLEAN DEFAULT {bt}",
            "edited": f"BOOLEAN DEFAULT {bt}",
        },
        "job": {
            "upload_date": "VARCHAR DEFAULT ''",
            "timing_done": f"BOOLEAN DEFAULT {bt}",
            "assignee": "VARCHAR DEFAULT ''",
            "practice": f"BOOLEAN DEFAULT {bt}",
            "practice_course": "VARCHAR DEFAULT ''",
            "clone_of": "INTEGER",
            "session_key": "VARCHAR DEFAULT ''",
        },
        "segment": {
            "low_conf": "VARCHAR DEFAULT ''",
            "lang": "VARCHAR DEFAULT 'ko'",
            "edited": f"BOOLEAN DEFAULT {bt}",
            "review_flag": "VARCHAR DEFAULT ''",
        },
    }
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table, cols in wanted.items():
            if table not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        # Fork idempotency is enforced in fork_track by an application-level
        # existence check, NOT a DB unique index: a UNIQUE(job_id,lang,idx)
        # collides with the transient duplicate idx values that split/merge/
        # repair legitimately hold mid-transaction (SQLite checks unique
        # indexes per-row, non-deferred), so it 500s those flows. Drop it if a
        # prior version created it. Drop ix_segment_idx too (idx is renumbered
        # in split/merge and never queried without job_id — pure write cost).
        if "segment" in existing_tables:
            for idx_name in ("uq_segment_job_lang_idx", "ix_segment_idx"):
                conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
            # a few cross-job lang-scoped scans DO exist (translation_examples'
            # forked branch, split.learned_line_budget) — WHERE lang=? AND
            # reviewed=?. lang is very low-cardinality (nearly all rows "ko"),
            # so a composite (lang, reviewed) index lets a target-lang lookup
            # skip the bulk of the table instead of full-scanning.
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_segment_lang_reviewed "
                    "ON segment (lang, reviewed)"
                )
            )
        if "job" in existing_tables:
            # one active tutorial video per course (PLAN v4 §4.1): the partial
            # unique index makes a concurrent double-bind an IntegrityError
            # instead of two silent winners. Works on SQLite and Postgres.
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_job_practice_course "
                    "ON job (practice_course) WHERE practice_course <> ''"
                )
            )


def get_engine():
    global _engine
    if _engine is None:
        url = _db_url()
        if url:
            # Cloud Postgres (ADR-0007 path B). pool_pre_ping recycles
            # connections a serverless DB may have dropped between requests.
            # Pool sized for tens of concurrent reviewers (requests are short,
            # so 10+20 overflow rarely saturates; Railway PG allows ~100 conns).
            _engine = create_engine(
                url, pool_pre_ping=True, pool_size=10, max_overflow=20
            )
        else:
            ensure_dirs()
            # busy_timeout: the preview server and the user's own browser can
            # share jamak.db (MEMORY.md). Without it a concurrent writer fails
            # instantly with 'database is locked'; 30s makes writers wait and
            # serialize. (Postgres gives real row locking — this is the local
            # single-file path only.)
            _engine = create_engine(
                f"sqlite:///{DB_PATH}", connect_args={"timeout": 30}
            )
        SQLModel.metadata.create_all(_engine)
        _ensure_columns(_engine)
    return _engine


def save_stt_blob(session: Session, job_id: int, data: str) -> None:
    """Upsert the raw stt.json text for a job so the cloud app can serve the
    word-map / tighten timing without local job files. One row per job."""
    row = session.exec(select(SttBlob).where(SttBlob.job_id == job_id)).first()
    if row is None:
        session.add(SttBlob(job_id=job_id, data=data))
    else:
        row.data = data
        session.add(row)


def load_stt_blob(session: Session, job_id: int) -> Optional[str]:
    """Raw stt.json text for a job, or None if STT was never stored."""
    row = session.exec(select(SttBlob).where(SttBlob.job_id == job_id)).first()
    return row.data if row else None


def get_session() -> Session:
    return Session(get_engine())


def backup_db(keep: int = 30) -> Optional[Path]:
    """Timestamped online backup of the SQLite DB (safe while it's being written).

    jamak.db is the single source of truth for a year+ of review/learning data,
    yet it's a tiny text-only file — a backup is cheap and the loss would not be.
    Writes data/backups/jamak-<ts>.db via SQLite's online backup API and keeps
    the newest `keep` copies. Returns the backup path, or None if there's no DB.
    """
    import sqlite3

    if not Path(DB_PATH).exists():
        return None
    backups = Path(DB_PATH).parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    dest = backups / f"jamak-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"

    src = sqlite3.connect(str(DB_PATH))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)  # atomic, consistent even with concurrent writers
        finally:
            dst.close()
    finally:
        src.close()

    if keep > 0:
        for old in sorted(backups.glob("jamak-*.db"))[:-keep]:
            try:
                old.unlink()
            except OSError:
                pass
    return dest
