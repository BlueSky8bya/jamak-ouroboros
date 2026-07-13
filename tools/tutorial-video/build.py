"""Orchestrator: scripts -> TTS -> audio.wav + timing.json (-> Remotion mp4).

Usage (from tools/tutorial-video/):
    uv run --with edge-tts==7.2.8 python build.py            # audio for all 6
    uv run --with edge-tts==7.2.8 python build.py --courses 1
    uv run --with edge-tts==7.2.8 python build.py --voice ko-KR-InJoonNeural
    uv run --with edge-tts==7.2.8 python build.py --render    # + remotion mp4s

Console output is ASCII-safe (cp949 consoles — project rule); child process
output is captured and re-encoded with errors=replace.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

from audio import (
    build_track,
    decode_pcm,
    expected_duration,
    rms_of_window,
    write_timing,
    write_wav,
)
from parse_scripts import parse_all
from tts import DEFAULT_VOICE, ensure_line, preflight

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
PUBLIC = ROOT / "public"
FPS = 30
SILENCE_RMS_MAX = 0.005  # planted pauses must be dead silent (we wrote zeros)


def log(msg: str) -> None:
    # cp949-safe: replace anything the console can't encode
    enc = sys.stdout.encoding or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc))


async def build_course(n: int, slug: str, lines, voice: str) -> dict:
    course_dir = OUT / f"practice-{n}"
    synth_calls = 0
    line_pcm: dict[int, bytes] = {}
    for ln in lines:
        if ln.style == "침묵":
            continue
        mp3, fresh = await ensure_line(ln.text, ln.style, voice)
        synth_calls += int(fresh)
        line_pcm[ln.i] = decode_pcm(mp3)
        # keep per-line mp3s inspectable
        dst = course_dir / "lines" / f"{ln.i:02d}.mp3"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mp3, dst)

    pcm, cues = build_track(lines, line_pcm)
    dur = len(pcm) / 2 / 48000
    exp = expected_duration(lines, line_pcm)
    assert abs(dur - exp) < 1 / 48000, f"practice-{n}: duration {dur} != expected {exp}"

    # planted-silence assert: every pause >= 0.5s must be dead silent
    for c, ln in zip(cues, lines):
        if ln.pause_after >= 0.5:
            r = rms_of_window(pcm, c.end + 0.05, c.end + ln.pause_after - 0.05)
            assert r <= SILENCE_RMS_MAX, (
                f"practice-{n} line {ln.i}: pause RMS {r:.4f} > {SILENCE_RMS_MAX}"
            )

    write_wav(course_dir / "audio.wav", pcm)
    write_timing(course_dir / "timing.json", cues)

    # Remotion asset contract (PLAN §2.5): wav + timing under public/
    pub = PUBLIC / f"practice-{n}"
    pub.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(course_dir / "audio.wav", pub / "audio.wav")
    shutil.copyfile(course_dir / "timing.json", pub / "timing.json")

    return {
        "n": n,
        "slug": slug,
        "lines": len(lines),
        "duration": round(dur, 2),
        "synth_calls": synth_calls,
    }


def render_course(n: int, duration: float) -> None:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found on PATH")
    out_mp4 = OUT / f"practice-{n}.mp4"
    proc = subprocess.run(
        [
            npx,
            "remotion",
            "render",
            f"practice-{n}",
            str(out_mp4),
            "--codec",
            "h264",
        ],
        cwd=str(ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"remotion render practice-{n} failed: {err[-1500:]}")
    # ffprobe acceptance: resolution / fps / streams / duration vs wav
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height,avg_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(out_mp4),
        ],
        capture_output=True,
    )
    import json as _json

    info = _json.loads(probe.stdout.decode("utf-8", errors="replace"))
    streams = {s["codec_type"]: s for s in info["streams"]}
    assert "video" in streams and "audio" in streams, f"practice-{n}: missing stream"
    v = streams["video"]
    assert (v["width"], v["height"]) == (1920, 1080), f"practice-{n}: {v['width']}x{v['height']}"
    mp4_dur = float(info["format"]["duration"])
    assert abs(mp4_dur - duration) <= 1 / FPS + 0.05, (
        f"practice-{n}: mp4 {mp4_dur:.3f}s vs wav {duration:.3f}s"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--courses", default="1,2,3,4,5,6")
    ap.add_argument("--render", action="store_true", help="also render mp4s via remotion")
    args = ap.parse_args()

    wanted = {int(x) for x in args.courses.split(",")}
    courses = parse_all()
    log(f"parse OK: {sum(len(v[1]) for v in courses.values())} lines / 6 courses")
    await preflight(args.voice)
    log(f"voice OK: {args.voice}")

    total_synth = 0
    results = []
    for n, (slug, lines) in sorted(courses.items()):
        if n not in wanted:
            continue
        r = await build_course(n, slug, lines, args.voice)
        total_synth += r["synth_calls"]
        results.append(r)
        log(
            f"practice-{r['n']}: {r['lines']} lines, {r['duration']}s, "
            f"synth_calls={r['synth_calls']}"
        )
        if args.render:
            render_course(n, r["duration"])
            log(f"practice-{n}: mp4 rendered + probed OK")

    log(f"DONE, total synth calls this run = {total_synth}")


if __name__ == "__main__":
    asyncio.run(main())
