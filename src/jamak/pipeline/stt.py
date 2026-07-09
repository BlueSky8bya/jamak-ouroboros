"""Stage 2 — STT: faster-whisper large-v3 with word timestamps.

The initial_prompt is seeded from the glossary (ouroboros input #1):
whisper biases decoding toward vocabulary it has seen in the prompt,
which is the cheapest way to make it hear 축지법 instead of 축제법.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import WHISPER_COMPUTE, WHISPER_DEVICE, WHISPER_MODEL


def _register_cuda_dlls() -> None:
    """Windows: pip-installed cuBLAS/cuDNN DLLs live inside site-packages
    (nvidia/*/bin) and are not on PATH — register them so ctranslate2
    can load cublas64_12.dll etc."""
    import os
    import sys

    if sys.platform != "win32":
        return
    for site in sys.path:
        nvidia_dir = Path(site) / "nvidia"
        if not nvidia_dir.is_dir():
            continue
        for bin_dir in nvidia_dir.glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            # ctranslate2 resolves CUDA DLLs via PATH, not the
            # add_dll_directory search list — need both
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ["PATH"]


@dataclass
class Word:
    start: float
    end: float
    word: str
    probability: float


@dataclass
class SttSegment:
    start: float
    end: float
    text: str
    words: list[Word]
    avg_logprob: float


def transcribe(
    audio_path: Path,
    job_dir: Path,
    initial_prompt: str = "",
    progress_callback=None,
) -> list[SttSegment]:
    """Run whisper; cache the result as stt.json inside the job dir."""
    cache = job_dir / "stt.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return [
            SttSegment(
                start=s["start"],
                end=s["end"],
                text=s["text"],
                words=[Word(**w) for w in s["words"]],
                avg_logprob=s["avg_logprob"],
            )
            for s in raw
        ]

    _register_cuda_dlls()
    from faster_whisper import WhisperModel  # heavy import, keep it lazy

    model = WhisperModel(
        WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE
    )

    segments_iter, info = model.transcribe(
        str(audio_path),
        language="ko",
        word_timestamps=True,
        vad_filter=True,
        # lectures have long applause gaps; don't glue speech across them
        vad_parameters={"min_silence_duration_ms": 700},
        initial_prompt=initial_prompt or None,
        condition_on_previous_text=True,
        # skip silent windows where whisper tends to regurgitate the
        # initial_prompt / loop; the crosscheck stage also filters echoes
        hallucination_silence_threshold=2.0,
    )

    results: list[SttSegment] = []
    for seg in segments_iter:
        results.append(
            SttSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                words=[
                    Word(w.start, w.end, w.word, w.probability)
                    for w in (seg.words or [])
                ],
                avg_logprob=seg.avg_logprob,
            )
        )
        if progress_callback:
            progress_callback(seg.end, info.duration)

    cache.write_text(
        json.dumps([asdict(s) for s in results], ensure_ascii=False),
        encoding="utf-8",
    )
    return results
