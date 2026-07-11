"""jamak CLI — the pipeline's front door.

Commands:
    jamak doctor            environment check (GPU, ffmpeg, API key, DB)
    jamak run <url>         full pipeline: ingest -> stt -> crosscheck -> [correct] -> srt
    jamak seed-import <dir> bootstrap glossary/corrections from reviewed .srt files
    jamak export <video_id> write .srt from the latest stage available
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from . import config
from .db import Job, Segment, get_session, utcnow

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def doctor() -> None:
    """Check that every external dependency is ready."""
    import shutil
    import subprocess

    ok = True

    # ffmpeg
    if shutil.which("ffmpeg"):
        console.print("[green]OK[/] ffmpeg")
    else:
        console.print("[red]MISSING[/] ffmpeg - install and add to PATH")
        ok = False

    # GPU
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        gpu = out.stdout.strip()
        console.print(f"[green]OK[/] GPU: {gpu}" if gpu else "[yellow]WARN[/] no GPU")
    except Exception:
        console.print("[yellow]WARN[/] nvidia-smi not found - STT will run on CPU (slow)")

    # ctranslate2 CUDA
    try:
        import ctranslate2

        n = ctranslate2.get_cuda_device_count()
        if n > 0:
            console.print(f"[green]OK[/] ctranslate2 sees {n} CUDA device(s)")
        else:
            console.print(
                "[yellow]WARN[/] ctranslate2 sees no CUDA device - "
                "check cuDNN/cuBLAS (uv sync --extra cuda)"
            )
    except Exception as e:
        console.print(f"[red]FAIL[/] ctranslate2 import: {e}")
        ok = False

    # Anthropic API key (needed from M2)
    import os

    if os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[green]OK[/] ANTHROPIC_API_KEY set")
    else:
        console.print("[yellow]WARN[/] ANTHROPIC_API_KEY not set - LLM correction disabled")

    # DB
    from .db import get_engine

    get_engine()
    console.print(f"[green]OK[/] DB at {config.DB_PATH}")

    raise typer.Exit(0 if ok else 1)


@app.command()
def run(
    url: str,
    correct: bool = typer.Option(True, help="Run Claude correction stage (needs API key)"),
    fresh: bool = typer.Option(
        False, help="Ignore cached STT and re-transcribe (re-roll with current glossary)"
    ),
    keep_audio: bool = typer.Option(
        False,
        help="Keep audio.wav after STT. Default: delete it (~112 MB/hr) once stt.json "
        "is cached — review/word-map/tighten need only stt.json; retranscribe "
        "re-downloads the audio on demand.",
    ),
) -> None:
    """Full pipeline: URL in, draft .srt out."""
    from .pipeline.assemble import to_srt
    from .pipeline.crosscheck import crosscheck
    from .pipeline.ingest import ingest
    from .pipeline.stt import transcribe

    config.ensure_dirs()

    console.rule("[1/5] Ingest")
    res = ingest(url)
    console.print(f"{res.title} ({res.duration_seconds/60:.0f}min) - {res.video_id}")
    if res.captions_path:
        console.print("YouTube auto-captions: [green]found[/]")
    else:
        console.print("YouTube auto-captions: [yellow]none[/] (crosscheck limited)")

    with get_session() as session:
        job = session.exec(
            __import__("sqlmodel").select(Job).where(Job.video_id == res.video_id)
        ).first()
        if job is None:
            job = Job(video_id=res.video_id, url=url)
        job.title, job.channel = res.title, res.channel
        job.duration_seconds = res.duration_seconds
        if res.upload_date:
            job.upload_date = res.upload_date
        job.status, job.updated_at = "ingested", utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    console.rule("[2/5] STT (faster-whisper)")
    from .glossary import whisper_hotwords

    # domain vocabulary goes in via hotwords (acoustic bias, not echoable);
    # we intentionally pass NO initial_prompt to avoid prompt-echo hallucination
    hotwords = whisper_hotwords()
    if hotwords:
        console.print(f"hotwords ({len(hotwords.split())} terms): {hotwords[:80]}...")
    else:
        console.print("hotwords: none yet (glossary empty) — run seed-import / glossary-mine")
    if fresh:
        console.print("[yellow]fresh[/] — ignoring cached STT, re-transcribing")

    from rich.progress import Progress

    with Progress(console=console) as progress:
        task = progress.add_task("transcribing", total=res.duration_seconds)

        def cb(pos: float, total: float) -> None:
            progress.update(task, completed=min(pos, res.duration_seconds))

        stt_segments = transcribe(
            res.audio_path, res.job_dir, "", cb, hotwords, force=fresh
        )

    from .pipeline.split import (
        DEFAULT_MAX_CHARS,
        DEFAULT_SOFT_CHARS,
        learned_line_budget,
        split_segments,
    )

    budget = learned_line_budget()
    if budget:
        console.print(
            f"subtitle length learned from reviews: soft {budget[0]} / hard {budget[1]} chars"
        )
    else:
        console.print(
            f"subtitle length: default soft {DEFAULT_SOFT_CHARS} / hard {DEFAULT_MAX_CHARS} "
            "(learns after enough review)"
        )
    n_raw = len(stt_segments)
    stt_segments = split_segments(stt_segments, budget)
    n_split = len(stt_segments)

    from .pipeline.noise import filter_standalone_audience_responses

    stt_segments = filter_standalone_audience_responses(stt_segments)
    n_noise = n_split - len(stt_segments)
    console.print(f"{n_raw} raw segments -> {n_split} subtitle-sized")
    if n_noise:
        console.print(f"removed {n_noise} standalone audience-response segments")

    console.rule("[3/5] Crosscheck")
    rows, n_echo = crosscheck(stt_segments, res.captions_path)
    n_flagged = sum(1 for r in rows if r["flagged"])
    if n_echo:
        console.print(f"recovered {n_echo} hallucination/echo segments from YouTube captions")
    console.print(f"flagged {n_flagged}/{len(rows)} segments for review priority")

    # persist segments (replace any previous run of this job)
    with get_session() as session:
        from sqlmodel import delete, select

        from .db import Segment as _Seg, Translation as _Tr

        # ONLY replace the Korean source track. Forked translation tracks
        # (lang != "ko", ADR-0006) hold independent human review work and must
        # survive a re-run/retranscribe — an unscoped delete here would wipe
        # them ('기존 검수 데이터 파괴 금지').
        # Delete the ko segments' Translation rows first: Segment.id is a reused
        # rowid, so orphaned translations would (a) accumulate every re-run and
        # (b) reattach to an unrelated re-inserted cue (mirrors app.py's
        # merge/delete/restore protection — this CLI path was the sole omission).
        ko_ids = list(
            session.exec(
                select(_Seg.id).where(_Seg.job_id == job_id, _Seg.lang == "ko")
            ).all()
        )
        if ko_ids:
            session.exec(delete(_Tr).where(_Tr.segment_id.in_(ko_ids)))
        session.exec(
            delete(Segment).where(Segment.job_id == job_id, Segment.lang == "ko")
        )
        for i, r in enumerate(rows):
            session.add(Segment(job_id=job_id, lang="ko", idx=i, **r))
        # Store the raw per-word STT in the DB too, so a cloud-hosted review app
        # (ADR-0007 path B) with no local job files can serve the word-map /
        # tighten timing. Local file stays the STT cache; this is the portable copy.
        _stt_file = res.job_dir / "stt.json"
        if _stt_file.exists():
            from .db import save_stt_blob

            save_stt_blob(session, job_id, _stt_file.read_text(encoding="utf-8"))
        job = session.get(Job, job_id)
        job.status, job.updated_at = "transcribed", utcnow()
        session.add(job)
        session.commit()

    text_key = "text_whisper"
    import os

    if correct and os.environ.get("ANTHROPIC_API_KEY"):
        console.rule("[4/5] LLM correction (Claude)")
        from .pipeline.correct import correct_job

        with get_session() as session:
            job = session.get(Job, job_id)
            job.status, job.updated_at = "correcting", utcnow()
            session.add(job)
            session.commit()

        n_changed = correct_job(job_id, console=console)
        console.print(f"corrected {n_changed} segments")

        with get_session() as session:
            job = session.get(Job, job_id)
            job.status, job.updated_at = "corrected", utcnow()
            session.add(job)
            session.commit()
        text_key = "text_llm"
    else:
        console.rule("[4/5] LLM correction — skipped")

    console.rule("[5/5] Export draft .srt")
    with get_session() as session:
        from sqlmodel import select

        segs = session.exec(
            select(Segment).where(Segment.job_id == job_id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]
    out = to_srt(
        seg_dicts,
        text_key,
        res.job_dir / f"{res.video_id}.draft.srt",
    )
    console.print(f"[bold green]draft ready:[/] {out}")

    # audio.wav is only needed for STT; review/word-map/tighten use stt.json.
    # Delete it by default so hundreds of 1-2h videos don't fill the disk
    # (~112 MB/hr) — retranscribe re-downloads it via ingest when needed.
    if not keep_audio and res.audio_path.exists():
        try:
            freed = res.audio_path.stat().st_size / 1_048_576
            res.audio_path.unlink()
            console.print(
                f"cleaned audio.wav ({freed:.0f} MB freed; stt.json kept, "
                "re-downloads on retranscribe). --keep-audio to retain."
            )
        except OSError:
            pass


@app.command("seed-import")
def seed_import(
    directory: Path = typer.Argument(..., help="Folder with reviewed .srt files"),
) -> None:
    """Bootstrap the ouroboros DB from past human-reviewed subtitles."""
    from .seed import import_seeds

    stats = import_seeds(directory)
    console.print(
        f"imported [bold]{stats['files']}[/] files, "
        f"{stats['terms']} glossary candidates, {stats['pairs']} correction pairs"
    )


@app.command("glossary-mine")
def glossary_mine_cmd(
    directory: Path = typer.Argument(
        config.SEEDS_DIR, help="Corpus folder (.txt/.srt)"
    ),
) -> None:
    """Mine an approved glossary from the reviewed corpus (fills hotwords + prompt).

    One-time cheap Claude pass over frequency candidates — curates domain
    vocabulary, categories, and misrecognition variants into the glossary.
    """
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY not set[/]")
        raise typer.Exit(1)
    if not directory.exists():
        console.print(f"[red]no such folder: {directory}[/]")
        raise typer.Exit(1)

    from .glossary_mine import mine_glossary

    stats = mine_glossary(directory, console=console)
    console.print(
        f"[bold green]glossary:[/] +{stats['kept']} new, {stats['updated']} promoted "
        f"(approved) from {stats['candidates']} candidates"
    )
    console.print("이제 whisper hotwords가 이 용어들로 채워집니다 (음향 편향).")


@app.command()
def export(
    video_id: str,
    stage: str = typer.Option("best", help="best | whisper | llm | final"),
) -> None:
    """Write .srt for a job from the requested (or best available) stage."""
    from sqlmodel import select

    from .pipeline.assemble import to_srt

    key_map = {"whisper": "text_whisper", "llm": "text_llm", "final": "text_final"}

    with get_session() as session:
        job = session.exec(select(Job).where(Job.video_id == video_id)).first()
        if job is None:
            console.print(f"[red]no job for {video_id}[/]")
            raise typer.Exit(1)
        segs = session.exec(
            select(Segment).where(Segment.job_id == job.id).order_by(Segment.idx)
        ).all()
        seg_dicts = [s.model_dump() for s in segs]

    if stage == "best":
        for candidate in ("text_final", "text_llm", "text_whisper"):
            if any(d.get(candidate) for d in seg_dicts):
                key = candidate
                break
        else:
            console.print("[red]job has no text at any stage[/]")
            raise typer.Exit(1)
    else:
        key = key_map[stage]

    out = to_srt(seg_dicts, key, config.JOBS_DIR / video_id / f"{video_id}.{key}.srt")
    console.print(f"[bold green]exported:[/] {out}")


@app.command()
def absorb(video_id: str) -> None:
    """Ouroboros feedback: diff reviewed segments into corrections DB."""
    from .feedback import absorb_job

    stats = absorb_job(video_id)
    console.print(
        f"absorbed [bold]{stats['reviewed_segments']}[/] reviewed segments: "
        f"{stats['new_pairs']} new correction pairs, {stats['bumped']} reinforced, "
        f"{stats['applied']} later draft segments updated"
    )


@app.command()
def eval() -> None:  # noqa: A001
    """CER trend: machine draft vs human final, per job."""
    from rich.table import Table

    from .evaluate import evaluate_all

    rows = evaluate_all()
    if not rows:
        console.print("no reviewed jobs yet - review segments in the web app first")
        raise typer.Exit(0)
    table = Table(title="CER trend (lower is better)")
    for col in ("video", "date", "segs", "STT CER", "corrected CER", "gain"):
        table.add_column(col)
    for r in rows:
        gain = r["cer_whisper"] - r["cer_llm"]
        table.add_row(
            r["video_id"],
            r["date"],
            str(r["reviewed_segments"]),
            f"{r['cer_whisper']:.2%}",
            f"{r['cer_llm']:.2%}",
            f"{gain:+.2%}",
        )
    console.print(table)


@app.command("export-training-data")
def export_training_data_cmd(
    no_clips: bool = typer.Option(False, help="Manifest only, skip audio slicing"),
) -> None:
    """Export reviewed subtitles as a Whisper fine-tuning corpus (M5 prep)."""
    from .training import export_training_data

    stats = export_training_data(make_clips=not no_clips)
    console.print(
        f"training pairs: [bold]{stats['pairs']}[/] ({stats['minutes']} min of audio)"
    )
    if stats["skipped_no_audio"]:
        console.print(f"[yellow]{stats['skipped_no_audio']} skipped[/] (audio.wav missing)")
    console.print(f"manifest: {stats['manifest']}")
    console.print(
        "다음 단계: 데이터가 충분히 쌓이면 Whisper LoRA 파인튜닝 (ADR-0004)"
    )


@app.command("export-correction-data")
def export_correction_data_cmd() -> None:
    """Export (whisper draft -> human final) text pairs for a local correction model.

    Phase 1 of ADR-0005: accumulate the supervision needed to later fine-tune a
    free local model that replaces the per-video Claude correction call. API-free.
    """
    from .training import export_correction_pairs

    stats = export_correction_pairs()
    console.print(
        f"correction pairs: [bold]{stats['pairs']}[/] "
        f"({stats['changed']} changed / {stats['unchanged']} kept-as-is)"
    )
    console.print(f"manifest: {stats['manifest']}")
    if stats["pairs"] < 2000:
        console.print(
            "[yellow]아직 파인튜닝엔 부족[/] — 검수·흡수(absorb) 쌓을수록 증가 (ADR-0005)"
        )


@app.command("backfill-dates")
def backfill_dates() -> None:
    """Fetch YouTube upload dates for jobs ingested before we stored them."""
    from sqlmodel import select

    from .pipeline.ingest import fetch_upload_date

    with get_session() as session:
        jobs = session.exec(select(Job).where(Job.upload_date == "")).all()
        if not jobs:
            console.print("all jobs already have upload dates")
            return
        for job in jobs:
            try:
                d = fetch_upload_date(job.video_id)
            except Exception as e:  # noqa: BLE001
                console.print(f"[yellow]skip[/] {job.video_id}: {e}")
                continue
            if d:
                job.upload_date = d
                session.add(job)
                console.print(f"{job.video_id}: {d}")
        session.commit()
    console.print("done")


@app.command()
def backup(
    keep: int = typer.Option(30, help="How many timestamped backups to keep"),
) -> None:
    """Back up jamak.db to data/backups/ (timestamped, safe with live writes)."""
    from .db import backup_db

    dest = backup_db(keep=keep)
    if dest is None:
        console.print("[yellow]no DB to back up yet[/]")
    else:
        console.print(f"[bold green]backed up:[/] {dest}")


@app.command()
def serve(
    port: int = typer.Option(8710, help="Port for the review web app"),
    host: str = typer.Option(
        "127.0.0.1",
        help="Bind address. Keep 127.0.0.1 behind a tunnel (Cloudflare/Tailscale); "
        "use 0.0.0.0 only to expose on the LAN. Set JAMAK_AUTH before exposing.",
    ),
    backup_hours: float = typer.Option(
        24.0, help="Auto-backup jamak.db every N hours while serving (0 = off)"
    ),
) -> None:
    """Start the review web app (http://localhost:8710).

    Deployment: keep host=127.0.0.1 and put a tunnel (Cloudflare Tunnel +
    Access, or Tailscale) in front — see docs/agent/deployment.md. Set
    JAMAK_AUTH="user:pw,..." to require a login on the app itself. Auto-backs up
    jamak.db on start and every --backup-hours (data/backups/, keeps last 30).
    """
    import os
    import threading
    import time

    import uvicorn

    from .db import backup_db

    config.ensure_dirs()
    # session auth (JAMAK_ADMINS/NAMES + passwords) or legacy JAMAK_AUTH both count
    _auth_set = any(
        os.environ.get(v)
        for v in ("JAMAK_AUTH", "JAMAK_ADMINS", "JAMAK_NAMES")
    )
    if host != "127.0.0.1" and not _auth_set:
        console.print(
            "[bold yellow]warning:[/] binding a non-local host with no login "
            "configured — the app is unauthenticated. Set JAMAK_ADMINS + "
            "JAMAK_ADMIN_PASSWORD (and JAMAK_NAMES + JAMAK_PASSWORD), or front it "
            "with a tunnel gate."
        )

    # keep the year+ of learning data safe: back up on start, then on a timer
    if backup_hours > 0:
        def _backup_loop() -> None:
            while True:
                try:
                    backup_db()
                except Exception:
                    pass
                time.sleep(backup_hours * 3600)

        threading.Thread(target=_backup_loop, daemon=True).start()

    console.print(f"[bold green]review app:[/] http://{host}:{port}")
    uvicorn.run("jamak.web.app:app", host=host, port=port)


@app.command("migrate-to-cloud")
def migrate_to_cloud(
    to: str = typer.Option(
        "",
        "--to",
        help="Target Postgres URL (postgres://... / postgresql://...). "
        "Defaults to the DATABASE_URL env var.",
    ),
    force: bool = typer.Option(
        False, help="Copy even if the target already has jobs (may duplicate)."
    ),
) -> None:
    """One-time copy of the local SQLite DB (+ stt.json files) into a cloud
    Postgres (ADR-0007 path B). Source is opened read-only; only the target is
    written. Preserves primary-key ids (foreign keys stay valid) and resets the
    Postgres id sequences afterward so new inserts don't collide.
    """
    import json as _json
    import os

    from sqlmodel import Session, SQLModel, create_engine, select

    from . import db as dbmod
    from .db import (
        Correction,
        GlossaryTerm,
        Job,
        LlmCache,
        Segment,
        SttBlob,
        Track,
        Translation,
        _db_url,
        _ensure_columns,
        save_stt_blob,
    )

    target_url = to.strip() or os.environ.get("DATABASE_URL", "").strip()
    if not target_url:
        console.print("[red]no target: pass --to or set DATABASE_URL[/]")
        raise typer.Exit(1)
    # normalize via the same rule the app uses
    os.environ["DATABASE_URL"] = target_url
    norm = _db_url()
    if norm is None or not norm.startswith("postgresql"):
        console.print(f"[red]target must be Postgres, got:[/] {target_url}")
        raise typer.Exit(1)

    src_path = config.DB_PATH
    if not Path(src_path).exists():
        console.print(f"[red]no local DB at {src_path}[/]")
        raise typer.Exit(1)

    src = create_engine(f"sqlite:///{src_path}", connect_args={"timeout": 30})
    dst = create_engine(norm, pool_pre_ping=True)
    SQLModel.metadata.create_all(dst)
    _ensure_columns(dst)

    # dependency order: parents before children (FKs)
    order = [
        Job,
        Track,
        Segment,
        Translation,
        SttBlob,
        Correction,
        LlmCache,
        GlossaryTerm,
    ]
    tables = {
        Job: "job",
        Track: "track",
        Segment: "segment",
        Translation: "translation",
        SttBlob: "sttblob",
        Correction: "correction",
        LlmCache: "llmcache",
        GlossaryTerm: "glossaryterm",
    }

    with Session(dst) as dsession:
        existing = dsession.exec(select(Job)).first()
        if existing is not None and not force:
            console.print(
                "[yellow]target already has jobs — aborting to avoid duplicates. "
                "Use --force to copy anyway.[/]"
            )
            raise typer.Exit(1)

        with Session(src) as ssession:
            for model in order:
                rows = ssession.exec(select(model)).all()
                for row in rows:
                    # copy every column incl. id -> FK references stay valid
                    dsession.add(model(**row.model_dump()))
                dsession.commit()
                console.print(f"copied {len(rows):>6} {tables[model]}")

            # jobs whose stt.json only lived on disk -> pull into SttBlob
            have_blob = {
                b.job_id for b in dsession.exec(select(SttBlob)).all()
            }
            added = 0
            for job in ssession.exec(select(Job)).all():
                if job.id in have_blob:
                    continue
                f = config.JOBS_DIR / job.video_id / "stt.json"
                if f.exists():
                    save_stt_blob(dsession, job.id, f.read_text(encoding="utf-8"))
                    added += 1
            if added:
                dsession.commit()
                console.print(f"imported {added} stt.json file(s) into SttBlob")

        # reset Postgres id sequences to max(id) so new inserts don't collide
        from sqlalchemy import text

        for t in tables.values():
            # table names come from the fixed `tables` map, never user input
            dsession.execute(
                text(
                    f'SELECT setval(pg_get_serial_sequence(\'"{t}"\', \'id\'), '
                    f'COALESCE((SELECT MAX(id) FROM "{t}"), 1))'
                )
            )
        dsession.commit()

    console.print("[bold green]migration complete[/] -> cloud Postgres")


if __name__ == "__main__":
    app()
