# Agent Change Log

## v0.2.0 — 2026-07-11~12 (배포 + 경로 B + 검수 도구)

세부 커밋은 git 이력 참조(메시지 상세). 아래는 테마별 통합 기록. 라이브 배포처 = https://hky-jamak.com (Railway, Singapore).

### CHG-20260711-001 — DEPLOY — 터널 방식 1차 배포 + 역할 인증 (ADR-0007)
Change: 로컬 `jamak serve`(127.0.0.1) 앞에 Cloudflare Tunnel(hky-jamak.com). 스타일된 인앱 로그인(크롬 팝업 아님) + 서명 세션 쿠키. 비번=역할(관리자/검수자), 이름은 표시용. 우상단 접속자 칩·계정변경. 네이티브 select→커스텀 Dropdown 전면. h1 "자막 검수 작업대 ♾️". 3축 진행 링.
Validation: 로그인 200/401, 커스텀 드롭다운 렌더, 라이브 URL 200.
Rollback: ADR-0007 + 관련 web 커밋 revert.

### CHG-20260712-001 — DEPLOY — 경로 B: 클라우드 웹앱 + 전용 Postgres (ADR-0008)
Change: 검수앱 Railway 상시 호스팅 + 전용 Postgres 단일 DB. `DATABASE_URL` 있으면 PG(psycopg), 없으면 기존 SQLite(로컬 100% 그대로). stt.json→`SttBlob`(DB, 워드맵/타이밍 클라우드 동작). `jamak migrate-to-cloud` 이관. Dockerfile(node빌드→python serve)·railway.json. DB 리전 Singapore 이전(앱·DB 동일 리전, 프록시 URL 불변). 앱 DATABASE_URL=internal(egress 0).
Validation: SQLite 무변화·URL 정규화·SttBlob·PK보존 이관·클라우드 쓰기왕복·리전 이전 후 데이터 온전(7 job/3722 seg).
Rollback: `DATABASE_URL` 미설정 = 로컬 SQLite 복귀.

### CHG-20260712-002 — FEAT — DB 요청 큐 + jamak worker (경로 B 영상 생성)
Change: 웹앱은 GPU 안 돌리고 `JobRequest`(DB)에 요청만 기록(관리자, 클라우드 포함). 로컬 `jamak worker`가 pending을 하나씩 처리→클라우드 DB. 워커 시작 시 stuck `processing`→`pending` 회수(Ctrl+C 복구). 파이프라인 heartbeat(음성인식%/자막정리/교정중)→`/api/queue` note+age→배너·카드 진행 표시, ⚠는 STT 정체만. `JAMAK_NO_PIPELINE` 폐기(can_ingest=is_admin). 취소 ✕(pending/error/stuck-processing).
Validation: 요청·dedup·순차·reclaim·취소 temp-DB, 클라우드 실검증(요청 pending→queued, heartbeat note).
Rollback: 관련 app.py/cli.py/App.tsx revert.

### CHG-20260712-003 — FEAT — 클라우드 DB 백업 자동화 (오프사이트)
Change: `jamak backup-cloud` — 클라우드 PG→로컬 gzip SQLite 스냅샷(pg_dump 불필요, --keep). 주간 Windows 태스크(`jamak-backup-cloud`)→구글드라이브(`JAMAK_BACKUP_DIR`). 워커 로그온 자동시작(시작프로그램). 텍스트뿐이라 스냅샷 수백KB~수십MB.
Validation: 스냅샷 복원 행수 일치(322KB), 드라이브 저장, 태스크 등록.
Rollback: 명령·태스크·시작프로그램 파일 제거.

### CHG-20260712-004 — FEAT — 검수 완료 .srt 카드 임포트 + 되돌리기 + 한국어 가드
Change: 카드에 .srt 드래그/📄버튼→시간겹침 정렬→ko `text_final`+reviewed→우로보로스 흡수. 적용 전 미리보기 모달(대상 영상·매칭 N/총·낮으면 경고·취소). 적용 전 `SrtBackup` 스냅샷→카드 `↩ .srt 취소`로 정확 복원. 한글:영문 비율로 비한국어 거부. 비-srt 거부.
Validation: 정렬·미리보기·적용·undo·언어감지 temp-DB, 실브라우저 드롭→모달→취소.
Rollback: import-srt/undo-srt/SrtBackup 관련 revert.

### CHG-20260712-005 — FEAT — 영상별 담당 검수자 (담당자)
Change: `Job.assignee`(+마이그레이션). 카드 `👤 담당` 배지→스타일 모달(내 이름 프리필·해제·취소·지정, 크롬 prompt 아님). 누구나 클레임/재지정(비번+자유이름 모델). `POST /api/jobs/{id}/assignee`, list_jobs 노출.
Validation: set/list/clear temp-DB + 클라우드 왕복(정리), 칩 렌더·모달.
Rollback: assignee 관련 revert.

### CHG-20260712-006 — FIX/UX — 웹 폴리시 배치
Change: 드롭다운 body portal(카드 transform/overflow 탈출). no-cache index.html(재배포 즉시 반영). 배포버전 배지(`/api/version`, RAILWAY_GIT_COMMIT_SHA). 리스트 썸네일 16:9 무크롭·무빈공간(고정행+auto열). 그리드 footer 버튼 무클리핑(meta 한줄+칩 다음줄) + footer 하단고정(완료카드 빈공간↓). 모달 텍스트드래그-닫힘 버그(onMouseDown target). 진행칩 패딩(전역 .progress 충돌 네임스페이스). 번역 무-API키 500→깔끔 안내. 처리중 숫자→펄스점.
Validation: 각 항목 실브라우저 측정(portal/ratio/clip/footer/modal drag/ %).
Rollback: 해당 web 커밋 revert.

## v0.1.0 — 2026-07-10

### CHG-20260710-007 — FEAT — 현재 영상 피드백 전파

Problem: 피드백 흡수가 다음 영상부터만 체감되면 같은 영상 안에서 반복 오인식을 계속 손으로 고쳐야 함.
Change: `absorb_job`이 검수 완료 세그먼트에서 배운 교정쌍을 해당 위치 이후의 미검수 세그먼트에 즉시 무API 치환으로 반영. 학습 버튼은 저장 완료를 기다린 뒤 흡수하고 세그먼트를 재조회. export 자동 흡수는 흡수 후 세그먼트를 다시 읽어 다운로드 파일에도 반영.
Validation: 임시 SQLite 스팟체크 PASS(검수 지점 이전 미검수는 유지, 이후 미검수 1개 반영), `python -m compileall src/jamak` PASS, `npm.cmd run build` PASS. `uv run jamak doctor`는 ffmpeg PATH 누락으로 PARTIAL(GPU/ctranslate2/API key/DB OK).
Rollback: `src/jamak/feedback.py`, `src/jamak/web/app.py`, `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/api.ts`, `src/jamak/cli.py` revert.

### CHG-20260710-008 — FEAT — 검수 타이밍 UX 보강

Problem: 잘못 나뉜 자막, 중복 문장, 애매한 경계 때문에 편집 중인 줄과 영상 위치가 헷갈리고 시간 조절 피로가 큼.
Change: 재생 자막/편집 자막 상태 패널과 미니 타임라인 추가. 각 행에 현재 재생 위치 rail 추가. 현재 시간으로 시작/끝/다음 경계 맞춤, 현재+다음 자막 시간 재분배 버튼 추가. `merge-next`는 접두/접미 중복을 자동 제거.
Validation: 임시 SQLite merge/boundary/redistribute 스팟체크 PASS, `python -m compileall src/jamak` PASS, `npm.cmd run build` PASS, HTTP smoke PASS. Browser visual check NOT VERIFIED(node_repl runtime sandbox error).
Rollback: `src/jamak/web/app.py`, `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/api.ts`, `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-009 — UX — 연결형 타이밍 버튼

Problem: `시작/끝/경계/나눔`은 개념이 겹치고, `끝`만 누르면 다음 자막 시작이 따라오지 않아 다시 수동 보정해야 함.
Change: 행 버튼을 `여기서 시작`/`여기서 넘김`으로 축소. `여기서 시작`은 이전 끝+현재 시작을 같은 시간으로 조정, `여기서 넘김`은 현재 끝+다음 시작을 같은 시간으로 조정. 수동 start/end 입력도 겹침이 생기면 이전/다음 자막을 최소 조정.
Validation: 임시 SQLite prev/next boundary + manual overlap 스팟체크 PASS, `python -m compileall src/jamak` PASS, `npm.cmd run build` PASS, HTTP smoke PASS.
Rollback: `src/jamak/web/app.py`, `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/api.ts`, `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-010 — UX — 즉시 삭제와 세그먼트 Undo

Problem: 자막 삭제 확인창이 검수 흐름을 끊고, 빠른 정리 작업을 방해함.
Change: 삭제 확인창 제거. split/merge/delete/timing 조작 직전 세그먼트 스냅샷을 Undo 스택에 저장하고, `Ctrl+Z` 또는 왼쪽 패널 `되돌리기`로 마지막 세그먼트 조작을 DB까지 복원. 텍스트 입력 중 `Ctrl+Z`는 기본 텍스트 Undo 유지. 왼쪽 작업 패널/상태 표시 polish.
Validation: 임시 SQLite delete→restore 스팟체크 PASS, FastAPI TestClient restore route PASS, `python -m compileall src/jamak` PASS, `npm.cmd run build` PASS. `uv run jamak doctor`는 ffmpeg PATH 누락으로 PARTIAL(GPU/ctranslate2/API key/DB OK).
Rollback: `src/jamak/web/app.py`, `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/api.ts`, `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-011 — UX — Continue Workflow And Delete Shortcut

Problem: The `먼저 볼 곳` / `안 본 곳` filters made the reviewer choose a view before continuing, and there was no fast keyboard path for deleting the currently selected subtitle cell.
Change: Removed the review filters, added a single `이어서 작업하기` button that flushes pending edits and jumps to the next unreviewed subtitle from the focused/current position, changed Enter-confirm navigation to use the same next-work target, and added a `Delete` shortcut that immediately deletes the focused/current subtitle only when the user is not typing in a text field. Delete reuses the existing segment undo stack, so `Ctrl+Z` restores it.
Validation: `python -m compileall src/jamak` PASS, frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only). Browser visual check NOT VERIFIED because the in-app browser/node runtime failed with a Windows sandbox setup error.
Rollback: `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/styles.css`, `src/jamak/web/frontend/src/types.ts` revert.

### CHG-20260710-012 — UX — Text Undo And Cell Undo Shortcut Split

Problem: While editing subtitle text, `Delete` correctly deletes characters and `Ctrl+Z` correctly undoes text edits, but that left no keyboard-only way to delete or undo the current subtitle cell without clicking outside the textarea.
Change: Added dedicated cell-level shortcuts that work while editing: `Alt+Delete` deletes the focused/current subtitle cell, `Alt+Z` runs segment/cell undo, and `Ctrl+Esc` is accepted as a delete fallback when the browser receives it. Kept native text editing behavior untouched: `Delete` deletes text in the textarea, and `Ctrl+Z` remains text undo while typing.
Validation: `npm.cmd run build` PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS (`http://127.0.0.1:8710` returned 200).
Rollback: `src/jamak/web/frontend/src/Editor.tsx` revert.

### CHG-20260710-013 — UX — Review App Visual Redesign

Problem: Shortcut help was a hard-to-scan flat table, and the app still looked like a prototype rather than a polished long-session subtitle editing tool.
Change: Replaced the shortcut table with grouped shortcut cards, refreshed the landing page into a work dashboard with summary chips and job progress bars, and rewrote the editor CSS around a calmer neutral surface system, clearer primary/secondary buttons, stronger active/focused subtitle states, cleaner side-panel controls, and responsive layout rules.
Validation: `npm.cmd run build` PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS and served the new built assets (`index-Ck2xiCJK.js`, `index-DXzJDlpH.css`). Browser visual check NOT VERIFIED because the in-app browser/node runtime still fails with a Windows sandbox setup error.
Rollback: `src/jamak/web/frontend/src/App.tsx`, `src/jamak/web/frontend/src/Editor.tsx`, `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-014 — UX — Eye Comfort Color Tuning

Problem: Even after the visual redesign, too many large surfaces were effectively pure white, which made the review workspace feel bright and tiring during long subtitle sessions.
Change: Shifted the global palette to low-saturation blue-gray: darker app background, tinted panels/cards/inputs, softer shortcut and reviewed-row surfaces, and fewer direct white fills while keeping primary actions and status colors readable.
Validation: `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS and served the new built assets (`index-DcHoUJtu.js`, `index-Cj0Kab1c.css`).
Rollback: `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-015 — UX — Copy Wrapping Cleanup

Problem: The landing description was right-aligned, so wrapped Korean text looked like an awkward hanging indent. Similar helper text could also wrap too aggressively.
Change: Left-aligned the landing description, moved the header to a single-column flow, widened the copy measure, and applied `text-wrap: pretty` plus Korean `word-break: keep-all` to helper/copy surfaces including job titles, hints, shortcut details, and source text.
Validation: `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root served the new built assets (`index-DXZuCohL.js`, `index-BuhVC8YR.css`).
Rollback: `src/jamak/web/frontend/src/styles.css` revert.

### CHG-20260710-016 — PIPELINE — Standalone Audience Response Filter

Problem: Lecture audience replies can appear as standalone subtitle cells, especially `네`, creating review noise that should not be part of the lecturer subtitle draft.
Change: Added `pipeline/noise.py` with a conservative deterministic filter for short standalone audience responses (`네`, `네네`, `예`, `예예`, `넵`) and applied it immediately after STT splitting, before crosscheck and DB segment creation. Full sentences containing the same words are preserved.
Validation: Local Python smoke checks PASS for standalone/remain cases, segment-list filter smoke PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only). `uv run` smoke NOT VERIFIED because the user-home uv cache path failed to initialize; direct `PYTHONPATH=src` smoke checks were used instead.
Rollback: `src/jamak/pipeline/noise.py` delete and `src/jamak/cli.py` filter call revert.

### CHG-20260710-017 — FIX — Pronoun-Safe Feedback Propagation

Problem: The feedback loop could learn contextual rewrites such as `그 여자`/`그 사람` -> a proper name and then propagate them into later subtitles, even though subtitles should preserve pronouns when that is what was spoken.
Change: Added a shared learned-pair safety guard for Korean pronoun/demonstrative references. Unsafe pairs are now skipped during extraction, same-video propagation, global pre-pass, and LLM few-shot prompt construction. The correction prompt now explicitly says not to expand pronouns into proper names, and `PROMPT_VERSION` was bumped to `v3` so old prompt-influenced correction cache entries are not reused. Added a repair pass for prior unsafe reference propagation on unreviewed machine suggestions only; current visible unreviewed residue for `lFuxxOlgl5Y` was cleared.
Validation: Learned-pair guard smoke PASS, feedback extraction/propagation smoke PASS, pre-pass/prompt smoke PASS, reviewed bad-LLM pair extraction blocked PASS, current DB residue query found 0 visible unreviewed matches after repair, `.venv\Scripts\python.exe -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only).
Rollback: `src/jamak/learned_pairs.py` delete; revert changes in `src/jamak/feedback.py`, `src/jamak/glossary.py`, and `src/jamak/pipeline/correct.py`.

### CHG-20260710-018 — UX — Spacebar-Safe Playback Shortcuts

Problem: Spacebar could still toggle the YouTube player while the reviewer expected it to type a normal space, making text editing feel unpredictable.
Change: Made playback toggle Tab-only in the app shortcut layer, removed the `Ctrl+Space` current-subtitle replay shortcut from both handler and shortcut help, changed the help text to mark Space as typing-only, and set YouTube `playerVars.disablekb=1` so the embedded player does not consume Space as play/pause when focused.
Validation: Frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only). Browser visual/interaction check NOT VERIFIED.
Rollback: Revert `src/jamak/web/frontend/src/Editor.tsx` and `src/jamak/web/frontend/src/usePlayer.ts`.

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
