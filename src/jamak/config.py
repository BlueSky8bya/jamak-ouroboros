"""Project-wide paths and settings.

All paths are resolved relative to the project root so the folder can be
renamed or moved freely (asdf -> jamak-ouroboros -> wherever).
"""

from __future__ import annotations

import os
from pathlib import Path


def find_project_root() -> Path:
    """Walk up from this file until we find pyproject.toml."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: cwd (e.g. running from an installed wheel)
    return Path.cwd()


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
SEEDS_DIR = DATA_DIR / "seeds"
DB_PATH = DATA_DIR / "jamak.db"

# STT settings tuned for RTX 4060 Ti 8GB
WHISPER_MODEL = os.environ.get("JAMAK_WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("JAMAK_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = os.environ.get("JAMAK_WHISPER_COMPUTE", "int8_float16")

# LLM correction
CLAUDE_MODEL = os.environ.get("JAMAK_CLAUDE_MODEL", "claude-sonnet-5")

# Korean subtitle conventions
MAX_CHARS_PER_LINE = 18
MAX_LINES = 2
MIN_SEGMENT_SECONDS = 1.0
MAX_SEGMENT_SECONDS = 7.0


def ensure_dirs() -> None:
    for d in (DATA_DIR, JOBS_DIR, SEEDS_DIR):
        d.mkdir(parents=True, exist_ok=True)
