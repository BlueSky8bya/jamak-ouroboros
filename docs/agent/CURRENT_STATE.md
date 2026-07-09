# Current State

Last Updated: 2026-07-10 (M4 완료 시점)
Project Version: 0.1.0
Harness Protocol: project-initializing_260710.md

## Current Objective

전체 루프(M0~M4) 완성됨. 다음: 실사용 — 용어 승인(/glossary-review), 실제 검수 1회전, CER 추이 관찰.

## Current Status

- M0 스캐폴드: 완료
- M1 코어 파이프라인 (ingest→STT→crosscheck→srt): **완료, 검증됨** (lFuxxOlgl5Y 9분, 104 세그먼트, 59 flagged)
- M2 LLM 교정 + seed-import: **완료, 검증됨**. 교정 28/104, uncertain 19. 오인식 수정 확인: 에스드→에스더, 수화성→수가성, 오물가→우물가, 허성정→허경영, 엑스테라→엑스트라, 모계사→모계사회. seed-import: 103개 강연 → 용어 후보 500개 (전부 미승인 — glossary-review 대기)
- M3 검수 웹앱: **완료, E2E 검증됨** (`jamak serve` → localhost:8710). 플레이어 동기화 리스트, 인라인 편집(blur 저장), Ctrl+Enter 저장+완료+다음, flagged/uncertain 하이라이트+W/Y 원문 비교, 타이밍 ±0.1s, 필터, srt 다운로드(세그먼트별 best), 피드백 흡수 버튼
- M4 피드백 루프 + eval: **완료, 검증됨**. absorb(diff→교정쌍, 멱등), eval(CER 추이). 테스트: 검수 시뮬레이션 → 교정쌍 1개 생성 → CER whisper 1.92% vs llm 0.55%

## Active Work

- 없음 (실사용 단계). API 키 세션 미반영 시:
  `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; <명령>`

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

1. `/glossary-review` — 용어 후보 500개 승인 (승인 전까지 whisper prompt는 기본값)
2. 실제 검수 1회전: `uv run jamak serve` → 웹에서 검수 → "피드백 흡수" → `uv run jamak eval`
3. 새 강연 영상으로 2회전 → CER 추이 확인 (우로보로스 실증)
4. 관찰 항목: LLM 자동자막 문맥 보충([1] "지혜로우니까"), 사투리 정규화(내한테→나한테) — 과교정 패턴이면 correct.py 프롬프트 조정
5. ISSUE-002 (긴 세그먼트 분할) — 검수 불편하면 착수

## Last Verified

- `uv run jamak run https://youtu.be/lFuxxOlgl5Y` 전체 파이프라인(교정 포함) → PASS — 2026-07-10
- 웹앱 E2E (목록→에디터→편집→저장→DB→export 반영) → PASS — 2026-07-10
- absorb/eval 루프 (diff→교정쌍→CER, 멱등성) → PASS — 2026-07-10
- 실 검수 데이터 기준 CER 추이: NOT VERIFIED (검수 데이터 아직 없음 — 시뮬레이션만)
