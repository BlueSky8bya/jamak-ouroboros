"""Stage 1 — Ingest: download audio, YouTube auto-captions, and metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

from ..config import JOBS_DIR


@dataclass
class IngestResult:
    video_id: str
    title: str
    channel: str
    duration_seconds: float
    upload_date: str  # YouTube upload date, YYYYMMDD ('' if unknown)
    audio_path: Path
    captions_path: Path | None  # ko auto-captions (json3), None if unavailable
    job_dir: Path


def extract_video_id(url: str) -> str:
    # [WH-CHANGE v0.9.22 | FIX | 2026-07-15 | CHG-20260715-043]
    # Reason: 라이브(였던) 영상 링크는 /live/<id> 형식이라 안 걸렸음 — 재생은
    #   일반 영상과 동일(11자 video_id)이니 지원해야 한다. /embed/도 함께 추가.
    # Related: CHANGELOG CHG-20260715-043.
    m = re.search(
        r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})", url
    )
    if not m:
        raise ValueError(f"Cannot extract video id from URL: {url}")
    return m.group(1)


def fetch_upload_date(video_id: str) -> str:
    """Metadata-only fetch of the YouTube upload date (YYYYMMDD).

    Used to backfill jobs ingested before we captured the date. No media
    is downloaded.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return info.get("upload_date") or ""


def ingest(url: str) -> IngestResult:
    video_id = extract_video_id(url)
    job_dir = JOBS_DIR / video_id
    job_dir.mkdir(parents=True, exist_ok=True)

    audio_path = job_dir / "audio.wav"
    info_path = job_dir / "info.json"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(job_dir / "audio.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
        # 16kHz mono: exactly what whisper wants, keeps files small
        "postprocessor_args": {"extractaudio": ["-ar", "16000", "-ac", "1"]},
        "writeautomaticsub": True,
        "subtitleslangs": ["ko"],
        "subtitlesformat": "json3",
        "quiet": True,
        "no_warnings": True,
    }

    if audio_path.exists() and info_path.exists():
        # Already ingested — reuse (jobs are resumable per stage)
        info = json.loads(info_path.read_text(encoding="utf-8"))
    else:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
        info_path.write_text(
            json.dumps(
                {
                    "id": info["id"],
                    "title": info.get("title", ""),
                    "channel": info.get("channel", ""),
                    "duration": info.get("duration", 0),
                    "upload_date": info.get("upload_date", ""),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        info = json.loads(info_path.read_text(encoding="utf-8"))

    captions = next(iter(job_dir.glob("*.ko.json3")), None)

    return IngestResult(
        video_id=info["id"],
        title=info.get("title", ""),
        channel=info.get("channel", ""),
        duration_seconds=float(info.get("duration", 0)),
        upload_date=info.get("upload_date", ""),
        audio_path=audio_path,
        captions_path=captions,
        job_dir=job_dir,
    )
