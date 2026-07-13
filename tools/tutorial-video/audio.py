"""PCM assembly + timing (PLAN.md §2.4).

Never concat mp3s: encoder delay accumulates and sample rates can disagree.
Every line is decoded to one fixed PCM format first; silence is generated as
an exact sample count; timings are computed from PCM sample offsets, so
timing.json is exact by construction.
"""

from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path

from parse_scripts import Line
from tts import run_ffmpeg

SR = 48000
BYTES_PER_SAMPLE = 2  # s16 mono
HEAD_TAIL_PAD = 1.5  # seconds of silence at both ends (youtube intro clipping)


def decode_pcm(mp3: Path) -> bytes:
    """mp3 -> 48 kHz mono s16 raw PCM."""
    return run_ffmpeg(
        ["-i", str(mp3), "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"]
    )


def _silence(seconds: float) -> bytes:
    return b"\x00" * (round(seconds * SR) * BYTES_PER_SAMPLE)


@dataclass
class Cue:
    i: int
    text: str
    style: str
    start: float
    end: float


def build_track(lines: list[Line], line_pcm: dict[int, bytes]) -> tuple[bytes, list[Cue]]:
    """Assemble the full track; return (pcm, cues with sample-exact times)."""
    parts: list[bytes] = [_silence(HEAD_TAIL_PAD)]
    n_samples = round(HEAD_TAIL_PAD * SR)
    cues: list[Cue] = []
    for ln in lines:
        start = n_samples / SR
        if ln.style != "침묵":
            pcm = line_pcm[ln.i]
            parts.append(pcm)
            n_samples += len(pcm) // BYTES_PER_SAMPLE
        end = n_samples / SR
        cues.append(Cue(i=ln.i, text=ln.text, style=ln.style, start=start, end=end))
        parts.append(_silence(ln.pause_after))
        n_samples += round(ln.pause_after * SR)
    parts.append(_silence(HEAD_TAIL_PAD))
    n_samples += round(HEAD_TAIL_PAD * SR)
    pcm = b"".join(parts)
    assert len(pcm) == n_samples * BYTES_PER_SAMPLE, "sample bookkeeping drifted"
    return pcm, cues


def expected_duration(lines: list[Line], line_pcm: dict[int, bytes]) -> float:
    """PLAN §2.4-5: 2*pad + sum(speech samples/SR + pause)."""
    total = 2 * HEAD_TAIL_PAD
    for ln in lines:
        if ln.style != "침묵":
            total += (len(line_pcm[ln.i]) // BYTES_PER_SAMPLE) / SR
        total += ln.pause_after
    return total


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(BYTES_PER_SAMPLE)
        w.setframerate(SR)
        w.writeframes(pcm)


def write_timing(path: Path, cues: list[Cue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "i": c.i,
                    "text": c.text,
                    "style": c.style,
                    "start": round(c.start, 4),
                    "end": round(c.end, 4),
                }
                for c in cues
            ],
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def rms_of_window(pcm: bytes, start_s: float, end_s: float) -> float:
    """RMS (0..1) of a window — used to assert planted silences (PLAN §2.6)."""
    import array

    a = array.array("h")
    lo = round(start_s * SR) * BYTES_PER_SAMPLE
    hi = round(end_s * SR) * BYTES_PER_SAMPLE
    a.frombytes(pcm[lo:hi])
    if not a:
        return 0.0
    acc = 0
    for v in a:
        acc += v * v
    return (acc / len(a)) ** 0.5 / 32768.0
