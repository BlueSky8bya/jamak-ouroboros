"""Ouroboros data store: jobs, segments, corrections, glossary.

The DB is the single source of truth for everything the loop has learned.
Markdown exports (e.g. glossary snapshots) are views, never the original.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine

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
    lang: str = Field(default="ko", index=True)
    idx: int = Field(index=True)  # order within the job (per lang track)
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
    low_conf: str = ""  # whisper's least-confident words here (comma-sep) — review hint


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


_engine = None


def _ensure_columns(engine) -> None:
    """Lightweight additive migration for SQLite (create_all won't add
    columns to an existing table). Adds any missing nullable columns."""
    from sqlalchemy import inspect, text

    wanted = {
        "translation": {
            "reviewed": "BOOLEAN DEFAULT 0",
            "edited": "BOOLEAN DEFAULT 0",
        },
        "job": {
            "upload_date": "VARCHAR DEFAULT ''",
            "timing_done": "BOOLEAN DEFAULT 0",
        },
        "segment": {
            "low_conf": "VARCHAR DEFAULT ''",
            "lang": "VARCHAR DEFAULT 'ko'",
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


def get_engine():
    global _engine
    if _engine is None:
        ensure_dirs()
        _engine = create_engine(f"sqlite:///{DB_PATH}")
        SQLModel.metadata.create_all(_engine)
        _ensure_columns(_engine)
    return _engine


def get_session() -> Session:
    return Session(get_engine())
