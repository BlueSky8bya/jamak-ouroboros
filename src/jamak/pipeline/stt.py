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
    hotwords: str = "",
    force: bool = False,
) -> list[SttSegment]:
    """Run whisper; cache the result as stt.json inside the job dir.

    force=True ignores (and overwrites) the cache so a "re-transcribe" with a
    richer glossary actually re-runs STT instead of replaying old segments.
    """
    cache = job_dir / "stt.json"
    if cache.exists() and not force:
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
        vad_parameters={
            # lectures have long applause gaps; don't glue speech across them
            "min_silence_duration_ms": 700,
            # more sensitive so quiet / over-music opening speech isn't dropped
            # (was defaulting to 0.5, which trimmed the speaker's intro)
            "threshold": 0.35,
            # keep a little audio around detected speech so word edges and the
            # very first words aren't clipped
            "speech_pad_ms": 400,
        },
        # NOTE: we deliberately do NOT pass a keyword-list initial_prompt.
        # faster-whisper emits the initial_prompt verbatim over silent/applause
        # stretches (prompt-echo hallucination), which is exactly the "신인,
        # 축지법... 나옵니다" garbage repeated for dozens of segments. Domain
        # vocabulary is biased via `hotwords` (acoustic decoder) instead, which
        # is not emitted as text. Caller may still force a prompt if needed.
        initial_prompt=initial_prompt or None,
        hotwords=hotwords or None,
        # False so a single hallucination is NOT carried into the next window
        # and repeated across dozens of consecutive segments (the cascade the
        # user saw). Each window decodes independently.
        condition_on_previous_text=False,
        # drop windows whose decode is a repetitive loop, and skip silent
        # windows where whisper tends to regurgitate/loop
        compression_ratio_threshold=2.4,
        no_repeat_ngram_size=3,
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
