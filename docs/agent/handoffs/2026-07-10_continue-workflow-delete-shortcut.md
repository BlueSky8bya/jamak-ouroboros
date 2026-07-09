# Handoff — Continue Workflow And Delete Shortcut

Date: 2026-07-10

## What Changed

- Review filters were removed from the editor. The right pane now always shows the full subtitle list.
- The left panel has a single `이어서 작업하기` button. It flushes pending row edits, finds the next unreviewed subtitle after the focused/current subtitle, seeks the video there, and focuses the row.
- Pressing Enter in a subtitle textarea now confirms the row and moves to that same next-work target rather than a filtered visible list.
- Pressing `Delete` outside text inputs deletes the focused/current subtitle immediately. The operation goes through the existing segment undo snapshot, so `Ctrl+Z` restores it.

## Files

- `src/jamak/web/frontend/src/Editor.tsx`
- `src/jamak/web/frontend/src/styles.css`
- `src/jamak/web/frontend/src/types.ts`

## Verification

- `python -m compileall src/jamak` PASS.
- `npm.cmd run build` PASS.
- `git diff --check` PASS, with only existing CRLF warnings.
- Browser visual check NOT VERIFIED. The in-app browser/node runtime failed with `windows sandbox failed: spawn setup refresh`.

## Notes

- Starting `jamak serve` in the foreground works when `UV_CACHE_DIR=C:\Projects\asdf\.uv-cache` is set and `--port 8710` is used. Background `Start-Process` attempts in this session did not stay alive, so the visual check was skipped rather than claimed.

