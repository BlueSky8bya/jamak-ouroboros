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
) -> None:
    """Full pipeline: URL in, draft .srt out."""
    from .glossary import whisper_prompt
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
        job.status, job.updated_at = "ingested", utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    console.rule("[2/5] STT (faster-whisper)")
    prompt = whisper_prompt()
    console.print(f"initial_prompt: {prompt[:80]}...")

    from rich.progress import Progress

    with Progress(console=console) as progress:
        task = progress.add_task("transcribing", total=res.duration_seconds)

        def cb(pos: float, total: float) -> None:
            progress.update(task, completed=min(pos, res.duration_seconds))

        stt_segments = transcribe(res.audio_path, res.job_dir, prompt, cb)

    from .pipeline.split import split_segments

    n_raw = len(stt_segments)
    stt_segments = split_segments(stt_segments)
    console.print(f"{n_raw} raw segments -> {len(stt_segments)} subtitle-sized")

    console.rule("[3/5] Crosscheck")
    rows = crosscheck(stt_segments, res.captions_path)
    n_flagged = sum(1 for r in rows if r["flagged"])
    console.print(f"flagged {n_flagged}/{len(rows)} segments for review priority")

    # persist segments (replace any previous run of this job)
    with get_session() as session:
        from sqlmodel import delete

        session.exec(delete(Segment).where(Segment.job_id == job_id))
        for i, r in enumerate(rows):
            session.add(Segment(job_id=job_id, idx=i, **r))
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
        f"{stats['new_pairs']} new correction pairs, {stats['bumped']} reinforced"
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


@app.command()
def serve(
    port: int = typer.Option(8710, help="Port for the review web app"),
) -> None:
    """Start the review web app (http://localhost:8710)."""
    import uvicorn

    config.ensure_dirs()
    console.print(f"[bold green]review app:[/] http://localhost:{port}")
    uvicorn.run("jamak.web.app:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
