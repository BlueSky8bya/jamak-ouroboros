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

## Parked (데이터 게이트 — 나중에 재실험)

- **STT 파인튜닝 (ADR-0004 stage3)**: 지금은 `large-v3-turbo` 유지(범용 최선, v3보다 나음 실측). 범용 모델 교체로 얻을 것 거의 없음 — 진짜 개선은 검수 오디오로 turbo LoRA 파인튜닝. **트리거: 검수 오디오 ≥10시간** (`jamak export-training-data`의 minutes, 현재 ~0.13h). 8GB로 QLoRA 가능. 그때까지 검수로 오디오만 축적. gap-fill(YouTube)이 whisper 미스 커버하는 안전망 이미 있음.
- **로컬 교정 모델 (ADR-0005 Phase 2)**: 교정을 로컬 파인튜닝 소형 LLM으로 이전. **트리거: 교정쌍 ≥ ~2,000~5,000** (`jamak export-correction-data`의 pairs로 확인, 현재 113). 도달하면 EXAONE/Qwen/Gemma 2~7B LoRA 파인튜닝 → `jamak eval` CER 게이트로 Claude 이하일 때만 채택. 그때까지 검수·absorb로 데이터만 축적. Phase 0(스킵 40%)·Phase 1(export) 이미 됨.

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

- **검수 효율 3종** (반복노동·마우스의존↓, 정보량 과다 주의):
  - **찾기·바꾸기 전체 일괄** (`POST /replace` + 접이식 바): 반복 오인식을 전 자막에서 한 번에 교정. 기본 접힘("🔎 찾기·바꾸기" 링크), 열면 찾기/바꿈 입력 + 라이브 매치수 프리뷰(디바운스) + 모두 바꾸기(매치 있을 때만). API 0, 결정적. 검증: 프리뷰 "여러분" 12곳/11자막, 접힘/열림/닫힘, 라이브 카운트.
  - **키보드 검수 루프**: `Alt+Shift+↑/↓` = 이전/다음 **미검수** 자막 점프(확인한 건 건너뜀). 수정자키라 타이핑 중 안전(사용자 우려 반영). 기존 `Alt+↑/↓`(인접)에 `!shift` 가드. 검증: 포커스 0→1행 이동.
  - **구간 반복 재생**: `🔁 구간반복` 토글 — 편집 중 현재 구간 오디오 loop. 재생 컨트롤 아래 2토글행(반복·입력중멈춤). 빌드 PASS, 콘솔 0.

- **피로도 정밀 보강 3종** (2026-07-10, 화면 정보량 순증 없이 감소 지향, build+preview 검증):
  - **완료 자막 접기** (progressive disclosure): reviewed 행은 `collapsed`(=reviewed && !focused)로 1줄 요약(✓·텍스트·시작시각)으로 접힘 — 리스트가 작업할수록 짧아져 스크롤·시선피로↓. textarea는 DOM에 숨겨만 둠(autosave/handle 그대로). 클릭·`Alt(+Shift)+↑/↓`이면 `focusSegment`로 펼침+포커스. 검증: 12행 접힘, 높이 161→31px(~80%↓), 클릭 시 펼침(collapsed 12→11).
  - **남은 시간 추정**: 최근 확인 12개 타임스탬프(`paceRef`, `performance.now`)로 페이스 계산 → hero에 "이 속도면 약 N분 남음"(샘플 3개↑, 남은 것 있을 때만). 끝없는 리스트 불안↓. 검증: 3회 확인 후 표시.
  - **구간 통과 미세 축하**: 25/50/75/100% 교차 시 statusbar 메시지 + hero 짧은 pulse(`celebrate`, 900ms). 새 박스 없음. 파일: `Editor.tsx`, `styles.css`(.collapsed-preview/.cp-*/.flow-eta/hero-celebrate). 검증 중 실사용 job(LI3phxRnkMM) reviewed 3개 임시 토글 → **원상복구 완료**(12개, idx 4·18·23…67 그대로).

- **작업대(랜딩) 강화 3종** (2026-07-10, `App.tsx`+`styles.css`, build+preview 검증):
  - **이어서 검수 히어로**: 진행 중(segments>0, !ko_complete, !running) 영상 중 **완료 임박순** 1개를 상단 큰 카드로 — 썸네일·제목·진행바·"12/81·15%·남은 69개"·`이어서 →`. 원클릭 재개로 "뭘 열지" 결정피로 제거. 검증: 히어로=LI3phxRnkMM, 클릭 시 에디터(81행) 진입.
  - **살아있는 대시보드**: 기존 밋밋한 chip 3개 → 통계 타일(영상·완료·검수한 자막·남은 자막·처리 중). 검수한/남은 자막 합계로 우로보로스 성장 체감. 검증: 검수한 자막 136(12+124), 남은 69.
  - **뷰 기억 + 키보드**: 필터/정렬 localStorage 저장(재방문 재설정↓), `/`=검색 포커스, 검색칸 Esc=지우기·blur. 검증: `/`로 검색 포커스, localStorage 키 저장. 다크 대비 확인(제목 #f2f5fa, 메타 #bcc7d6). 이번 배치 데이터 변경 없음(내비게이션만).
  - **정렬 기준+방향 분리 + 배치 정리** (후속): 정렬을 기준(업로드일·추가일·진행률·영상 길이·제목) + `↓내림/↑오름` 토글로 분리, `jamak.dir` 저장. 통계는 떠 있던 타일 → **하나의 세그먼트 바**(연결·max-content)로 정돈. 검증: 방향 토글 시 카드 순서 역전(desc↔asc)·라벨·저장, 진행률 asc=15%→100%, 정렬 옵션 5개.

- **작업대 벤치마킹 대량 확장 12종 + 좌우 균형 재설계** (2026-07-10, `App.tsx` 전면 재작성 + `styles.css`, build+preview 전수 검증, 상시 노이즈 0 지향 — 대부분 hover·조건부·숨김):
  1. **좌우 균형 재설계**: 통계바 full-width(링+숫자 space-between, 1071/1119px), 상태칩/툴바 폭 정렬. 적은 영상일 때 우측 공백은 **목록 보기**로 해소.
  2. **전체 검수 도넛 링**: totalReviewed/totalSegments SVG 도넛(66%=136/205) — 우로보로스 성장 한눈.
  3. **상태 퀵필터 칩**: 전체/검수 중/완료/처리 중 + 각 카운트, 원클릭(Linear/Notion식). `jamak.status` 저장. 검증: 완료→1장.
  4. **카드/목록 보기 토글**(▦/☰, `jamak.view` 저장): 목록=full-width 행(168px+1fr). 검증: 클래스·컬럼.
  5. **카드 hover 퀵액션**: `.srt 바로 받기`(완료본, 기존 exportUrl) · `링크 복사`(clipboard) — 에디터 안 열고 처리. hover에만 노출.
  6. **아무데나 붙여넣기→링크 자동 감지**: window paste에서 youtube id 파싱 시 URL칸 자동 채움+포커스.
  7. **생성 전 썸네일 미리보기**: URL칸에 유효 링크 → 썸네일+"이 영상으로" 확인. 검증: 표시/사라짐.
  8. **스켈레톤 로딩**: 첫 fetch 전 shimmer 카드 4장(체감 속도).
  9. **카드 상대시간**: 업로드일 없으면 "N일 전 추가"(relTime).
  10. **검색어 하이라이트**: 제목 매칭 `<mark>`. 검증: "예수" 1건.
  11. **필터 초기화 칩**: 필터/검색 활성 시만 노출. 검증: 표시→초기화 2장 복귀.
  12. **키보드 + 도움말**: `/`=검색, `N`=URL칸, `?`=단축키 팝오버, Esc=닫기/지우기. 검증: N 포커스, ? 팝오버(4행) Esc 닫힘.
  - 카드 `<button>`→`<div role=button>`(중첩 버튼 허용, `.disabled` 규칙 이관). 다크 대비 확인(링 #f2f5fa, 칩 텍스트 정상). 데이터 변경 0.

- **언어 배지 오버플로 방지 + 작업대 추가 7종** (2026-07-10, `App.tsx`+`styles.css`, build+preview 검증, 데이터 변경 0):
  - **언어 배지 캡(+N)**: 번역 언어가 많아도 한국어+최대 3개만 노출, 나머지는 `+N` 칩(title에 전체 나열). 검증: 6개 언어 주입 → 한국어✓·영어✓·일본어✓·중국어 + `+3`(title 6개), head 2줄 우측정렬로 안 깨짐.
  - **썸네일 오버레이 3종**: 완료본 `✓ 완료` 리본, 진행 중 하단 진행 오버레이 바, 처리 중 상단 스캔 라인 애니메이션 — 카드 열지 않고 상태 파악.
  - **키보드 카드 네비**: `←→↑↓`로 카드 커서 이동(파란 링)+스크롤, `Enter`로 열기. 검증: 커서 0→1, Enter로 에디터 진입.
  - **툴바 sticky**: 상태칩+필터바를 스크롤 시 상단 고정(blur 배경). 긴 목록에서도 필터 접근. 검증: position sticky.
  - **탭 타이틀 앰비언트**: `작업대 · 남은 69` (남은 자막 수 반영). 검증 ✓.
  - **썸네일 로드 실패 fallback**: img onError→`.broken`(투명, surface 배경 노출).

- **자막이 침묵까지 늘어나는 문제 해결** (2026-07-10): 세그먼트가 대부분 contiguous(end[i]=start[i+1], median gap 0)라 침묵 구간에도 앞 자막이 남아있었음. word 타임스탬프는 DB에 없지만 `job_dir/stt.json`에 캐시됨.
  - **A. 파이프라인 근본 수정** (`pipeline/split.py`, 앞으로/재인식 적용): `SILENCE_SPLIT=0.7`s 침묵에서 **강제 컷**(짧은 줄도), split을 **모든 세그먼트**에 적용(짧은 것도 word 경계로 다듬기), tail-glue가 침묵을 넘어 병합 안 하게 가드. 오프라인 검증: 1.0s 휴지에서 2조각(1.2→2.2 무자막), 짧은 줄 0.0-4.0→1.0-1.8 word-tight.
  - **B. 라이브 비파괴 다듬기** (`POST /api/jobs/{id}/tighten`, `✂ 무음 다듬기` 버튼): stt.json 단어시각으로 각 자막을 실제 발화 시작~끝에 스냅. **timing만 변경 — 텍스트·검수·개수 불변**(검수 중에도 안전), API/GPU 0. 오프라인 검증(실 stt.json, DB 미변경): 76/89 다듬김, 선행 침묵 제거(15.53→16.64=1.1s), 실제 gap 15→22개, 연속 발화는 contiguous 유지.
  - 서버 재시작 완료 → `/tighten`·파이프라인 라이브. (프리뷰 서버 812c5392)

- **미세 타이밍 UX 대량 추가** (2026-07-10, 벤치마킹: Aegisub·Subtitle Edit 파형/스냅·YouTube Studio·Descript). 스트레스 없는 정밀 조절이 목표:
  - **발화 시각화 맵(WordMap)** — 파형 대체(유튜브 iframe은 오디오 접근 불가). `GET /api/jobs/{id}/words`(stt.json 단어시각, 읽기 전용)로 포커스된 자막 구간에 **단어 블록(초록=말소리) + 침묵**을 미니 타임라인으로 그림. 시작/끝 **손잡이를 끌면 가장 가까운 단어 끝에 자석처럼 스냅**(SNAP 0.12s), 빈 곳 클릭=시크, 재생헤드 표시. 포커스 행에만(정보량 관리).
  - **넛지 버튼** — 시작/끝 각각 `◀▶` ±0.1s 마우스 미세조절(포커스 행). Alt(+Shift)+←→ 키와 동일.
  - **⤢ 발화 맞춤(행별)** — 이 자막만 실제 발화 시작~끝으로 스냅(앞뒤 침묵 제거), 단어시각 이용, 1 undo 스텝.
  - `setTimes`(양끝 동시, pushUndo) 추가. WordMap/발화맞춤/드래그 전부 Ctrl+Z 가능.
  - 검증(완료본 포커스, **DB 쓰기 0**): WordMap 렌더(단어블록 8, 손잡이 2 @21%/79%, 밴드, 재생헤드), 넛지 4개, 발화맞춤 버튼, `/words`=605단어. 빌드 PASS, 콘솔 0. 시드 임포트 영상(단어 없음)은 WordMap 자동 숨김.

- **자막 미리보기 + 미리보기(극장) 모드** (2026-07-10, 프론트 only): 커밋 e523cb2 이후.
  - **영상 위 자막 오버레이**: `currentTime`에 맞춰 현재 큐를 유튜브 영상 위(하단 중앙 유튜브식 캡션)에 겹침. 활성 큐 없는 침묵 구간엔 자동 사라짐(발화-밀착 타이밍 그대로 확인).
  - **영상 비율/크기 근본 수정**: YT.Player가 기본 640×360으로 iframe 생성 → 패널 폭에 잘려 비율 엉망·작음. `width/height:"100%"` + `#yt-player`(=iframe) aspect-ratio로 16:9 꽉 채움. 검증: 편집 396×226 → 미리보기 634×360, ratio 1.76.
  - **미리보기(극장) 모드**(토글, 기본 OFF — 편집이 1순위): 영상 크게(좌열 440→678px), 오버레이 18px, **재생 중 큐를 화면 가운데로 자동 스크롤 + 확장 + 강한 파란 링 하이라이트**. 편집 모드에선 안 함(속도 불일치). 검증: 활성 큐 확장·38% 중앙·box-shadow 파란 3px 링.
  - **현재 큐 하이라이트 강화**(전역): `.row.active` 파란 3px 링 + 배경 틴트(기존 약함 개선).
  - **Shift+Alt+Tab = 3초 뒤로**(단축키 추가, 단 Windows에서 OS가 Alt+Tab 가로챌 수 있어 Shift+Tab이 확실). 치트시트 갱신.

- **타이밍·도구 단축키 대량 추가** (2026-07-10, 프론트 only, 전역 keydown, 편집 중에도 Alt 조합이라 안전):
  - 큐 타이밍: `Alt+,` 여기서 시작 · `Alt+.` 여기서 넘김 · `Alt+/` 발화 맞춤(포커스 큐, flush 후 실행).
  - 모드 토글: `Alt+R` 구간반복 · `Alt+S` 편집 시작 시 멈춤 · `Alt+P` 미리보기.
  - 좌패널 도구: `Alt+B` 찾기·바꾸기 · `Alt+G` 복구·채우기 · `Alt+M` 무음 다듬기 · `Alt+K` 학습.
  - Windows/Chrome 예약키 회피(Alt+D/E/F 안 씀). 버튼 tooltip·치트시트에 표기.
  - 검증: 토글 4종(Alt+P/R/S/B) E2E 플립 확인. DB 쓰는 것(,./·M/G/K)은 버튼과 동일 핸들러라 미실행(실사용 검수 중 보호). 빌드 PASS, 콘솔 0.
  - **3초 앞/뒤 seek 단축키**(추가): `Alt+<`(=Alt+Shift+,) 3초 뒤로 · `Alt+>`(=Alt+Shift+.) 3초 앞으로.

- **단축키 footgun 사고 + 수정 + 복구** (2026-07-10, 중요): `Alt+.`=여기서 넘김(경계 이동=시간 파괴)과 `Alt+Shift+.`=3초 앞으로를 **같은 키에** 뒀더니, 사용자가 seek 하려다 Shift 놓쳐 초반 큐(idx1-4) 타이밍 훼손(음수/17s dur).
  - **지혈**: 파괴적 타이밍 단축키(여기서 시작/넘김/발화맞춤)를 `,`/`.`/`/`에서 **`Alt+[`/`Alt+]`/`Alt+\`**(in/out 관례)로 이전. `,`/`.`는 seek 전용(Shift 필수), Shift 놓치면 무동작. 검증: `Alt+.` 3연타 시간 불변, `Alt+Shift+.` seek만.
  - **복구**: stt.json 단어시각으로 idx1-4 텍스트-단어 정렬(정확 일치 확인) → **역순(idx4→1) PUT**로 이웃 linking 클램프 회피. 결과 idx0-5 정상·음수0·순서정상. idx2만 contiguity linking으로 9.55부터(원래 침묵 1s) — 무음 다듬기/드래그로 미세조정 가능. 잔여 overlap 1곳(idx9/10 −0.2s)은 이전부터 존재.
  - 교훈 메모: `destructive-shortcut-footgun`. 파괴적 동작을 nav 키 옆(모디파이어 1개 차이)에 두지 말 것.

- **단축키 근본 재설계 (안전 우선, 벤치마킹)** (2026-07-10): 원칙 = "키 하나=한 성격, 파괴적 동작은 nav 키의 모디파이어 1개 차이에 절대 안 둠, 오타/Shift 실수는 무동작이거나 같은 계열".
  - **화살표 = 순수 이동만**: `Alt+←/→` 3초 seek, `Alt+Shift+←/→` 10초 seek, `Alt+↑/↓` 자막 이동, `Alt+Shift+↑/↓` 미검수 이동. 파괴 동작 배정 0 → Shift 실수해도 무해.
  - **경계 편집(파괴적, 되돌리기 됨) = 고립된 `Alt+[`/`Alt+]`/`Alt+\`** (in/out 관례). 화살표·seek 키와 물리적으로 분리.
  - **위험한 맨키 제거**: 맨 `Delete`(셀 삭제), 맨 `Ctrl+Z`(셀 undo), `Ctrl+Esc`, `Alt+Shift+,/.` seek, `Shift+Alt+Tab` 전부 삭제 → 삭제=`Alt+Delete`만, 셀 undo=`Alt+Z`만, 글자 Delete/Ctrl+Z는 입력칸 안 네이티브.
  - 키보드 ±0.1s 시간 넛지 제거(화살표를 seek로 회수) → 미세조정은 타임라인 드래그·◀▶ 버튼.
  - 토글/도구 `Alt+P/R/S/B/M/G/K` 유지. 치트시트 전면 갱신(그룹 제목에 안전성 명시). 검증: Alt+→/Alt+Shift+→ seek·Alt+↓ 이동 ✓, 맨 Delete·Alt+. 무동작(89→89, 시간 불변) ✓. 빌드 PASS, DB 쓰기 0.

- **경계 조절 규칙 업계 표준화 + 깜빡임 방지** (2026-07-10, 사용자 결정): 이원화(핸들=연동 / WordMap=독립)로 혼란 → 통일.
  - **모든 가장자리 드래그 = 독립 리사이즈**: TimingStrip 핸들도 `boundary_prev/next`(연동) 대신 `timeChange`→`update_segment`(독립) 사용. WordMap도 동일. `update_segment`를 push→**clamp**로 변경(줄이면 gap, 늘려서 겹치면 이웃 벽에서 멈춤, **이웃 절대 안 밈**). 검증(완료본 1셀, 복원): 축소→gap+이웃불변, 확장→벽 clamp+이웃불변, 정확 복원.
  - **`여기서 시작/넘김` 버튼만 연동 유지**(벽 통째 이동 — 초반 대략 수정용).
  - **내보내기 깜빡임 방지**(`assemble.to_srt`, `GAP_JOIN_BELOW=0.2s`): 자막 사이 gap이 200ms 미만(또는 겹침)이면 **이어붙여 연속 출력**, 200ms↑는 실제 침묵으로 유지. 검증(오프라인): 0.1s→join, 0.5s→유지, 겹침→clamp. Netflix 2프레임·Subtitle Edit min-gap 관례 반영.
  - ⚠️ 백엔드 변경 → 서버 재시작 완료(9e089044).

- **꼬리/gap 구간 마지막 자막 조절 불가 수정** (2026-07-11): 재생헤드가 마지막 자막 뒤(꼬리)나 gap에 있으면 active 자막이 없어 TimingStrip 핸들이 안 붙고, 창도 빈 공간으로 스크롤돼 마지막 자막이 화면 밖으로 나감 → 못 잡음.
  - `handleTargetId = activeId ?? nearestBehind`(재생헤드 바로 앞 자막) → 꼬리에서도 마지막 셀에 양끝 핸들.
  - `live` 창: active 없을 때 `center = min(currentTime, nearestBehind.end+5)`로 붙잡아 그 자막을 화면에 유지.
  - 검증: 재생헤드 7:14.3(꼬리)인데 창 6:53.3–7:09.3로 마지막 자막(6:53~6:56) 유지, start+end 핸들 각 1개. 콘솔 0.

- **비용 구조 개편** (commit cee717a): thinking off(출력 3.6k tok, $0.074/영상), 교정 캐시(재실행 $0), pre-pass(count≥2 교정쌍 무료 치환 — 피드백 쌓일수록 API 의존 감소), id 기반 매핑(동시 편집 안전), 삭제 확인창, 단계별 모델 env, 토큰/비용 리포트 출력
- 남은 비용 레버 (미적용): Batch API(-50%, 비동기 1h), JAMAK_CORRECT_MODEL=claude-haiku-4-5(-66%, 품질 검증 필요), M5 whisper 파인튜닝(교정 API 자체 제거)

- 랜딩 페이지: URL 붙여넣기 → 웹에서 파이프라인 실행 (백그라운드 subprocess + 상태 폴링). 같은 영상 재제출은 409 (검수 데이터 보호)
- 세그먼트 구조 편집: 커서 위치 분할(시간 비율 배분) / 병합 / 삭제 — E2E PASS
- 타이밍 보조: 현재 재생 시간으로 `여기서 시작`/`여기서 넘김`, 이웃 자막 자동 연동, 합치기 중복 제거
- 즉시 삭제 + Undo: 삭제 확인창 제거, 왼쪽 패널 되돌리기 버튼/상태 표시, `Ctrl+Z` 세그먼트 복구
- 다운로드 파일명 대소문자 파싱 버그 수정 (`제목_자막_<lang>.srt` 정상)
- 피드백 흡수 버튼: 저장 레이스 제거, 현재 영상 뒤쪽 미검수 자막 즉시 갱신, export 자동 흡수 결과가 다운로드 파일에 포함되도록 순서 조정
- **웹에서 새 URL 최초 제출 → 파이프라인 완주: NOT VERIFIED** (기존 영상 409 경로만 검증. 첫 실사용 시 확인 필요)
- **시드 코퍼스 용어 마이닝** (`jamak glossary-mine`, `src/jamak/glossary_mine.py`): 1년치 검수 코퍼스(`data/seeds/기존 검수 완료본.txt`, 260만자)에서 빈도 후보 1500개 결정적 추출 → Claude 1회 정제(sonnet, thinking off)로 도메인 어휘만 선별 + 카테고리 + 오인식 변형 부여 → `approved=True`로 upsert. 실행 결과: +47 신규 / 18 승격 = 승인 65개(고유어휘 22, 기독교 13, 지명 10, 인명 6, 한자어 6, 불교 5, 유교 1). 비용 $0.06 일회성. 이제 hotwords/initial_prompt가 축지법/공중부양/하늘궁/신인/석가모니/십자가/석고대죄/용맹정진 등으로 채워짐. 교정쌍은 기계 초안이 없어 불가 — 요청대로 hotwords+용어사전만 채움. 잔여 노이즈(조사 붙은 형태: 신인이, 십자가가, 미국은)는 hotwords에 무해, `/glossary-review`로 정리 가능.

- **STT 리세마라** (`POST /api/jobs/{vid}/retranscribe` + 랜딩 카드 `🎲 음성인식 다시 시도` 버튼): 현재 용어사전/hotwords로 기존 영상 STT 재실행(`jamak run <url>` 백그라운드, 세그먼트 교체). 용어사전 성장 → 인식 개선 기대 시 리롤. **한국어 검수 완료(ko_complete) 시 프론트 버튼 숨김 + 백엔드 409 이중 차단**. 부분 검수는 프론트 confirm(편집 N개 초기화 경고). 검증: 완료 영상 직접 POST → 409, 미완료 영상만 버튼 노출(스크린샷).

- **STT hallucination 근본 수정** (사용자 보고: "생판 다른 단어 수십개 연속"): 원인 3가지 — (1) `initial_prompt`(용어 나열 문장)을 whisper가 무음/박수에서 그대로 토해냄, (2) `condition_on_previous_text=True`로 그 echo가 다음 창으로 전파돼 수십개 연속 반복(cascade), (3) `transcribe`가 `stt.json` 캐시 반환 → "다시 시도" 눌러도 STT 재실행 안 됨(재분할만).
  - 예방(stt.py): **initial_prompt 미주입**(용어는 hotwords 음향편향으로만 — echo 불가), **`condition_on_previous_text=False`**(cascade 차단), `no_repeat_ngram_size=3`, `compression_ratio_threshold=2.4`, `force` 캐시 무효화.
  - reroll: `jamak run --fresh` → 캐시 무시 재전사. `retranscribe` 엔드포인트가 `--fresh` 전달.
  - 복구(prompt-agnostic): `noise.cascade_indices`(연속 동일 자막 = 신뢰 가능한 hallucination 시그니처) + `is_known_prompt_leak`(옛 기본 프롬프트 템플릿). crosscheck + repair-stt 양쪽 적용 → 프롬프트가 마이닝으로 바뀌어도 옛 누수 감지. **검증: LI3phxRnkMM 12/12 YouTube 자막으로 복구, 잔여 누수 0, 완료본 lFuxxOlgl5Y 오탐 0 (E2E API PASS).**
  - **NOT VERIFIED: 예방 로직의 실제 whisper 재전사** (GPU 8분 소요 — 미실행). 감지/복구는 검증됨.

- **STT 시작 부분 손실 복구** (사용자: "1번 셀이 신인 첫 발화가 아닌 엉뚱한 뒤에서 시작, 앞에 셀 추가도 안돼 꼬임"): whisper가 인트로/음악 위 발화를 VAD로 버려 첫 세그먼트가 24.6초부터 시작(0~24.6초 통째 손실). YouTube 자막은 3.8초부터 실제 발화 있음.
  - 예방(stt.py): VAD 완화 `threshold=0.35`, `speech_pad_ms=400` → 조용한/음악 위 인트로 발화 안 버림.
  - 복구(crosscheck.py): `deroll_captions`(롤링 YouTube 자막 → 중복 제거 + 다음 시작으로 end 클램프 = 겹침 없는 실제 라인들) + `youtube_gap_rows`(whisper가 아무것도 없는 구간, 특히 맨앞을 YouTube 자막으로 채움). 파이프라인/재전사 시 자동 적용.
  - 즉시 복구(repair-stt 확장): 기존 echo 복구 + **빈 구간 gap-fill(맨앞 포함) 삽입 + start 기준 재인덱스**. 버튼 `🛠 음성인식 복구 · 빈 구간 채우기`. **완료본(전 세그먼트 reviewed)은 409로 차단**(검수 훼손 방지).
  - **검증**: LI3phxRnkMM 69→107 세그먼트, idx0가 24.6초→**3.8초 "내가 여기 있어 여러분이 나를"**, 재인덱스 단조, 2차 호출 멱등(0). 완료본 lFuxxOlgl5Y 409 차단 + 124개 무손상. (실수로 완료본에 삽입됐던 25개는 삭제 복구함.)
  - **NOT VERIFIED**: 에디터 UI에서 토스트/버튼 라벨 시각 확인(빌드 PASS, API E2E만 검증). VAD 완화의 실제 whisper 효과(재전사 미실행).

- **gap-fill 정직성 수정** (사용자: "음성인식이랑 유튜브 자막이 왜 똑같지? 모델이 인식한 거 맞아?"): gap 세그먼트에 `text_whisper=YouTube텍스트`를 넣어 참고칸 "음성인식"이 유튜브와 동일하게 보여 오해 유발. 수정: gap 행은 `text_whisper=""`(whisper 실제로 못 들음) + 작업텍스트는 `text_llm/text_final`에 유튜브 시드. 에디터 참고칸이 빈 whisper면 "이 구간은 음성인식이 놓쳐서 유튜브 자막으로 채웠습니다" 안내 표시. 기존 38개 행 데이터도 `text_whisper` 비움. `reviewed` 상태 라벨 매핑 추가. **검증: 에디터 첫 세그먼트 0:03.8 "내가 여기 있어..." + 참고칸 정직 표시 (스크린샷), 콘솔 에러 0.**

- **`>>` 화자표시 자동 제거 (API 0)**: `crosscheck.strip_speaker_markers` — YouTube 자막의 `>>`/`>` 마커를 파싱 단계에서 제거(모든 다운스트림 clean). 기존 DB 163개 세그먼트/번역도 일괄 정리(0 잔여). 결정적, API 미사용.
- **참고칸 표시 조건 개선**: `showSources = flagged || uncertain || (youtube/whisper가 작업텍스트와 다름)`. crosscheck 플래그가 token 유사도 관대(예: whisper "보고삼" vs YouTube "부부삼"이 플래그 안 됨)해서 참고칸이 숨던 문제 해결. 검증: 21.1초 세그먼트 참고칸 이제 표시(오인식 비교 가능), `>>` 0개, 콘솔 에러 0.
- **STT --fresh 실증**: LI3phxRnkMM 재전사(수정 STT, 교정 없이) → echo 0(이전 12), 첫 whisper 실제발화 160초→21초, avg_logprob 균일.
- **모델 교체 large-v3 → large-v3-turbo (기본값 변경, config.py)**: 같은 영상 v3 vs turbo 실측 비교 — 첫 실제발화 21.1초→**2.2초**(인트로 직접 인식), raw 20→32세그, 커버 347→402초, YouTube gap-fill 28→**9**(의존 급감), 오인식 "보고삼"→**"부부싸움"** 교정, echo 0 유지, 속도↑. turbo 결정적 우세 → `JAMAK_WHISPER_MODEL` 기본 turbo. 모델은 HF 캐시됨(`mobiuslabsgmbh/faster-whisper-large-v3-turbo`).

- **교정 API 절감 tier 1.5** (`correct._needs_llm` + `glossary.glossary_surface_forms`): LLM 보내기 전 "고칠 것 없는" 세그먼트 제외 — 빈 whisper(gap), 또는 (플래그 없음 AND 도메인어 없음). 교정은 "바뀐 것만 반환"이라 이들은 어차피 no-op → 손실 0. **실측 40% 세그먼트 제외**(LI3phxRnkMM 33/81, lFuxxOlgl5Y 52/124). E2E 실행 검증: 81세그→48 LLM, text_llm 81/81 채움, $0.038.
- **ADR-0005 + Phase 1 착수**: 교정을 로컬 파인튜닝 소형 LLM으로 점진 이전(번역은 API 유지) 결정 기록. `jamak export-correction-data`(`training.export_correction_pairs`): 검수 세그먼트에서 (whisper, youtube, final) 쌍 → `data/training/corrections/manifest.jsonl`. changed+unchanged 둘 다(유지 쌍이 "안 고치는 법" 학습), gap 제외. **현재 113쌍**(완료본 1개, 55교정/58유지). 트리거 2~5천쌍 도달 시 Phase 2(LoRA+CER 게이트).

- **검수 피로↓ 기능 2종 (API 0)**:
  - **① 안심 구간 일괄 확인**: `_is_safe`(플래그無 + uncertain無 + low_conf無 + 도메인어無)로 저위험 세그먼트 판별 → 에디터 "안심" 배지 + `POST /confirm-safe` 일괄 확인(text_final 승격, reviewed=True, 되돌리기 가능). `_needs_llm`과 동일 신호 재사용. 검증: LI3phxRnkMM 12개 원클릭 확인, 멱등, 빈 final 0.
  - **② 의심 단어 하이라이트**: 초기엔 whisper 단어확률(<0.55, `low_conf` 컬럼) 사용했으나 2025 CHI 논문이 단일신뢰도 하이라이트 "효과 없음+거슬림"으로 반박 → **2엔진 불일치 기반으로 교체**(`app._suspect_words`: whisper와 YouTube가 다른 단어; YouTube 없으면 `low_conf` 폴백). 검증: 41개, 예 "수있는"(vs YouTube "수 있는").
- **연구 기반 추가** (자막 후편집·인지부하 논문): **CPS 읽기속도 플래그** — 글자수/시간>17자/초 "⏩ 빠름 N" 배지(라이브), `_is_safe`에서도 제외. 이 영상 max 15.3이라 트리거 0(정상), 라이브 편집 시 배지 렌더 검증. 근거: [ASR후편집](https://aclanthology.org/2021.triton-1.23/) · [CHI2025](https://arxiv.org/html/2503.15124v1) · [자막속도](https://subtitlesedit.com/blog/netflix-subtitle-style-guide-explained) · [분할인지부하](https://pmc.ncbi.nlm.nih.gov/articles/PMC7901653/).
  - 3순위(Batch API −50%)는 미착수(대기).
- **디자인 피로도 패스** (사용자: 워크바 촌스러움 + 작업대 피로↓, 버튼 늘리지 말고): 
  - **다크모드** (장시간 눈피로 최대 절감) — `theme.tsx`: 시스템 선호 감지 + `localStorage` 지속 + ☀/🌙 토글(랜딩 헤더·에디터 상단). CSS 토큰 전면화(`:root` 라이트 + `:root[data-theme=dark]` 딥슬레이트) + 하드코딩 hex ~40개 토큰으로 치환(`--field-bg/--focus-bg/--reviewed-bg/--left-bg/--deep/--blue-ink` 등). 검증: 시스템 dark 자동 적용(body rgb(14,19,26)), 토글 라이트↔다크 전환·저장, 랜딩·에디터 전 요소 대비 양호(카드/배지/textarea/continue/좌측 다 확인), 콘솔 에러 0.
  - **몰입**: 편집 중(`focus-within`) 포커스 행은 부각(테두리+그림자), 나머지 행은 은은히 후퇴(opacity 0.66, hover 복귀).
  - **워크바 정돈**: 박스 남발 제거(border 0/투명), 버튼 radius 통일, `continue-btn` 다크 정합(--text→--deep). 버튼 수 증가 없음(토글 1개만).
  - 스크린샷 툴은 에디터 YouTube iframe으로 계속 타임아웃 → 색상은 `preview_inspect` 계산값으로 검증.
- **좌측 패널 v2 재설계 + 미세 인터랙션** (사용자: 배치 어지러움, 몰입/조작감 벤치마킹): 잡탕이던 하단(workbar/복구/안심/멈춤/진척/이어서/내보내기/학습)을 4구역으로 그룹화 — ①상태(은은한 autosave 점+텍스트, 토스트 X) ②**진행 히어로**(큰 진척 12/81·%·바 + `이어서 작업하기` = 유일 주 CTA, momentum) ③**도구**(안심/복구/학습/멈춤 = compact pill 보조, 안심만 teal accent) ④내보내기 푸터. 핸들러는 `runRepair/runConfirmSafe/runAbsorb/runExport` 함수로 추출. 미세 인터랙션: 모션 토큰(110/200/340ms), 체크 완료 pop 애니(연구: 만족도↑), 저장 점 pulse, `prefers-reduced-motion` 존중. 벤치마킹 근거: 인지명료성>화려함·마찰제거·momentum·미세피드백. 검증: 신규 4구역 렌더, 도구 compact, 라이트/다크 대비 양호, 콘솔 0, 빌드 PASS. 근거: [calm UX](https://www.uxmatters.com/mt/archives/2025/05/designing-calm-ux-principles-for-reducing-users-anxiety.php) · [flow](https://peepaldesign.com/flow-state-in-ux-designing-for-engagement/) · [micro-interactions](https://www.justinmind.com/web-design/micro-interactions) · [Descript/Aegisub 패턴](https://aegisub.org/docs/latest/editing_subtitles/).
- **에디터 점진적 노출(progressive disclosure)로 정리** (사용자: 버튼 너무 많아 어지러움): 편집 중인 행(`focused`)만 참고칸·의심단어·타이밍(여기서시작/넘김)·구조(나누기/합치기/지우기) 노출, 나머지 행은 [시간·배지·텍스트·확인완료]만. 자막 에디터 표준(한 번에 한 행). per-row 버튼 486→87(~82%↓). `복구` 버튼은 희귀 도구라 보조 스타일로 축소(안심 버튼은 유지). 검증: 신규 로드 시 81행 전부 간결(timing/sources/suspect 0 노출), 실제 클릭 시 해당 행만 전체 컨트롤(eval 확인), 콘솔 에러 0. (스크린샷 툴은 YouTube iframe으로 타임아웃 — eval로 검증)

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
