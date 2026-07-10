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

# STT settings tuned for RTX 4060 Ti 8GB.
# large-v3-turbo beats large-v3 on these lectures: it transcribes the opening
# (large-v3 dropped 0-21s), covers more audio, mishears fewer words (부부싸움
# vs large-v3's "보고삼"), and is faster — with no prompt-echo either. Measured
# on LI3phxRnkMM: first speech 21.1s -> 2.2s, YouTube gap-fill 28 -> 9.
WHISPER_MODEL = os.environ.get("JAMAK_WHISPER_MODEL", "large-v3-turbo")
WHISPER_DEVICE = os.environ.get("JAMAK_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE = os.environ.get("JAMAK_WHISPER_COMPUTE", "int8_float16")

# LLM stages — override per stage to trade quality for cost
# (e.g. JAMAK_TRANSLATE_MODEL=claude-haiku-4-5 is ~3x cheaper)
CLAUDE_MODEL = os.environ.get("JAMAK_CLAUDE_MODEL", "claude-sonnet-5")
CORRECT_MODEL = os.environ.get("JAMAK_CORRECT_MODEL", CLAUDE_MODEL)
TRANSLATE_MODEL = os.environ.get("JAMAK_TRANSLATE_MODEL", CLAUDE_MODEL)

# learned pairs confirmed this many times are applied as free string
# replacement before the LLM sees the text (ouroboros -> fewer API tokens)
PREPASS_MIN_COUNT = 2

# Korean subtitle conventions
MAX_CHARS_PER_LINE = 18
MAX_LINES = 2
MIN_SEGMENT_SECONDS = 1.0
MAX_SEGMENT_SECONDS = 7.0


def ensure_dirs() -> None:
    for d in (DATA_DIR, JOBS_DIR, SEEDS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _load_api_key_fallback() -> None:
    """Windows: processes launched before the User env var was set don't
    inherit ANTHROPIC_API_KEY — fall back to reading it from the registry
    so `jamak serve` / `jamak run` work without a shell restart."""
    import sys

    if os.environ.get("ANTHROPIC_API_KEY") or sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            value, _ = winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")
            if value:
                os.environ["ANTHROPIC_API_KEY"] = value
    except OSError:
        pass


_load_api_key_fallback()
