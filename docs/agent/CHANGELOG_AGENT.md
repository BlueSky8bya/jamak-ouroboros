# Agent Change Log

## v0.1.0 — 2026-07-10

### CHG-20260710-001 — FEAT — 초기 스캐폴드 (commit 061638c)

Change: 파이프라인 5단계, SQLite 저장소, CLI, 스킬 4개, CLAUDE.md 생성.
Validation: `uv run jamak doctor` → PASS.
Rollback: git revert 061638c.

### CHG-20260710-002 — FIX — Windows CUDA DLL 로딩 (commit 74b9cc0)

Problem: `RuntimeError: Library cublas64_12.dll is not found` — pip 설치 NVIDIA DLL이 PATH에 없음.
Root Cause: ctranslate2는 `os.add_dll_directory` 검색 목록이 아니라 PATH로 CUDA DLL을 찾음.
Change: `stt.py _register_cuda_dlls()` — venv `nvidia/*/bin`을 add_dll_directory + PATH 양쪽에 등록.
Validation: DLL ctypes 로드 테스트 PASS → 전체 파이프라인 실행 PASS (104 세그먼트).
Rollback: 함수 제거 시 GPU STT 불가 (제거 금지 — Locked Area).

### CHG-20260710-003 — FEAT — .txt 시드 임포트 (commit 74b9cc0)

Change: `seed.py` — 타임코드 강연 전사 .txt 포맷 파싱 ([날짜] 헤더, MM:SS 타임코드 제거), 후보 500개 캡.
Validation: 실제 코퍼스(103개 강연) 임포트 → 500 후보 생성 PASS.
Rollback: glossary 테이블에서 `category='자동추출'` 삭제.

### CHG-20260710-004 — FIX — cp949 콘솔 크래시 (commit 74b9cc0)

Problem: rich 출력의 em-dash가 cp949 콘솔에서 UnicodeEncodeError.
Change: CLI 문자열의 em-dash를 ASCII hyphen으로 교체.
Validation: `jamak doctor` 재실행 PASS.

### CHG-20260710-006 — FEAT — 세그먼트 분할 + 다국어 번역 export + 자동 흡수 (commit 54eddff)

Change: split.py(자막 크기 분할), translate.py(10개 언어, 세그먼트+해시 캐시), export 파일명 `제목_자막_<lang>.srt`, export 시 absorb 자동 실행, config 레지스트리 API키 폴백.
Validation: 104→168 분할 확인, en 번역 export PASS(에스더→Esther), 캐시 재요청 2.1s, 파일명 헤더 UTF-8 PASS.
Rollback: commit 54eddff revert. Translation 테이블은 삭제해도 원문 무손실.

### CHG-20260710-005 — DOCS — WHITEHAVEN Agent Harness 도입 (MODE C)

Change: agent-harness.yaml, AGENTS.md, docs/agent/* 생성. CLAUDE.md를 adapter로 축소. 기존 CLAUDE.md 내용은 CONSTITUTION/PROJECT_MAP으로 재배치.
Validation: 문서 내 링크 경로 존재 확인.
Rollback: docs/agent/, AGENTS.md, agent-harness.yaml 삭제 + CLAUDE.md git revert.
