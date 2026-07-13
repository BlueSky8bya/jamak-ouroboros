"""verify_harness.py — Agent Harness structural integrity check.

Not a code test. Verifies that the repository's long-term memory structure
(protocol 260712) is intact: required docs exist, manifest paths resolve,
DECISION_INDEX links point at real files, and every BLOCKING rule is
classified with the fields its enforcement class requires.

Run:  uv run python scripts/agent-harness/verify_harness.py
Exit: 0 = OK, 1 = problems found (listed on stdout, ASCII only for cp949).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
problems: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        problems.append(msg)


def main() -> int:
    # 1) required agent docs
    required = [
        "AGENTS.md",
        "CLAUDE.md",
        "agent-harness.yaml",
        "docs/agent/CONSTITUTION.md",
        "docs/agent/CURRENT_STATE.md",
        "docs/agent/PROJECT_MAP.md",
        "docs/agent/RISK_PROFILE.md",
        "docs/agent/DEFINITION_OF_DONE.md",
        "docs/agent/CHANGELOG_AGENT.md",
        "docs/agent/DECISION_INDEX.md",
        "docs/agent/HARNESS_MIGRATION.md",
        "docs/agent/plans/ACTIVE_PLAN.md",
    ]
    for rel in required:
        check((ROOT / rel).exists(), f"missing required doc: {rel}")

    manifest_text = (ROOT / "agent-harness.yaml").read_text(encoding="utf-8")

    # 2) manifest protocol source is current
    check(
        "project-initializing_260712.md" in manifest_text,
        "agent-harness.yaml protocol_source is not 260712 (stale protocol?)",
    )

    # 3) every entrypoint path in the manifest resolves
    for m in re.finditer(r'^\s{2}[a-z_]+:\s+"([^"]+\.md)"', manifest_text, re.M):
        check((ROOT / m.group(1)).exists(), f"manifest entrypoint missing: {m.group(1)}")

    # 4) blocking rules: id present; MACHINE needs mechanism+trigger,
    #    UNENFORCED needs manual_gate+owner
    blocks = re.split(r"\n  - id: ", manifest_text)
    for block in blocks[1:]:
        rid = block.split('"')[1] if '"' in block else "?"
        if '"MACHINE"' in block:
            check("mechanism:" in block and "null" not in block.split("mechanism:")[1].split("\n")[0],
                  f"{rid}: MACHINE rule without a mechanism path")
            check("trigger:" in block, f"{rid}: MACHINE rule without a trigger")
            # mechanism file must exist if it names a repo script
            mm = re.search(r"mechanism:.*?(scripts/[\w./-]+)", block)
            if mm:
                check((ROOT / mm.group(1)).exists(), f"{rid}: mechanism script missing: {mm.group(1)}")
        elif '"UNENFORCED"' in block:
            check("manual_gate:" in block, f"{rid}: UNENFORCED rule without manual_gate")
            check("owner:" in block, f"{rid}: UNENFORCED rule without owner")
        else:
            check(False, f"{rid}: enforcement is neither MACHINE nor UNENFORCED")

    # 5) DECISION_INDEX links resolve
    idx = (ROOT / "docs/agent/DECISION_INDEX.md").read_text(encoding="utf-8")
    for m in re.finditer(r"\[(ADR|GDR)-\d+\]\(([^)]+)\)", idx):
        check((ROOT / "docs/agent" / m.group(2)).exists(),
              f"DECISION_INDEX link missing file: {m.group(2)}")

    # 6) DoD carries the Verification Capability Boundary
    dod = (ROOT / "docs/agent/DEFINITION_OF_DONE.md").read_text(encoding="utf-8")
    check("Verification Capability Boundary" in dod,
          "DEFINITION_OF_DONE.md lacks the Verification Capability Boundary table")

    # 7) doc-drift hook wiring (BR-DOCS-001 MACHINE claim)
    settings = ROOT / ".claude/settings.json"
    check(settings.exists(), ".claude/settings.json missing (doc-drift hook)")
    if settings.exists():
        check("doc-drift-check.ps1" in settings.read_text(encoding="utf-8"),
              ".claude/settings.json does not reference doc-drift-check.ps1")
    check((ROOT / "scripts/doc-drift-check.ps1").exists(),
          "scripts/doc-drift-check.ps1 missing")

    if problems:
        print("HARNESS CHECK: FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print("HARNESS CHECK: OK (all structural checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
