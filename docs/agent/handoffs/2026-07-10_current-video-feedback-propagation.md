# Handoff — Current-Video Feedback Propagation

Date: 2026-07-10
Risk: L2

## Context

User reported that learning should reduce repeated corrections inside the current review session, not only improve the next video. Example class: one recurring misrecognition can force the reviewer to fix the same phrase many times.

## What Changed

- `src/jamak/feedback.py`
  - `absorb_job` now gathers correction pairs with the reviewed segment idx.
  - Pairs confirmed in the current video are applied only to later unreviewed segments.
  - Globally confirmed pairs (`count >= PREPASS_MIN_COUNT`) still apply to any unreviewed segment.
  - Return stats now include `propagated_segments`, `propagated_replacements`, and `propagation_pairs`.
  - Job status becomes `done` only when all segments are reviewed; partial absorbs keep it `reviewing`.
- `src/jamak/web/app.py`
  - Export now runs absorb before reading segments, so same-video propagation is included in downloaded SRT files.
- `src/jamak/web/frontend/src/Editor.tsx`
  - Pending autosaves are awaited before absorb/export/back.
  - After absorb, the segment list is fetched again so current-video draft updates are visible immediately.
- `src/jamak/cli.py`, `api.ts`
  - Updated stats/reporting.

## Cost Decision

Default path remains zero API calls. The system uses deterministic word-boundary replacement for learned pairs. A future optional improvement could add a targeted LLM recheck only for later unreviewed segments containing newly learned wrong phrases, but that should be opt-in because it spends API budget.

## Validation

- `python -m compileall src/jamak` PASS.
- Temporary SQLite spot check PASS: before-reviewed unreviewed segment stayed unchanged; after-reviewed unreviewed segment was updated.
- `npm.cmd run build` PASS.
- `uv run jamak doctor` PARTIAL: ffmpeg missing in PATH; GPU, ctranslate2, API key, and DB OK.

## Notes

- An initial spot-check script accidentally wrote a synthetic `video_id='spot'` job and `wrongterm -> rightterm` correction into the real DB because `db.DB_PATH` was not patched. A guarded cleanup verified exact synthetic contents and removed only those rows; follow-up read confirmed they no longer exist.
- Physical folder rename from `C:\Projects\asdf` to `C:\Projects\jamak-ouroboros` was attempted with escalation and failed because Windows reported the folder is used by another process. The code is path-independent; retry after closing Codex/terminals that have the folder as cwd.
