# Harness Migration — 260710 → 260712 (MODE D)

Date: 2026-07-13
From: `project-initializing_260710.md` (schema 1.0)
To: `project-initializing_260712.md` (schema 1.1)
Approved by: User ("전부 적용")

## Audit — what already complied (kept as-is)

- Repository-is-memory: CURRENT_STATE / CHANGELOG_AGENT(CHG-IDs with Change/Validation/Rollback) / ADR×8 + DECISION_INDEX / ACTIVE_PLAN / handoffs.
- Minimum necessary change, NOT VERIFIED discipline, supersede procedure — practiced.
- Doc-drift enforcement already MACHINE-grade: PostToolUse(Bash) hook → `scripts/doc-drift-check.ps1` (added 2026-07-12, commit c9f6e60).

## Gaps closed in this migration

| # | 260712 requirement | Action taken |
|---|---|---|
| 1 | `blocking_rules` manifest with MACHINE/UNENFORCED classification | `agent-harness.yaml` → schema 1.1, 5 rules registered (BR-DOCS-001 MACHINE, BR-DATA-001 / BR-FEEDBACK-001 / BR-SECRET-001 / BR-ADR-001 UNENFORCED) |
| 2 | Standard in-code Change Annotation `[WH-CHANGE ...]` | Policy added to AGENTS.md — applies to meaningful behavior changes **from now on** (no retrofit; existing free-form why-comments remain valid) |
| 3 | DoD Verification Capability Boundary (DIRECT/INDIRECT/DELEGATED/SHARED) | Table added to `DEFINITION_OF_DONE.md`, mapped to this project's real executors (agent env has no browser-YouTube playback, cloud deploy verified via /api/version, GPU pipeline local-only) |
| 4 | `verify-harness` script | `scripts/agent-harness/verify_harness.py` (doc existence, yaml paths, DECISION_INDEX links, blocking-rule integrity) + command registered in manifest |
| 5 | Decision Write-Through / Continuity-Break Handoff triggers | Rules added to AGENTS.md; Handoff written when a session ends with unpersisted state |

## Explicitly NOT changed

- Existing docs/ADRs/history: untouched (no re-initialization).
- Version policy (semver), risk profiles core (GENERAL + ML_EVALUATION; AUTH/DESTRUCTIVE_DATA added to reflect the live web app + single cloud DB — additive, not a rewrite).
- No retroactive WH-CHANGE annotations on old code.

## Rollback

Revert this migration commit; the 260710-era files are fully recoverable from git history.
