# Handoff - Pronoun-Safe Feedback Propagation

## Summary

The feedback loop now treats Korean pronouns and demonstrative references as contextual, not reusable correction pairs. This prevents cases like `그 여자` or `그 사람` being rewritten to `수로보가네` across later subtitles.

## Changed Files

- `src/jamak/learned_pairs.py`: new shared pair-safety rules.
- `src/jamak/feedback.py`: skips unsafe pairs during extraction/propagation and repairs previous unsafe unreviewed machine suggestions.
- `src/jamak/glossary.py`: excludes unsafe pairs from few-shot correction examples.
- `src/jamak/pipeline/correct.py`: excludes unsafe pre-pass pairs, adds prompt rule, bumps `PROMPT_VERSION` to `v3`.
- `docs/agent/CURRENT_STATE.md`, `docs/agent/CHANGELOG_AGENT.md`, completed plan.

## Verification

- Learned-pair guard smoke: PASS.
- Feedback extraction/propagation smoke: PASS.
- Pre-pass/prompt smoke: PASS.
- Reviewed bad-LLM pair extraction blocked: PASS.
- Current DB visible unreviewed over-propagation residue after repair: 0 matches.
- `.venv\Scripts\python.exe -m compileall src/jamak`: PASS.
- `git diff --check`: PASS, line-ending warnings only.

## Notes

Unsafe correction rows already in `data/jamak.db` were not deleted; they are ignored by the runtime filters. One current unreviewed machine-suggestion over-propagation in `lFuxxOlgl5Y` was repaired through the project repair function.
