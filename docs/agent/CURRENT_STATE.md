# Current State

Last Updated: 2026-07-10
Project Version: 0.1.0
Harness Protocol: project-initializing_260710.md

## Current Objective

M2 검증 (LLM 교정이 실제 오인식을 고치는지) → M3 검수 웹앱 → M4 우로보로스 피드백 루프 완성.

## Current Status

- M0 스캐폴드: 완료
- M1 코어 파이프라인 (ingest→STT→crosscheck→srt): **완료, 검증됨** (lFuxxOlgl5Y 9분 영상, 104 세그먼트, 59 flagged, draft.srt 생성)
- M2 LLM 교정 + seed-import: **완료, 검증됨** (2026-07-10). 교정 28/104 세그먼트, uncertain 19. 알려진 오인식 전부 수정 확인: 에스드→에스더, 수화성→수가성, 오물가→우물가, 허성정→허경영, 엑스테라→엑스트라, 모계사→모계사회. seed-import: 103개 강연 → 용어 후보 500개 (전부 미승인 — glossary-review 대기)
- M3 검수 웹앱: 미착수
- M4 피드백 루프 + eval: 미착수 (evaluate.py 미작성)

## Active Work

- M3 검수 웹앱 (ACTIVE_PLAN M3-A부터)
- API 키: 세션 env에 없으면 명령별 레지스트리 주입:
  `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; uv run jamak run <url>`

## Known Issues

### ISSUE-001 — 검수 코퍼스가 GitHub에 push됨

Status: Resolved 2026-07-10 — 사용자 결정: 공개 유지. 조치 불필요.

### ISSUE-002 — 긴 세그먼트 미분할

Status: Open
Evidence: draft.srt에 24~27초 세그먼트 존재. 자막 규칙(표시시간)에 어긋남.
Affected: `pipeline/assemble.py` (또는 stt 세그먼트 분할 로직).
Hypothesis: whisper 세그먼트를 그대로 사용 — 문장/시간 기준 분할 단계 필요. M3 전후 처리 권장.

### ISSUE-003 — 콘솔 인코딩

Status: Mitigated
cp949 콘솔에서 유니코드 특수문자 크래시 → CLI 문자열에서 em-dash 제거로 해결. 새 콘솔 출력 추가 시 주의. `PYTHONIOENCODING=utf-8` 병용.

## Locked / Stable Areas

- `data/jamak.db`, `data/seeds/` — 파괴적 조작 금지
- `pipeline/stt.py`의 `_register_cuda_dlls` — Windows CUDA 동작의 전제. 제거 금지

## Open Decisions

- 테스트 스위트 도입 여부/범위 (현재 없음. wrap_korean, crosscheck, seed 파서가 단위테스트 후보)
- 폴더 rename: `C:\Projects\asdf` → `jamak-ouroboros` (세션 잠금으로 보류 중, 코드는 경로 독립적)
- ISSUE-001 seeds 공개 여부

## Next Exact Steps

1. M3-A 웹앱 백엔드 (`src/jamak/web/app.py` + `jamak serve` 명령)
2. M3-B 검수 UI (플레이어 동기화, 인라인 편집, flagged/uncertain 하이라이트)
3. `/glossary-review`로 용어 후보 500개 승인 (언제든 병행 가능)
4. 관찰 항목: LLM이 자동자막에서 문맥 보충하는 케이스([1] "지혜로우니까" 추가), 사투리 정규화(내한테→나한테) — 검수 UI에서 사람이 판단, 과교정 패턴이면 correct.py 프롬프트 조정

## Last Verified

- `uv run jamak doctor` → PASS — 2026-07-10
- `uv run jamak run https://youtu.be/lFuxxOlgl5Y` 전체 파이프라인(교정 포함) → PASS — 2026-07-10
- 교정 스팟체크: 알려진 오인식 6종 수정 확인 → PASS — 2026-07-10
