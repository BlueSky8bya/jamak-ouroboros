# Agent Entry Point — jamak-ouroboros

This repository uses the WHITEHAVEN Agent Harness (protocol: `project-initializing_260710.md`).

유튜브 강연 영상(허경영 강연)의 한국어 자막을 자동 생성 → LLM 교정 → 사람 검수 → 배포하며, 검수 결과가 다음 실행의 입력으로 되먹임되는(우로보로스) 파이프라인.

## Before modifying code

1. Read `docs/agent/CURRENT_STATE.md` — 현재 상태와 다음 작업.
2. Route via `docs/agent/PROJECT_MAP.md` — 수정 대상 경로 찾기.
3. Read related Accepted ADRs (`docs/agent/DECISION_INDEX.md`).
4. L2/L3 작업이면 `docs/agent/plans/ACTIVE_PLAN.md` 생성/갱신 후 구현.
5. 철학·불변 규칙은 `docs/agent/CONSTITUTION.md`.

## Non-negotiables

- Inspect before asking; 저장소에서 확인 가능한 것은 묻지 않는다.
- Minimum necessary change; 요청 밖 리팩토링 금지.
- `data/jamak.db`, `data/seeds/`는 파괴적 조작 금지 (학습 데이터 원본).
- 학습 데이터(용어, 교정쌍)를 코드/프롬프트 파일에 하드코딩하지 않는다 — DB가 원본.
- 실행하지 않은 검증을 성공이라 말하지 않는다. 미검증은 `NOT VERIFIED`.
- Accepted ADR을 조용히 덮어쓰지 않는다 — supersede 절차 사용.
- 검수 완료 자막이 생기면 반드시 피드백 흡수(diff → corrections/glossary) 실행. 건너뛴 세션은 미완성.
- 작업 종료 시 `CURRENT_STATE.md` 갱신; substantial task 종료 시 Handoff 작성.
