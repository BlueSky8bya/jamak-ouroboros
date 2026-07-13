"""Parse docs/tutorial/scripts/연습N-*.md tables into per-course line lists.

The script tables are both the human-review document and the machine input
for the render pipeline (PLAN.md §2.2). Any malformed row fails loudly with
file + line number — silent skips would desync the video from the course.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "tutorial" / "scripts"
STYLES = {"보통", "빠르게", "느리게", "웅얼", "침묵"}
# PLAN.md §2.2: total spoken-line count contract. Update together with scripts.
EXPECTED_TOTAL = 77


@dataclass
class Line:
    i: int
    text: str
    style: str
    pause_after: float


def _is_separator(cell: str) -> bool:
    return bool(cell) and set(cell) <= {"-", ":"}


def parse_file(path: Path) -> list[Line]:
    lines: list[Line] = []
    expected_i = 1
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) != 4:
            continue  # not a script row (e.g. prose containing a pipe)
        if cells[0] in ("#", "") or _is_separator(cells[0]):
            continue  # header / separator
        where = f"{path.name}:{lineno}"
        if not cells[0].isdigit():
            raise ValueError(f"{where}: row number not an integer: {cells[0]!r}")
        i = int(cells[0])
        if i != expected_i:
            raise ValueError(f"{where}: row number {i}, expected {expected_i}")
        expected_i += 1
        text, style, pause_raw = cells[1], cells[2], cells[3]
        if style not in STYLES:
            raise ValueError(f"{where}: unknown style {style!r} (allowed: {sorted(STYLES)})")
        if style != "침묵" and not text:
            raise ValueError(f"{where}: empty text on a spoken row")
        try:
            pause = float(pause_raw)
        except ValueError:
            raise ValueError(f"{where}: pause not a number: {pause_raw!r}") from None
        if not 0 <= pause <= 30:
            raise ValueError(f"{where}: pause {pause} out of sane range [0, 30]")
        lines.append(Line(i=i, text=text, style=style, pause_after=pause))
    if not lines:
        raise ValueError(f"{path.name}: no script rows found")
    return lines


def parse_all() -> dict[int, tuple[str, list[Line]]]:
    """Return {course_n: (title_slug, lines)} for 연습1..연습6."""
    out: dict[int, tuple[str, list[Line]]] = {}
    for path in sorted(SCRIPTS_DIR.glob("연습*-*.md")):
        m = re.match(r"연습(\d)-(.+)\.md$", path.name)
        if not m:
            raise ValueError(f"unexpected script filename: {path.name}")
        n = int(m.group(1))
        if n in out:
            raise ValueError(f"duplicate course number {n}: {path.name}")
        out[n] = (m.group(2), parse_file(path))
    if sorted(out) != [1, 2, 3, 4, 5, 6]:
        raise ValueError(f"expected courses 1..6, found {sorted(out)}")
    total = sum(len(v[1]) for v in out.values())
    if total != EXPECTED_TOTAL:
        raise ValueError(
            f"total line count {total} != contract {EXPECTED_TOTAL} "
            f"(PLAN.md §2.2 — update both together)"
        )
    return out


if __name__ == "__main__":
    courses = parse_all()
    for n, (slug, lines) in sorted(courses.items()):
        styles = {}
        for ln in lines:
            styles[ln.style] = styles.get(ln.style, 0) + 1
        print(f"practice-{n} ({len(lines)} lines) styles={styles}")
    print("PARSE OK, total =", sum(len(v[1]) for v in courses.values()))
