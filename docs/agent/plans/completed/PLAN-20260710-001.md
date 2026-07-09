# Active ExecPlan

Plan ID: PLAN-20260710-001
Status: In Progress
Task Risk: L2
Created: 2026-07-10
Updated: 2026-07-10

## Objective

M2 검증(LLM 교정 실효성 확인) 후 M3 검수 웹앱 구축 → 사람 검수가 가능한 상태.

## Verifiable End State

1. 테스트 영상의 알려진 오인식(에스드→에스더, 수화성→수가성, 오물가→우물가)이 LLM 교정으로 수정된 draft.srt 존재.
2. 로컬 웹앱에서: 유튜브 플레이어 + 세그먼트 리스트 동기화, 인라인 편집, 저장 시 text_final 기록, .srt 다운로드.

## Scope

- correct 단계 첫 실행 + 결과 스팟체크
- `src/jamak/web/` FastAPI 백엔드 + 프론트 (단일 사용자 로컬)
- flagged/uncertain 하이라이트

## Out of Scope

- 피드백 diff 자동 흡수 (M4 별도 plan)
- 파인튜닝, 하드섭, 배포

## Milestones

### M2-V — LLM 교정 검증

Files: (실행만, 코드 변경 없음 예상)
Validation: 레지스트리 키 주입 후 `jamak run` 재실행 → draft.srt 교정본 육안 비교
Status: In Progress

### M3-A — 웹앱 백엔드

Files: `src/jamak/web/app.py` (FastAPI: job 목록, 세그먼트 CRUD, srt 다운로드), cli에 `serve` 명령
Validation: API로 세그먼트 조회/수정 → DB 반영 확인
Status: Pending

### M3-B — 검수 UI

Files: `src/jamak/web/frontend/` (플레이어 동기화, 편집, 하이라이트, 단축키)
Validation: preview 도구 E2E (클릭 시크/편집/저장/다운로드)
Status: Pending

## Rollback Strategy

각 milestone 별도 커밋. 웹앱은 신규 경로라 revert 안전.

## Progress Log

### 2026-07-10

- M1 검증 완료 (104 세그먼트 draft). M2 교정 미실행 (API 키 세션 이슈 → 레지스트리 주입 방식 확보).
