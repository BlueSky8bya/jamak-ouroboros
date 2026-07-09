# Current State

Last Updated: 2026-07-10 (fatigue-reduction batch: PLAN-20260710-010)
Project Version: 0.1.0
Harness Protocol: project-initializing_260710.md

## Current Objective

전체 루프(M0~M4) 완성 + 검수/번역 피로 최소화 보강. 다음: 실제 다회차 검수로 CER 추이, 번역 검수 체감 확인.

## PLAN-20260710-010 (6개 요청, 전부 done+verified)

- M-A 재생 단축키 복구: ▶재생/⏸멈춤 + ⟲3초 버튼(플레이어 밑), Space=재생/정지(입력칸 밖), Tab 유지. 토스트 자동 사라짐(4/8/6s). 파일명 `{lang}_제목_자막.srt`.
- M-B STT 프롬프트 환각 대응: `noise.is_prompt_echo` + crosscheck에서 유튜브 자막으로 대체/삭제, stt `hallucination_silence_threshold=2.0`. (현재 캐시엔 누출 없어 합성 검증)
- M-C 타임라인 드래그 미세조정: TimingStrip 경계 핸들 드래그 → linked boundary(undo 가능). dragRef로 fast-drag 안전.
- M-D 번역 검수 워크플로: 한국어 100% 검수 전 언어 잠금, 번역 생성→세그먼트별 수정/확인, edited/reviewed 보호(재번역 무시), export 반영. db 마이그레이션(translation.reviewed/edited).
- 로컬 번역 모델(요청 3): 미구현 — 답변만. NLLB-200/m2m100(CTranslate2) 또는 Ollama 가능하나 종교/강연 문맥 품질 열세. 저비용 대안 `JAMAK_TRANSLATE_MODEL=claude-haiku-4-5`. Open Decision.

## Current Status

- M4.5 continue workflow UX: **done, build verified**. Removed the flagged/unreviewed filter buttons from the review editor, added a single `이어서 작업하기` button that jumps to the next unreviewed subtitle from the current/focused position, changed Enter-confirm navigation to the same next-work target, and added a `Delete` shortcut for deleting the selected/current subtitle outside text inputs. Delete still feeds the segment-level undo stack.
- M4.6 shortcut split UX: **done, build verified**. Text editing keeps native `Delete` and `Ctrl+Z`; cell operations now have dedicated keyboard paths: `Alt+Delete` deletes the focused/current subtitle even while editing, `Alt+Z` runs segment/cell undo even while editing, and `Ctrl+Esc` is accepted as a delete fallback when the browser receives it.
- M4.7 review app visual redesign: **done, build verified**. Reworked shortcut help into grouped cards, redesigned the landing dashboard/job cards/progress bars, and overhauled the editor visual system with calmer surfaces, clearer buttons, stronger focused/active row states, cleaner side controls, and responsive layout rules.
- M4.8 eye comfort color tuning: **done, build verified**. Reduced large pure-white surfaces by shifting the app background, panels, cards, inputs, shortcut help, and reviewed rows to low-saturation blue-gray surfaces with stronger surface separation.
- M4.9 copy wrapping cleanup: **done, build verified**. Removed the right-aligned landing description that created awkward hanging lines, and applied prettier Korean wrapping to helper/copy surfaces such as job titles, hints, shortcut details, and source text.
- M4.10 standalone audience response filter: **done, smoke verified**. New runs now remove short standalone audience-response subtitles such as `네`, `네네`, `예`, `예예`, and `넵` immediately after STT splitting and before crosscheck/DB persistence, while preserving full sentences such as `네 맞습니다`.
- M4.11 pronoun-safe feedback propagation: **done, smoke verified**. Feedback learning now blocks contextual pronoun/demonstrative rewrites such as `그 여자`/`그 사람` -> proper name from extraction, same-video propagation, global pre-pass, and LLM few-shot prompts. Existing unsafe DB rows remain as historical data but are ignored; current unreviewed over-propagation for `lFuxxOlgl5Y` was repaired where it affected machine suggestions.
- M4.12 spacebar-safe playback shortcuts: **done, build verified**. Playback toggle is now Tab-only in the app shortcut layer, the Space-based current-subtitle replay shortcut was removed, shortcut help now states that Space is for typing, and the embedded YouTube player has keyboard controls disabled (`disablekb=1`) to prevent Space from toggling playback while editing.

- M0 스캐폴드: 완료
- M1 코어 파이프라인 (ingest→STT→crosscheck→srt): **완료, 검증됨** (lFuxxOlgl5Y 9분, 104 세그먼트, 59 flagged)
- M2 LLM 교정 + seed-import: **완료, 검증됨**. 교정 28/104, uncertain 19. 오인식 수정 확인: 에스드→에스더, 수화성→수가성, 오물가→우물가, 허성정→허경영, 엑스테라→엑스트라, 모계사→모계사회. seed-import: 103개 강연 → 용어 후보 500개 (전부 미승인 — glossary-review 대기)
- M3 검수 웹앱: **완료, E2E 검증됨** (`jamak serve` → localhost:8710). 플레이어 동기화 리스트, 인라인 편집(blur 저장), Ctrl+Enter 저장+완료+다음, flagged/uncertain 하이라이트+W/Y 원문 비교, 타이밍 ±0.1s, 필터, srt 다운로드(세그먼트별 best), 피드백 흡수 버튼
- M4 피드백 루프 + eval: **완료, 검증됨**. absorb(diff→교정쌍, 멱등), eval(CER 추이). 테스트: 검수 시뮬레이션 → 교정쌍 1개 생성 → CER whisper 1.92% vs llm 0.55%
- M4.1 현재 영상 피드백 전파: **완료, 스팟 검증됨**. 검수 완료 세그먼트에서 배운 교정쌍을 해당 위치 이후의 미검수 세그먼트에 결정적 치환으로 반영(Claude API 0원). 학습 버튼은 저장 완료를 기다린 뒤 흡수하고 세그먼트 목록을 재조회.
- M4.2 검수 타이밍 UX: **완료, 스팟 검증됨**. 재생 중 자막과 편집 중 자막을 분리 표시, 미니 타임라인/행 내부 재생 위치 표시, 중복 제거 합치기 추가(전부 무API).
- M4.3 연결형 타이밍 버튼: **완료, 스팟 검증됨**. `시작/끝/경계/나눔` 4버튼을 `여기서 시작`/`여기서 넘김`으로 축소. 시작은 이전 자막 끝+현재 시작을 함께 조정, 넘김은 현재 끝+다음 시작을 함께 조정. 수동 시간 입력도 겹침 발생 시 이웃 자막을 최소 조정.
- M4.4 즉시 삭제 + Undo: **완료, 스팟 검증됨**. 삭제 확인창 제거, split/merge/delete/timing 조작 직전 세그먼트 스냅샷 저장, `Ctrl+Z`/버튼으로 마지막 세그먼트 조작 복구. 텍스트 입력 중 `Ctrl+Z`는 브라우저 기본 텍스트 Undo 유지.

## Active Work

- 없음 (실사용 단계). API 키 세션 미반영 시:
  `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; <명령>`

## Known Issues

### ISSUE-001 — 검수 코퍼스가 GitHub에 push됨

Status: Resolved 2026-07-10 — 사용자 결정: 공개 유지. 조치 불필요.

### ISSUE-002 — 긴 세그먼트 미분할

Status: Resolved 2026-07-10 — `pipeline/split.py` (단어 타임스탬프 기반, 문장 경계 우선, 36자/7초 상한). 104 → 168 세그먼트 확인.

### ISSUE-004 — 분할 후 flagged 비율 상승

Status: Open (관찰)
Evidence: 분할 전 59/104(57%) → 분할 후 117/168(70%). 세그먼트가 짧아지며 자동자막 시간창 겹침 비교가 노이지해진 것으로 추정.
Affected: `pipeline/crosscheck.py` FLAG_THRESHOLD 또는 비교 창 로직.
Impact: 검수 우선순위 신호 희석. 검수 체감 나쁘면 조정.

### ISSUE-003 — 콘솔 인코딩

Status: Mitigated
cp949 콘솔에서 유니코드 특수문자 크래시 → CLI 문자열에서 em-dash 제거로 해결. 새 콘솔 출력 추가 시 주의. `PYTHONIOENCODING=utf-8` 병용.

## Locked / Stable Areas

- `data/jamak.db`, `data/seeds/` — 파괴적 조작 금지
- `pipeline/stt.py`의 `_register_cuda_dlls` — Windows CUDA 동작의 전제. 제거 금지

## Open Decisions

- 테스트 스위트 도입 여부/범위 (현재 없음. wrap_korean, crosscheck, seed 파서가 단위테스트 후보)
- 폴더 rename: `C:\Projects\asdf` → `C:\Projects\jamak-ouroboros` 시도했으나 Windows 프로세스 잠금으로 실패. Codex/터미널이 폴더를 놓은 뒤 parent에서 rename 필요. 코드는 경로 독립적.

## Next Exact Steps

1. `/glossary-review` — 용어 후보 500개 승인 (승인 전까지 whisper prompt는 기본값)
2. 실제 검수 1회전: `uv run jamak serve` → 웹에서 검수 → "피드백 흡수" → `uv run jamak eval`
3. 새 강연 영상으로 2회전 → CER 추이 확인 (우로보로스 실증)
4. 관찰 항목: LLM 자동자막 문맥 보충([1] "지혜로우니까"), 사투리 정규화(내한테→나한테) — 과교정 패턴이면 correct.py 프롬프트 조정
5. ISSUE-002 (긴 세그먼트 분할) — 검수 불편하면 착수

## Recent Additions (2026-07-10 후반)

- **비용 구조 개편** (commit cee717a): thinking off(출력 3.6k tok, $0.074/영상), 교정 캐시(재실행 $0), pre-pass(count≥2 교정쌍 무료 치환 — 피드백 쌓일수록 API 의존 감소), id 기반 매핑(동시 편집 안전), 삭제 확인창, 단계별 모델 env, 토큰/비용 리포트 출력
- 남은 비용 레버 (미적용): Batch API(-50%, 비동기 1h), JAMAK_CORRECT_MODEL=claude-haiku-4-5(-66%, 품질 검증 필요), M5 whisper 파인튜닝(교정 API 자체 제거)

- 랜딩 페이지: URL 붙여넣기 → 웹에서 파이프라인 실행 (백그라운드 subprocess + 상태 폴링). 같은 영상 재제출은 409 (검수 데이터 보호)
- 세그먼트 구조 편집: 커서 위치 분할(시간 비율 배분) / 병합 / 삭제 — E2E PASS
- 타이밍 보조: 현재 재생 시간으로 `여기서 시작`/`여기서 넘김`, 이웃 자막 자동 연동, 합치기 중복 제거
- 즉시 삭제 + Undo: 삭제 확인창 제거, 왼쪽 패널 되돌리기 버튼/상태 표시, `Ctrl+Z` 세그먼트 복구
- 다운로드 파일명 대소문자 파싱 버그 수정 (`제목_자막_<lang>.srt` 정상)
- 피드백 흡수 버튼: 저장 레이스 제거, 현재 영상 뒤쪽 미검수 자막 즉시 갱신, export 자동 흡수 결과가 다운로드 파일에 포함되도록 순서 조정
- **웹에서 새 URL 최초 제출 → 파이프라인 완주: NOT VERIFIED** (기존 영상 409 경로만 검증. 첫 실사용 시 확인 필요)

## Last Verified

- Spacebar-safe playback shortcuts: frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only). Browser visual/interaction check NOT VERIFIED.
- Pronoun-safe feedback propagation: learned-pair guard smoke PASS, feedback extraction/propagation smoke PASS (`그 여자` -> proper name skipped, `수로보관` -> `수로보가네` preserved), pre-pass/prompt smoke PASS, reviewed bad-LLM pair extraction blocked PASS, current DB over-propagation residue query found 0 visible unreviewed matches after repair, `.venv\Scripts\python.exe -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only).
- Standalone audience response filter: local Python smoke checks PASS (`네`/`예` removed, sentence forms preserved), segment-list filter smoke PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only). `uv run` smoke NOT VERIFIED because the user-home uv cache path failed to initialize; direct `PYTHONPATH=src` smoke checks were used instead.
- Continue workflow/delete shortcut: `python -m compileall src/jamak` PASS, frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only). Browser visual check NOT VERIFIED because the in-app browser/node runtime failed with a Windows sandbox setup error.
- Text/cell shortcut split: `npm.cmd run build` PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS (`http://127.0.0.1:8710` returned 200).
- Review app visual redesign: frontend `npm.cmd run build` PASS, `python -m compileall src/jamak` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS and root served new built assets (`index-Ck2xiCJK.js`, `index-DXzJDlpH.css`). Browser visual check NOT VERIFIED because the in-app browser/node runtime is still failing with a Windows sandbox setup error.
- Eye comfort color tuning: frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root smoke PASS and root served new built assets (`index-DcHoUJtu.js`, `index-Cj0Kab1c.css`).
- Copy wrapping cleanup: frontend `npm.cmd run build` PASS, `git diff --check` PASS (line-ending warnings only), HTTP root served new built assets (`index-DXZuCohL.js`, `index-BuhVC8YR.css`).

- `uv run jamak run https://youtu.be/lFuxxOlgl5Y` 전체 파이프라인(교정 포함) → PASS — 2026-07-10
- 웹앱 E2E (목록→에디터→편집→저장→DB→export 반영) → PASS — 2026-07-10
- absorb/eval 루프 (diff→교정쌍→CER, 멱등성) → PASS — 2026-07-10
- 현재 영상 피드백 전파 스팟체크(임시 SQLite): PASS — 2026-07-10
- 검수 타이밍 UX 스팟체크(임시 SQLite merge/boundary/redistribute): PASS — 2026-07-10
- 연결형 타이밍 버튼 스팟체크(임시 SQLite prev/next boundary + manual overlap): PASS — 2026-07-10
- 즉시 삭제 Undo 스팟체크(임시 SQLite + FastAPI TestClient): PASS — 2026-07-10
- 프론트엔드 빌드(`npm.cmd run build`): PASS — 2026-07-10
- HTTP smoke (`http://127.0.0.1:8710`, `/api/jobs`): PASS — 2026-07-10
- Browser plugin visual check: NOT VERIFIED — node_repl browser runtime failed with sandbox setup error twice
- `uv run jamak doctor`: PARTIAL — ffmpeg missing in PATH, GPU/ctranslate2/API key/DB OK
- 실 검수 데이터 기준 CER 추이: NOT VERIFIED (검수 데이터 아직 없음 — 시뮬레이션만)
