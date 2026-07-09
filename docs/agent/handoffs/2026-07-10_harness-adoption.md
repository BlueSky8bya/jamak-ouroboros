# Handoff Snapshot

Created: 2026-07-10
Agent / Tool: Claude Code (Fable 5)
Task: 초기 구축(M0~M2 코드) + WHITEHAVEN Harness 도입
Risk Level: L2
Project Version: 0.1.0

## Session Goal

빈 폴더 → 자막 파이프라인 스캐폴드 → M1 검증 → 하네스 도입.

## Completed

- M0/M1 완료 (커밋 061638c, 74b9cc0), M1 실영상 검증 PASS
- seed-import: 103개 강연 → 용어 후보 500개 (미승인)
- WHITEHAVEN Harness MODE C 도입 (agent-harness.yaml, AGENTS.md, docs/agent/*)

## Validation Evidence

- `uv run jamak doctor` → PASS (API 키 WARN)
- `uv run jamak run https://youtu.be/lFuxxOlgl5Y` → PASS (104 세그먼트, 59 flagged, LLM 교정 스킵)
- LLM 교정 → NOT VERIFIED

## Failed Attempts

- cuBLAS DLL 로드: `os.add_dll_directory`만으로 실패 → PATH 주입 병행으로 해결 (CHG-20260710-002)
- 세션 내 폴더 rename: cwd 잠금으로 불가 → 세션 밖에서 수행하기로

## Open Questions

- ISSUE-001: 검수 코퍼스 GitHub 공개 유지 여부 (사용자 답변 대기)
- 테스트 스위트 도입 시점

## Next Exact Step

1. `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; uv run jamak run "https://youtu.be/lFuxxOlgl5Y"`
2. `data/jobs/lFuxxOlgl5Y/lFuxxOlgl5Y.draft.srt`에서 에스더/수가성/우물가 교정 확인
3. ACTIVE_PLAN M3-A 진행

## Rollback

하네스 문서 전체는 신규 파일 — 삭제로 롤백. 코드 롤백은 커밋 단위 revert.
