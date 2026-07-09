# Handoff - Standalone Audience Response Filter

## Summary

New subtitle jobs now remove very short standalone audience response cells before crosscheck and DB persistence. This targets review-noise cells like `네` that come from audience replies in lectures.

## Changed Files

- `src/jamak/pipeline/noise.py`: new deterministic filter helper.
- `src/jamak/cli.py`: applies the filter after STT splitting and reports removed count.
- `docs/agent/CURRENT_STATE.md`: updated current status and verification.
- `docs/agent/CHANGELOG_AGENT.md`: added CHG-20260710-016.
- `docs/agent/plans/completed/PLAN-20260710-008.md`: completed plan.

## Verification

- Local Python smoke checks: PASS.
- Segment-list filter smoke: PASS.
- `python -m compileall src/jamak`: PASS.
- `git diff --check`: PASS, line-ending warnings only.

## Notes

The filter is intentionally conservative. It removes `네`, `네네`, `예`, `예예`, and `넵` after punctuation/spacing normalization, but keeps sentence forms such as `네 맞습니다`.
