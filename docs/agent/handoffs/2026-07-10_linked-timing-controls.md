# Handoff — Linked Timing Controls

Date: 2026-07-10
Risk: L1/L2

## Context

User found the four timing buttons (`시작`, `끝`, `경계`, `나눔`) conceptually fuzzy. They also pointed out that when setting an end time, the next subtitle should be adjusted to at least the same or later time automatically.

## What Changed

- `src/jamak/web/app.py`
  - Added `_previous_segment`.
  - Added `POST /api/segments/{id}/boundary-prev` to move previous end and current start together.
  - Updated `POST /api/segments/{id}/boundary-next` so it also works for the last segment by setting only current end.
  - Updated `PUT /api/segments/{id}` so manual `start`/`end` edits prevent overlaps by minimally adjusting previous/next segment timing.
- `src/jamak/web/frontend/src/Editor.tsx`
  - Replaced visible timing controls with two actions:
    - `여기서 시작`: current playback time becomes previous/current boundary.
    - `여기서 넘김`: current playback time becomes current/next boundary.
  - Last row shows `여기서 끝`.
  - Manual time edits refresh all segments so neighbor changes are visible immediately.
- `src/jamak/web/frontend/src/api.ts`
  - Added `boundaryPrev`.

## Cost Decision

Zero API. All behavior is deterministic local timing adjustment.

## Validation

- `python -m compileall src/jamak` PASS.
- Temporary SQLite linked timing spot check PASS.
- `npm.cmd run build` PASS.
- HTTP smoke `http://127.0.0.1:8710` PASS.

## Notes

- The previous `redistribute-next` backend/API function remains available, but the visible row button was removed to reduce cognitive load.
- The FastAPI server was restarted and is serving the new built assets on `http://127.0.0.1:8710`.
