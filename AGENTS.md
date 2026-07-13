# Agent Entry Point — jamak-ouroboros

This repository uses the WHITEHAVEN Agent Harness (protocol: `project-initializing_260712.md`, schema 1.1 — see `docs/agent/HARNESS_MIGRATION.md`).

유튜브 강연 영상(허경영 강연)의 한국어 자막을 자동 생성 → LLM 교정 → 사람 검수 → 배포하며, 검수 결과가 다음 실행의 입력으로 되먹임되는(우로보로스) 파이프라인.

## Before modifying code

1. Read `docs/agent/CURRENT_STATE.md` — 현재 상태와 다음 작업.
2. Route via `docs/agent/PROJECT_MAP.md` — 수정 대상 경로 찾기.
3. Read related Accepted ADRs (`docs/agent/DECISION_INDEX.md`).
4. L2/L3 작업이면 `docs/agent/plans/ACTIVE_PLAN.md` 생성/갱신 후 구현.
5. 철학·불변 규칙은 `docs/agent/CONSTITUTION.md`. BLOCKING 규칙 목록·강제 등급은 `agent-harness.yaml` `blocking_rules`.

## Non-negotiables

- Inspect before asking; 저장소에서 확인 가능한 것은 묻지 않는다.
- Minimum necessary change; 요청 밖 리팩토링 금지.
- `data/jamak.db`, `data/seeds/`는 파괴적 조작 금지 (학습 데이터 원본). [BR-DATA-001]
- 학습 데이터(용어, 교정쌍)를 코드/프롬프트 파일에 하드코딩하지 않는다 — DB가 원본.
- 실행하지 않은 검증을 성공이라 말하지 않는다. 미검증은 `NOT VERIFIED`; 검증 주체 구분은 DoD의 Verification Capability Boundary.
- Accepted ADR을 조용히 덮어쓰지 않는다 — supersede 절차 사용. [BR-ADR-001]
- 검수 완료 자막이 생기면 반드시 피드백 흡수(diff → corrections/glossary) 실행. 건너뛴 세션은 미완성. [BR-FEEDBACK-001]
- 실제 비밀번호·API 키를 레포/문서/커밋에 쓰지 않는다 (공개 레포). [BR-SECRET-001]
- 작업 종료 시 `CURRENT_STATE.md` 갱신. [BR-DOCS-001 — Claude Code 훅이 기계 강제]

## Decision Write-Through (같은 턴 기록)

사용자가 설계·범위·제약·기술을 확정/정정/기각한 턴에는 **그 턴 안에서** 저장소에 기록한다:
아키텍처·계약 → ADR / 현재 작업 실행 결정 → ACTIVE_PLAN 또는 CURRENT_STATE / 미확정 → Open Decisions.
코드 변경이 없어도 기록한다. 기록 불가 환경이면 `UNPERSISTED DECISION`으로 응답에 명시하고 다음 턴 첫 작업으로 기록한다.

## Change Annotation (2026-07-13부터)

의미 있는 **동작 변경**(버그픽스로 동작 변화, 알고리즘/데이터 규칙 변경, 보안 처리, 의도적 trade-off, workaround)의 decision boundary에 표준 주석 1개를 남긴다:

```
# [WH-CHANGE v<semver> | FIX|FEAT|PERF|SEC | YYYY-MM-DD | CHG-YYYYMMDD-NNN]
# Reason: 왜 바꿨는가.
# Related: ADR-XXXX / CHANGELOG 항목.
```

CHG-ID는 `CHANGELOG_AGENT.md` 항목과 일치시킨다. formatter·rename·오타·자명한 변경은 대상 아님. 기존 코드 소급 적용 없음 (기존 자유 형식 why-주석 유효).

## Handoff 트리거 (Continuity Break)

다음이 예상되면 `docs/agent/handoffs/YYYY-MM-DD_HHMM_<topic>.md` 작성: substantial task 종료, 세션 종료 예상, 다른 에이전트/사람으로 전환, 컨텍스트 한계 접근, 장기 공백. 현재 상태가 저장소만으로 복원 가능하면 생략 가능.

## Harness 자가 점검

`uv run python scripts/agent-harness/verify_harness.py` — 필수 문서·매니페스트 경로·DECISION_INDEX 링크·BLOCKING 규칙 무결성 검사.
