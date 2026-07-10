"""Turn finished reviews into a Whisper fine-tuning corpus.

Every human-reviewed subtitle is an (audio-clip, correct-text) pair — the
exact supervision Whisper needs to learn to *hear* 축지법 / 하늘궁 / 경상도
사투리 acoustically, instead of leaning on the Claude correction stage.

This module only builds the dataset (API-free, local ffmpeg). The training
step itself is M5 — see docs/agent/decisions/ADR-0004. Accumulate enough
pairs first, then fine-tune (LoRA) and convert back to CTranslate2.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from sqlmodel import select

from .config import DATA_DIR, JOBS_DIR
from .db import Job, Segment, get_session

TRAINING_DIR = DATA_DIR / "training"
CORRECTIONS_DIR = TRAINING_DIR / "corrections"
MIN_DURATION = 0.4
MAX_DURATION = 30.0  # whisper training clips must stay under 30s


def _slice(audio: Path, start: float, end: float, out: Path) -> bool:
    """Cut [start,end] out of audio.wav as 16k mono wav. False on failure."""
    out.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(audio),
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-ar", "16000", "-ac", "1",
            str(out),
        ],
        capture_output=True,
    )
    return r.returncode == 0 and out.exists()


def export_training_data(out_dir: Path = TRAINING_DIR, make_clips: bool = True) -> dict:
    """Build (clip, text) pairs from every reviewed subtitle.

    Writes out_dir/<video_id>/<idx>.wav and a single manifest.jsonl the
    HuggingFace `audiofolder` / a custom Whisper trainer can consume.
    Only human-reviewed segments with non-empty final text are exported.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    rows: list[dict] = []
    skipped_no_audio = 0

    with get_session() as session:
        jobs = session.exec(select(Job)).all()
        for job in jobs:
            audio = JOBS_DIR / job.video_id / "audio.wav"
            segs = session.exec(
                select(Segment)
                .where(
                    Segment.job_id == job.id,
                    Segment.reviewed == True,  # noqa: E712
                )
                .order_by(Segment.idx)
            ).all()
            for seg in segs:
                text = seg.text_final.strip()
                dur = seg.end - seg.start
                if not text or dur < MIN_DURATION or dur > MAX_DURATION:
                    continue
                if not audio.exists():
                    skipped_no_audio += 1
                    continue
                clip = out_dir / job.video_id / f"{seg.idx:05d}.wav"
                if make_clips and not clip.exists() and not _slice(
                    audio, seg.start, seg.end, clip
                ):
                    continue
                rows.append(
                    {
                        "audio": str(clip.relative_to(out_dir)).replace("\\", "/"),
                        "text": text,
                        "video_id": job.video_id,
                        "start": round(seg.start, 3),
                        "end": round(seg.end, 3),
                        "duration": round(dur, 3),
                    }
                )

    manifest.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    total_sec = sum(r["duration"] for r in rows)
    return {
        "pairs": len(rows),
        "minutes": round(total_sec / 60, 1),
        "skipped_no_audio": skipped_no_audio,
        "manifest": str(manifest),
    }


def export_correction_pairs(out_dir: Path = CORRECTIONS_DIR) -> dict:
    """Build (whisper draft -> human final) text pairs for a correction model.

    The long-term plan (ADR-0005) is to fine-tune a small local Korean LLM on
    exactly this project's correction behavior — fixing misheard words while
    KEEPING dialect/구어체 and never rewriting pronouns — so the per-video
    Claude correction call can eventually be replaced with a free local model.
    The training targets are the human-reviewed finals, so a model trained on
    them inherits those constraints instead of standardizing the text.

    API-free. Emits JSONL with the raw fields (whisper, youtube reference,
    final); prompt formatting is a training-time concern. Both changed and
    unchanged pairs are kept — unchanged ones teach the model when NOT to edit.
    Gap/echo-filled segments (no real whisper text) are excluded: they are not
    whisper-correction examples.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "manifest.jsonl"
    rows: list[dict] = []
    changed = 0

    with get_session() as session:
        jobs = session.exec(select(Job)).all()
        for job in jobs:
            segs = session.exec(
                select(Segment)
                .where(
                    Segment.job_id == job.id,
                    Segment.reviewed == True,  # noqa: E712
                )
                .order_by(Segment.idx)
            ).all()
            for seg in segs:
                whisper = seg.text_whisper.strip()
                final = seg.text_final.strip()
                if not whisper or not final:
                    continue  # gap/echo-filled or empty — not a correction pair
                is_changed = whisper != final
                if is_changed:
                    changed += 1
                rows.append(
                    {
                        "whisper": whisper,
                        "youtube": seg.text_youtube.strip(),
                        "final": final,
                        "changed": is_changed,
                        "video_id": job.video_id,
                        "idx": seg.idx,
                    }
                )

    manifest.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return {
        "pairs": len(rows),
        "changed": changed,
        "unchanged": len(rows) - changed,
        "manifest": str(manifest),
    }
