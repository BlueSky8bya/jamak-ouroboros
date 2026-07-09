# Current State

Last Updated: 2026-07-10
Project Version: 0.1.0
Harness Protocol: project-initializing_260710.md

## Current Objective

M2 검증 (LLM 교정이 실제 오인식을 고치는지) → M3 검수 웹앱 → M4 우로보로스 피드백 루프 완성.

## Current Status

- M0 스캐폴드: 완료
- M1 코어 파이프라인 (ingest→STT→crosscheck→srt): **완료, 검증됨** (lFuxxOlgl5Y 9분 영상, 104 세그먼트, 59 flagged, draft.srt 생성)
- M2 LLM 교정 + seed-import: 코드 완료. seed-import 실행됨 (103개 강연 → 용어 후보 500개, 전부 미승인). **교정 단계 NOT VERIFIED** — API 키 세션 미반영으로 미실행
- M3 검수 웹앱: 미착수
- M4 피드백 루프 + eval: 미착수 (evaluate.py 미작성)

## Active Work

- LLM 교정 첫 실행 (테스트 영상 lFuxxOlgl5Y 재실행 — STT 캐시 재사용됨)
- API 키: User 레지스트리에 존재하나 실행 중 세션 env에 없음 → 명령별 레지스트리 주입으로 해결 가능:
  `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; uv run jamak run <url>`

## Known Issues

### ISSUE-001 — 검수 코퍼스가 GitHub에 push됨

Status: Open (사용자 결정 대기)
Evidence: commit 74b9cc0에 `data/seeds/기존 검수 완료본.txt` (2.6MB) 포함, origin에 push됨.
Impact: 레포가 public이면 강연 전사 코퍼스 공개 상태.
Options: (a) 유지 (b) 히스토리 rewrite + .gitignore에 data/seeds/ 추가.

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

1. 레지스트리 주입 방식으로 `uv run jamak run "https://youtu.be/lFuxxOlgl5Y"` 재실행 (STT 캐시 재사용, 교정만 신규)
2. draft.srt에서 알려진 오인식(에스드→에스더, 수화성→수가성, 오물가→우물가) 교정 여부 육안 확인
3. `/glossary-review`로 용어 후보 500개 중 진짜 어휘 승인
4. M3 검수 웹앱 착수 (ACTIVE_PLAN 작성 후)

## Last Verified

- command: `uv run jamak doctor` → PASS (GPU/ffmpeg/CUDA/DB OK, API키만 WARN) — 2026-07-10
- command: `uv run jamak run https://youtu.be/lFuxxOlgl5Y` (교정 스킵) → PASS — 2026-07-10
- LLM 교정: NOT VERIFIED
