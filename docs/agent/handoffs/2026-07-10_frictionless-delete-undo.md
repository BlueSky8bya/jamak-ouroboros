# Handoff — Frictionless Delete And Undo

Date: 2026-07-10
Risk: L1/L2

## Context

User asked to remove the delete confirmation and rely on an Undo flow instead. They also asked for the review workspace to feel more polished and HCI-friendly.

## What Changed

- `src/jamak/web/app.py`
  - Added `SegmentSnapshot` / `RestoreSegmentsBody`.
  - Added `POST /api/jobs/{video_id}/segments/restore`, which restores a whole segment-list snapshot for one job.
- `src/jamak/web/frontend/src/api.ts`
  - Added `restoreSegments`.
- `src/jamak/web/frontend/src/Editor.tsx`
  - Delete button now deletes immediately.
  - Before split/merge/delete/timing actions, the current segment list is pushed to a one-step/multi-entry Undo stack.
  - `Ctrl+Z` restores the last segment operation when focus is outside inputs/textareas.
  - Text editing keeps native browser `Ctrl+Z`.
  - Added left-panel `되돌리기` button and work status text.
- `src/jamak/web/frontend/src/styles.css`
  - Polished left work panel, player frame, undo/status bar, and row hover state.

## Design Note

Undo is snapshot-based at the segment-list level. This makes delete/merge/split/timing recovery simple and robust without adding a DB schema table. Restore deletes current job segments and reinserts the snapshot. Translation rows for current segment ids are cleared during restore, which is safe but may require regeneration on translated export.

## Validation

- `python -m compileall src/jamak` PASS.
- Temporary SQLite delete -> restore spot check PASS.
- FastAPI TestClient restore route PASS.
- `npm.cmd run build` PASS.
- `uv run jamak doctor` PARTIAL: ffmpeg missing in PATH; GPU, ctranslate2, API key, and DB OK.

## Notes

- Background uvicorn launching was unreliable in this shell session after restarts; route-level validation was done with FastAPI TestClient.
- No DB schema changes were made.
