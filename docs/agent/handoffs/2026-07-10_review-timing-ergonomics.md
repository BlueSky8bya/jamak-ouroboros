# Handoff — Review Timing Ergonomics

Date: 2026-07-10
Risk: L1/L2

## Context

User reported heavy fatigue when subtitles are incorrectly split, repeated, or misaligned. The main issue was not only text accuracy, but losing orientation between the edited row, the playback position, and the subtitle boundary.

## What Changed

- `src/jamak/web/app.py`
  - Added `_join_dedup` and changed `merge-next` so repeated overlap is removed when adjacent subtitles are merged.
  - Added `POST /api/segments/{id}/boundary-next`: sets current segment end and next segment start to one time.
  - Added `POST /api/segments/{id}/redistribute-next`: redistributes current+next combined time span by current text length.
- `src/jamak/web/frontend/src/Editor.tsx`
  - Added separate playback vs editing status panel.
  - Added compact timing strip around focused/current time.
  - Added per-row playback rail for the segment currently under the video playhead.
  - Added row timing buttons: start, end, boundary, redistribute.
  - Focused row is now visually distinct from playback-active row.
- `src/jamak/web/frontend/src/api.ts`
  - Added boundary and redistribute client calls.
- `src/jamak/web/frontend/src/styles.css`
  - Added layout/styling for orientation panel, timing strip, row cue rail, and timing tools.

## Cost Decision

Everything added here is zero-API. Timing is based on current playback time, adjacent segment boundaries, and text-length weighting. No LLM or cloud speech calls are used.

## Validation

- `python -m compileall src/jamak` PASS.
- Temporary SQLite merge/boundary/redistribute spot check PASS.
- `npm.cmd run build` PASS.
- HTTP smoke PASS for `http://127.0.0.1:8710` and `/api/jobs`.
- `uv run jamak doctor` PARTIAL: ffmpeg missing in PATH; GPU, ctranslate2, API key, and DB OK.
- Browser visual check NOT VERIFIED: Browser plugin node_repl runtime failed with a sandbox setup error twice.

## Notes

- A FastAPI server was started in the background on `http://127.0.0.1:8710` using `.venv\Scripts\python.exe -m uvicorn jamak.web.app:app`.
- Vite dev server did not stay up; built frontend is served by FastAPI and was used for smoke checks.
- No DB schema changes were made.
