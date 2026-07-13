"""edge-tts synthesis with content-hash caching (PLAN.md §2.3).

Reproducibility contract:
- cache key = pipeline version + voice + style params + post-processing
  params + line text, so editing a line (or any knob) regenerates exactly
  the affected mp3s and nothing else;
- limited retries with backoff (edge-tts is an online service);
- atomic writes — a partially downloaded file never becomes a cache hit.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

import edge_tts

# Bump to invalidate every cached synth (e.g. after changing this module's logic).
PIPELINE_VERSION = "1"

DEFAULT_VOICE = "ko-KR-SunHiNeural"
RATE = {"보통": "-5%", "빠르게": "+40%", "느리게": "-20%", "웅얼": "+30%"}
# 🙉 bait: quiet + muffled so the line is genuinely hard to make out.
MUMBLE_FILTER = "volume=0.35,lowpass=f=700"

CACHE_DIR = Path(__file__).resolve().parent / "cache"
RETRIES = 3


def cache_path(text: str, style: str, voice: str) -> Path:
    post = MUMBLE_FILTER if style == "웅얼" else ""
    key = "|".join([PIPELINE_VERSION, voice, style, RATE[style], post, text])
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.mp3"


def _atomic_replace(tmp: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, dst)


async def _synth_once(text: str, voice: str, rate: str, dst: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(suffix=".mp3", dir=str(CACHE_DIR))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        await edge_tts.Communicate(text, voice, rate=rate).save(str(tmp))
        if tmp.stat().st_size == 0:
            raise RuntimeError("edge-tts wrote an empty file")
        _atomic_replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def _mumble_postprocess(src: Path, dst: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(suffix=".mp3", dir=str(CACHE_DIR))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        run_ffmpeg(["-i", str(src), "-af", MUMBLE_FILTER, "-y", str(tmp)])
        _atomic_replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def run_ffmpeg(args: list[str]) -> bytes:
    """Run ffmpeg capturing output as bytes (decoded UTF-8-safe by callers —
    never let a cp949 console choke on ffmpeg/edge-tts stderr, PLAN §2.3)."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"ffmpeg failed: {err[:500]}")
    return proc.stdout


async def preflight(voice: str) -> None:
    """Fail fast if the requested voice doesn't exist (PLAN §2.3)."""
    voices = await edge_tts.list_voices()
    names = {v["ShortName"] for v in voices}
    if voice not in names:
        ko = sorted(n for n in names if n.startswith("ko-"))
        raise RuntimeError(f"voice {voice!r} not available; korean voices: {ko}")


async def ensure_line(text: str, style: str, voice: str) -> tuple[Path, bool]:
    """Return (mp3 path, synthesized_now). Cache hit = no network call."""
    dst = cache_path(text, style, voice)
    if dst.exists():
        return dst, False
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rate = RATE[style]
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            if style == "웅얼":
                # synth clean first, then degrade — keeps the degradation
                # parameters in the cache key, not in the voice output.
                fd, raw_name = tempfile.mkstemp(suffix=".mp3", dir=str(CACHE_DIR))
                os.close(fd)
                raw = Path(raw_name)
                try:
                    await edge_tts.Communicate(text, voice, rate=rate).save(str(raw))
                    if raw.stat().st_size == 0:
                        raise RuntimeError("edge-tts wrote an empty file")
                    _mumble_postprocess(raw, dst)
                finally:
                    if raw.exists():
                        raw.unlink()
            else:
                await _synth_once(text, voice, rate, dst)
            return dst, True
        except Exception as e:  # noqa: BLE001 — retry any transient failure
            last = e
            await asyncio.sleep(2**attempt)
    raise RuntimeError(f"TTS failed after {RETRIES} tries for line {text[:30]!r}: {last}")
