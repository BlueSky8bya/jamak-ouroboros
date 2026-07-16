# Current State

Last Updated: 2026-07-17 (v0.9.59 — 타이밍 자동 정리 폐지: ADR-0012, 실검수 제거 + 서버 410 차단, 연습5 재설계 반영)

## 연습 영상 크기 제약 (2026-07-16 측정)
영상은 에디터 왼쪽 열(`.left = minmax(390px,440px)`) 안에서 재생 → **표시 폭 ~362px = 캔버스 1920의 0.19배**.
읽을 글자는 **캔버스 84px 이상**(=화면 16px), 얇은 선·작은 점은 저배율에서 뭉개짐 → 굵고 성기게.
새 시각 큐 추가 시 `out/check/*_zoom.png` 절차로 **362px 축소본을 눈으로 확인**하고 확정.
상세: `docs/tutorial/재설계계획-2026-07.md` §0.5.

## 정책 (2026-07-16 확정)
- 기준은 **"그 동작이 Claude API를 쓰느냐"**. 비용 발생 동작만 관리자 전용.
- **검수자(비관리자)**: API 안 쓰는 모든 것 — 한자 채우기·타이밍 자동정리·무음 다듬기·나누기/합치기·찾기바꾸기·🙉·되돌리기·확인, **그리고 번역 검수(기존 번역 보기·수정)**.
- **관리자(운영자)만**: Claude API 쓰는 **생성** 동작 — 맞춤법 검사·**번역 생성/재번역**·초안 생성. (번역 *검수*는 검수자에게 열림 — 검수엔 API 안 씀.)
- **연습 영상(튜토리얼)**: 무-API 도구만 교육. API 도구는 아예 안 가르침.

Project Version: 0.9.25

## Recent Additions (2026-07-15 — v0.9.5~0.9.18, 파일럿 반복)

- **셀별 정답 안내 정착(v0.9.5~0.9.7)**: 안내창 3층 구조(상태줄/지금↔실제 말 대조/메타줄), 단어 단위 시간 배정 + 문장 낙오 규칙(머리=무조건 문장 셀로, 꼬리=그 셀 STT 텍스트 존재 여부로 판별, 진짜 걸침은 "그대로 두세요·연습 4에서" 정직 안내).
- **stale-build pill(v0.9.9)**: 5분마다 /api/version 대조 — 탭 오래 열어둔 사용자에게 "새 버전" 새로고침 안내 (구버전 번들 혼선 실제 발생 후 도입).
- **재생 조작 단계 개선(v0.9.10~11)**: 단계 진입 시 글 상자 포커스 자동 해제 + "깜빡이는 줄이 있으면 바깥 빈 곳을 누른 뒤 Ctrl+←" 어르신 화법 안내.
- **에코 가드 숫자 정규화(v0.9.12, CHG-036)** + 6개 기준본 전수 정리(유령 5·확장 4).
- **연습 4 재료 복원(v0.9.13~17)**: 초장문 병합 주입(창 17~32.5s + 머리 조각 흡수 + 텍스트 앵커), "차분히..." 행 복원 검증. 자동 정리 자체 모달·모든 브라우저 confirm 교체(useConfirm)·연습 repair 허용·클론 404 자동 복구(전 도구, v0.9.18)·미리보기 모드 단계 중 자동 복원·subject 단계 행 앵커+이미 열림 자동 통과.
- **워커 감시 1분 간격**(vbs 무창 실행 — 콘솔 깜빡임 제거 포함).
- **다음**: 사용자 파일럿 계속(연습 4·5·6), 이상 셀 스크린샷 기반 미세 조정.
Harness Protocol: project-initializing_260712.md (schema 1.1 — HARNESS_MIGRATION.md)

## Current Objective

**라이브 운영 중**: https://hky-jamak.com (Railway 앱+Postgres, Singapore 리전). 검수자 다인(≤50명) 동시 협업 안전. 관리자 PC는 영상 만들 때만(`jamak worker`). 다음: 검수자(고령 다수) 실제 온보딩 + 새 내용/타이밍 모드 실사용 피드백, 다회차 검수로 CER 추이 확인.

## Pending (사용자 액션)

- **v0.3.0~1 실사용 확인** — DELEGATED (인앱 브라우저가 YT iframe 못 열어 재생 연동 미검증): ① 흘려듣기(영상 재생 중 자막 따라오기 + 입력칸 밖 Enter 확인), ② 카라오케 단어 하이라이트가 실제 말과 잘 맞는지(비례 매핑 근사), ③ 단어 클릭 재생 체감, ④ 자동 정리 결과가 실제 영상에서 자연스러운지, ⑤ ▶버튼 실재생(b8cd8b2).

## Recent Additions (2026-07-15 — v0.7.1~0.8.5, CHG-20260715-020~025)

- **즉시 피드백 원칙**: CONSTITUTION §4.1로 명문화 (busy pill·진행바·결과 배너·모달 안 성공/실패·이중 실행 잠금). 침묵 구간 = 결함.
- **.srt 임포트 v2**: 구조 통째 교체 + 번역 이어받기(텍스트+시간 매칭) + undo v2 + 벌크 삽입(2231행 실사용 타임아웃 수정) + O(1) 매칭 미리보기.
- **번역 UX**: 빈·stale 셀 "한 번에 다 채우기"(edited 보호 제외), 동적 진행바, 번역 트랙 찾기·바꾸기(/replace 확장, edited=True 보호), 뒤로가기 = 앱 페이지 스택.
- **에디터 정리(v0.8.5)**: 글씨 크기 3단계 세그먼트(보통/크게/최대 — 구 bigtype 승계), 🎓 따라하기 버튼 제거(튜토리얼 탭이 대체), 도구 줄 균일 그리드 + 도구별 "⏳ …중" + 결과 배너(학습 0건도 명시). 코스 지정 UI 전부 제거(서버 스크립트 관리, bind_courses.py 패턴).
- **튜토리얼 영상 교체 완료(v0.8.6)**: 시각 큐(키캡·탭포인터·분할/합치기 애니메이션) 재렌더판 6개를 User가 재업로드(lJppD218Lmo/6aMrjCU4heI/Qo09NS2e2-c/bu2Se03ni-8/ruviKyheqNY/rL_5E-1ZQBE) → 워커 처리 + practice 지정 + 코스 1~6 재바인딩 + 결함 주입(basic 4/fast 2/timing 1, 스펙 일치). 구 영상 6개는 자동 언바인딩, User가 유튜브에서 삭제함. 코스 카드 커버는 유튜브 썸네일 → **테마 연동 그라디언트+아이콘**(다크/화이트 자동 적응, `--tut-accent`).
- **중복 자막 뿌리 차단(v0.8.7, CHG-028)**: 원인 2계통을 파이프라인에서 결정적 차단 — 교정 확장 백스톱(clamp_neighbor_extensions, 이웃 문장 흡수 시 whisper로 되돌리고 uncertain) + 에코 가드 퍼지·양방향 강화. 유닛 스모크 9건 + 실강연 7,614행 시뮬레이션(발동 0.5%, 전부 문제 패턴). CER 재확인은 다음 강연 실행 때.
- **자유 연습 개념 제거(v0.8.8)**: 구 practice Job 6개 + 클론 DB 삭제(사용자 승인) — practice 기준본은 코스 바인딩 6개뿐. 튜토리얼 탭의 "코스 없는 자유 연습" 섹션 삭제.
- **중복 데이터 해소 완료(v0.8.9)**: 연습 2·4·5·6을 fresh 재처리(가드 적용 워커) — 인접 중복 전부 0, timing 결함 재주입, 클론 정리. `dup_fix_v2.py` 불필요해짐.
- **워커 온디맨드 자동화(v0.8.9, CHG-030)**: `--until-idle` + 네임드 뮤텍스 싱글턴 + `jamak-worker-watch` 스케줄드 태스크(5분) + 로그온 1회 확인. 상시 기동·수동 켜고 끄기·중복 기동 걱정 소멸.
- **튜토리얼 v2 라이브(v0.9.2, CHG-033)**: 흐름형 확인 단계(untilTime, 남은 N개 카운트다운)·코스 프리셋(설정 강제+나레이션 설명)·오타 셀 지목(targetDefect, 이미 열린 행 자동 통과). v2 영상 6개 처리·바인딩 완료(CPKQt7GCgpc/ZdMsy4zzUNE/fZFLIiMStT0/FXyQAHziD8M/ASOX4NnIRJI/brWm8g0z0c0 — 결함 4/2/1 스펙 일치, adj-dup 전부 0, 6글자 미만 겹침 3행은 수동 정리: 연습4 토막말 재료 보존 포함). v1 Job 6개 DB 삭제. **다음: 사용자 파일럿 재주행 + 유튜브에서 v1 영상 삭제.**
- **사용법 모달 폐지(v0.9.1, CHG-032)**: Guide.tsx 삭제, 첫 방문은 튜토리얼 탭 자동 이동(`jamak.visited`). practice-6 나레이션의 구 버튼 언급도 v2 대본에서 해소됨.
- **연습 체크포인트 동기화 완료(v0.9.0, CHG-031)**: 나레이션이 지시를 마치는 시각에 자동 일시정지+말풍선, 수행하면 자동 재개, 그 전엔 "N단계 준비 중" pill만. 코스 2·3·4·5 투어 순서를 나레이션 순서로 재배열, 신규 사용자 딥링크가 basic에 덮이던 경합 FIX. 실브라우저 실재생 E2E 통과 — **사용자 파일럿(코스 1~6 완주) 대기**. 영상 재렌더 시 tutorialSync.ts 표도 갱신할 것.

## Recent Additions (2026-07-14 — v0.6.2~0.7.0, CHG-20260714-012~019)

- **튜토리얼 UX 확정(v0.7.0)**: 랜딩 상단 📋 작업/🎓 튜토리얼 탭 분리(연습 영상은 목록·통계·이어서에서 제외), 연습 입장 = **무조건 리셋**(클론 재복제 — 사용자 확정 "나갔다 들어오면 처음 상태"). 코스 카드 클릭 → 리셋된 클론에서 해당 코스 자동 시작. 관리자 코스 지정은 튜토리얼 탭으로 이동.
- **유령 중복 행 차단(v0.6.7)**: 유튜브 CC 꼬리 자막이 침묵 갭 채우기로 수입되던 것 — 에코 가드(파이프라인+복구), 연습 기준본 6개에서 59행 청소.
- **모바일(v0.6.3~0.6.6)**: 터치 편집(행 나누기·합치기·지우기 + 바 ↶), 버튼 줄바꿈 전수 수정, HCI 재배치(중복 재생 줄 제거·⚙ 바텀 시트·헤더 수리).
- **품질 루프(v0.6.2·0.6.4)**: CER 계기판(src·매칭 CER), 교정 큐 이탈 규칙 9, 용어사전 DB diff 채굴(승인 99개, 실측 variants). 남은 것: 코스 2~6 바인딩(관리자, 튜토리얼 탭에서), 파일럿 완주, P4 잔여(seek 앵커·tourEvent 성공 후·힌트 보기).

## Recent Additions (2026-07-14 — v0.6.1, CHG-20260714-011)

- **모바일**: ≤700px에서 영상 스티키 상단 + 세로 흐름 + 하단 액션 바(⟲3초/▶/🙉/✔ 맞아요 — Enter 확인의 터치 대체) + 고령 터치 타겟(≥48px)·입력 16px(iOS 확대 방지)·단축키 패널 숨김. **PWA**: manifest+아이콘 — 홈 화면 추가하면 앱처럼. 실기기 확인 User 위임.

## Recent Additions (2026-07-14 — v0.5.x~0.6.0, CHG-20260714-007~010)

- **P4 완료 (v0.6.0)**: 연습 영상이 **사용자별 병렬 격리** — 기준 Job 불변, 열 때마다 브라우저별 클론(`base~sha256(key)[:10]` video_id — 기존 엔드포인트 무수정 재사용), ↺ 처음부터 다시 = 재복제. 코스 바인딩(practice_course + 부분 UNIQUE + 관리자 카드 선택기 + GET /api/tutorials) + bind 시 결정적 결함 주입(basic 오타 4행 / fast 몽치 2행 / timing 침묵 연장 — hotwords가 대본 미끼 전멸시킨 것 대체) + 코스 메뉴 딥링크(클론 부트스트랩 → 자동 시작). YT 위젯 throw 시 앱 백지 → 재생만 강등 FIX. **P4 잔여(다음 배치)**: seek 앵커, tourEvent 성공 후 발생, 버블 중앙 폴백, 힌트 보기(사용자 결정 대기).
- **긴 영상 번역 502 FIX (v0.5.2)**: 60개 배치 루프+진행률+배치별 커밋+중복 실행 409. 2h 영상(p_9m8r1bZSM, 1563세그) en 번역 배치 실행 완료.
- **P2·P3·P5 1차 (v0.5.0~1)**: 연습 영상 6개 렌더(InJoon, 위치 안내 포함 77대사)→유튜브 업로드→워커 처리+practice 지정. **관리자 다음 액션: 각 연습 영상 카드에서 코스 1~6 바인딩**(선택기) → 파일럿 1명.

## Recent Additions (2026-07-14 — v0.4.0~0.4.3, CHG-20260714-001~006)

- **따라하기 투어 6코스** (v0.3.5→v0.4.0~2): 실제 동작해야 진행(`tourEvent` 훅 ~28곳), 🎓 코스 메뉴 + 완료 ✓(localStorage `jamak.tour.<id>`), 주요 단축키·기능 커버리지 100%(MAPPING.md). 중도 이탈("그만 볼래요")은 완료로 기록 안 함(v0.4.3).
- **연습용 영상**(`Job.practice`): 관리자 🎓 지정, 에디터 배너. **모든 학습·평가 경로에서 제외**(v0.4.3, CHG-20260714-005): absorb + 줄길이 학습 + 번역 few-shot + 학습 export 2종 + CER.
- **클러스터 재번역**(v0.4.1): 🔄 다시 번역이 클릭 셀 + 연속 stale·빈 이웃(±6, edited/fresh에서 중단)을 한 번의 문맥 호출로. 부수 수정: 번역 수동 저장 500(`_hash` import 누락).
- **연습 영상 파이프라인 계획**: `docs/tutorial/PLAN.md` **v3** (Codex 외부 감사 2라운드 반영 — §9/§10 disposition 표. 2차 핵심 수용: practice 지정을 등록 직후로, 앵커 {t, focus}, 스냅샷 생명주기(source_rev), reset 경합 가드, 부분 UNIQUE 인덱스, key={videoId} 재마운트, staticFile 계약. 기각: lease 테이블, 6코스×3줌 전수 검증, LlmCache namespace). **P2·P3 완료, P5 1차 리허설 완료(2026-07-14)**: mp4 6개 렌더(InJoon, 77대사 — 위치 안내 보강판) → 사용자가 유튜브 업로드(IMd3wZ2JXnk/wD1cnUipwlc/gpinjj2uF3w/aGmGzliGH64/NFPgJGFj4Sk/6kC2UaRt31s) → 워커 큐로 6개 전부 STT+교정 처리 + **처리 직후 practice=True 자동 지정**. 미끼 predicate 결과: ⚠ **텍스트 미끼 전멸**(깻잎·밤나무·축지법·공중부양·뭉치 6/6 전부 정확 인식 — hotwords 경고 적중, 웅얼 문장도 STT는 정확) / ✅ 자연 발생 오인식 풍부(천군·익킵니다·열린이·건넛뛰면·글시·12도 달 + 중복 에코 행 다수 — 고치기 재료로 충분) / ✅ 연습4 토막말 5행·LONG 행 존재 / ✅ 연습5 FAST(cps>17) 2행 / △ 연습2 5초 침묵이 에코 행에 일부 먹혀 실제 갭 3.7초(건너뛰기 연습엔 충분). **결정: 재렌더 안 함** — 텍스트 미끼 결정화는 P4의 기준 Job 결함 주입으로 해결(코스1 깻잎→깨잎류, 코스3 뭉치→몽치 2행, 코스5 타이밍 결함 — 클론 구조라 모든 사용자에게 동일). 웅얼은 사람 귀 기준이 본질이라 STT 정확해도 드릴 성립 — 가청성만 User 확인 대기. **다음 = P4 구현**(클론 세션 §4.3 v4 + practice_course + 결함 주입 + seek 앵커 + tourEvent 성공 후). 열린 결정: 힌트 보기 포함 여부(Agent 추천: 포함).

## Recent Additions (2026-07-13 — v0.3.3, CHG-20260713-010~011)

- **셀 단위 재번역**: 원문 바뀐(stale) 번역 행에 🔄 다시 번역 — 앞뒤 문맥 넣어 그 셀만 재번역(`POST /retranslate`, `retranslate_one`). 전체 재번역 불필요.
- **형식 토글**: 롱폼/쇼츠 드롭다운 → 세그먼트 토글. **워커 명령 복사 버튼**(큐 배너, 자동시작 실패 대비). "글씨 크게" 라벨.
- **워커 자동시작 참고**: startup 폴더 `jamak-worker-autostart.cmd`(→ run-worker.ps1)가 로그온 시 기동하나 머신 상태 따라 안 붙을 수 있음. 로그(`data/worker.log`)는 시작만 찍히고 멈춘 이력. 안 돌면 배너의 복사 버튼으로 `uv run jamak worker` 수동 실행. DATABASE_URL은 User env에 설정됨.

## Recent Additions (2026-07-13 — v0.3.2, CHG-20260713-009)

- **내보내기 전 점검 모달**: "자막 받기" 클릭 시 규칙 QC(미확인/보류/빈/빠름/초과/시간/공백, API 0원) + 카테고리별 "보기→" 점프. 차단 아님(그대로 받기 가능).
- **✏️ AI 맞춤법**(옵트인, ko): 오타·띄어쓰기만 제안(구어체·사투리 보존), 줄 단위 LlmCache 캐시, diff 체크리스트 선택 적용 + Alt+Z 일괄 원복. 모델 `JAMAK_SPELL_MODEL`(기본 CLAUDE_MODEL).

## Recent Additions (2026-07-13 — v0.3.1, CHG-20260713-008)

- **읽기 뷰**(내용 모드 비포커스 행): 재생 중 단어 카라오케 하이라이트 + 단어 클릭=그 단어부터 재생 + 의심 단어 인라인 빨강 밑줄. 빈 곳 클릭=편집.
- **cps 신호등**(타이밍 모드): 행마다 초록/주황/빨강 점.
- **가 크게**: 자막 글자·버튼 확대 토글 (고령 검수자).

## Recent Additions (2026-07-13 — v0.3.0, ADR-0009, CHG-20260713-006~007)

- **검수 모드 2개**: 에디터 상단 큰 탭 ① 내용 확인 / ② 타이밍. 기본값 상태 파생(ko 미완→내용), 잠금 없음. 내용 모드는 타이밍 UI 전부 숨김(시간=읽기전용 라벨) — 고령 검수자 기준 "볼 것만 보이게".
- **🙉 잘 안 들림(보류)**: `Segment.review_flag`("hold", additive 컬럼) — Alt+H/버튼 → 건너뛰고 뒤로, 확인 시 자동 해제, "남은 건 보류 N개뿐" + 0.75×+구간반복 재청취 프리셋. 보류는 완료를 막음(정직한 완료).
- **흘려듣기**(내용 모드 기본 ON): 재생 따라 자막 중앙 스크롤 + 입력칸 밖 Enter=확인(안 멈춤).
- **✨ 타이밍 자동 정리**: absorb→발화 스냅→36자/7초 초과 분할(최대 침묵 지점)→빠른 자막 끝 연장(cps 해법). reviewed 보존, Alt+Z 한 방 되돌리기(restore-rows 재사용). 실브라우저 844→1264→undo 844 검증.
- **타이밍 문제 큐**: ⏱ 다듬을 자막 N개 + "다음 문제 →" 순회.

## Recent (2026-07-13 — 폴더 rename asdf→jamak-ouroboros 완료)

- 사용자가 rename 스크립트 실행. 에이전트 검증: settings.json 훅 경로 ✓(스크립트가 넣은 UTF-8 BOM 제거), backup-cloud.cmd ✓, 워커 새 venv 경로로 가동 중 ✓, 워커 autostart ✓, Claude 메모리 이전 ✓. 추가 패치: deploy/start-serve.cmd·restart-serve.cmd(스크립트 누락분, 잉여 스크립트지만 경로 정정). 스케줄 태스크 `jamak-backup-cloud` 재등록 완료(사용자 실행, 경로 새로+매주 일 03:00 유지, Ready). rename 마무리 완전 종료.

## Recent Additions (2026-07-13 — v0.2.1, CHANGELOG CHG-20260713-001~005)

- **Undo v2 (동시편집 안전)**: 되돌리기가 작업 단위(변경된 행만 복원, `restore-rows` + idx 재정규화). 텍스트 편집도 undo 대상(셀 세션 coalesce). 전체-트랙 delete-재삽입 제거 → 한 검수자의 undo가 다른 검수자 작업을 못 지움. "여러 개 되돌아감/안 먹힘" 해결.
- **편집 반응성**: 변이 응답=영향 행 → 로컬 패치(전체 refetch 제거), 낙관적 저장(Enter 즉시 이동, PUT 백그라운드 세그먼트별 직렬 큐+실패 롤백), `React.memo(Row)`+안정 콜백+currentTime은 active/focused 행만 → 재생 틱당 1행 렌더.
- **담당자 검색**: 검색창 제목+담당자 매칭, `👤 내 담당만` 칩(localStorage 유지). PG 풀 10+20(50명 대비).
- **동시편집 정책**: 같은 세그먼트 동시 수정은 last-write-wins(구두 안내로 운용, 담당자 지정 관례가 1차 방어). 남은 트랙-와이드 작업(fork/unfork/tighten/repair/replace/안심확인)은 드문 관리 작업이라 유지.

## Recent Additions (2026-07-12 — 경로 B 후속 배치, v0.2.0)

경로 B 라이브(af693bd) 이후 사용자 실사용하며 요청한 기능·수정. 전부 커밋·배포·검증(대부분 실브라우저). 세부는 git 이력 + CHANGELOG_AGENT v0.2.0.

- **DB 요청 큐 + `jamak worker`**: 웹앱=요청만 기록(JobRequest), 로컬 워커가 하나씩 처리. 워커 시작 시 stuck `processing` 회수(Ctrl+C 복구). 파이프라인 heartbeat→진행% 표시(배너·카드), ⚠는 STT 정체만. 취소 ✕. `JAMAK_NO_PIPELINE` 폐기.
- **백업 자동화**: `jamak backup-cloud`(PG→gzip SQLite, pg_dump 불필요) + 주간 태스크→구글드라이브. 워커 로그온 자동시작.
- **DB Singapore 이전**: 앱·DB 동일 리전(한국 지연↓). 프록시 URL 불변→설정 변경 0. 앱 DATABASE_URL=internal(egress 0). 이전 전 백업, 데이터 온전(7 job/3722 seg).
- **.srt 카드 임포트**: 드래그/📄버튼→시간겹침 정렬→ko text_final+reviewed+흡수. 미리보기 모달(대상·매칭·낮으면 경고). **되돌리기**(`SrtBackup`→`↩ .srt 취소`). **한국어만**(한글비율 감지) + 비-srt 거부. STT/교정 파인튜닝 데이터 이관 수단.
- **담당 검수자**: `Job.assignee`, 카드 `👤 담당` 배지→스타일 모달(내이름 프리필). 누구나 클레임(비번+자유이름 모델).
- **번역 무-키 500 → 안내**: ANTHROPIC_API_KEY 없으면 503 깔끔 메시지(프론트 JSON파싱 크래시 제거). 클라우드에 키 추가하면 동작.
- **UI 폴리시**: 드롭다운 body portal(카드 transform/overflow 탈출), no-cache index.html(재배포 즉시 반영), 배포버전 배지(`/api/version`), 리스트 썸네일 16:9 무크롭·무빈공간, 그리드 footer 버튼 무클리핑+하단고정, 모달 텍스트드래그-닫힘 수정, 진행칩 패딩(전역 .progress 충돌), 처리중 숫자→펄스점.
- **비번 rotate**(공개이력 노출): 관리자 2312hky·검수자 1004hky(옛것 무효). 실값은 env/Railway만.

## Deployed 참고 (2026-07-12 — 경로 B 라이브)
- **URL**: https://hky-jamak.com (커스텀 apex, Cloudflare→Railway 회색구름, Railway TLS). Railway 프로젝트 dynamic-courage/production, `jamak-ouroboros`(Dockerfile)+Postgres(Singapore).
- **env**: DATABASE_URL(internal 참조), JAMAK_ADMIN_PASSWORD, JAMAK_PASSWORD, JAMAK_SECRET, ANTHROPIC_API_KEY. GitHub push→자동 재배포.
- **로컬 워커**: `setx DATABASE_URL <cloud>` 후 `uv run jamak worker`(시작프로그램 자동), 백업 `JAMAK_BACKUP_DIR`=구글드라이브.

### 경로 B 배포 이력 상세 (2026-07-12, 시간순 — 일부는 이후 상위 배치에서 갱신됨)

주의: 아래 `JAMAK_NO_PIPELINE`·"유령카드"·"순차 큐"는 이후 **DB 요청 큐+worker(CHG-20260712-002)로 대체**됨 — NO_PIPELINE 폐기, url박스는 관리자 상시 노출, 처리는 워커가 담당. 이력으로만 참고.

- **URL**: https://hky-jamak.com (커스텀 apex, Cloudflare CNAME→Railway, 회색구름/DNS only, Railway TLS). 백업 URL jamak-ouroboros-production.up.railway.app.
- **Railway**: 프로젝트 dynamic-courage/production, `jamak-ouroboros` 서비스(Dockerfile 빌드) + Postgres. env: DATABASE_URL(참조), JAMAK_ADMIN_PASSWORD, JAMAK_PASSWORD, JAMAK_SECRET. GitHub push→자동 재배포.
- **이관 완료**: migrate-to-cloud로 job 4·segment 1067·translation 257·glossary 547·llmcache 748·correction 28 + stt.json 4블롭. 클라우드에서 4영상 로드 확인.
- **인증 = 비번이 역할 결정**(이름은 표시용): 관리자비번→admin, 검수자비번→reviewer, 오답→거부. 검수자 추가 = 비번(1004hky)만 공유. 클라우드에서 역할판정 200/401·admin엔드포인트 차단 검증.
- **비번 rotate**(공개이력 노출 대응): 관리자 2312hky / 검수자 1004hky. 옛 hky2312/hky1004 무효.
- **주의**: 로컬 `jamak.hky-jamak.com` 터널(+8711 serve)은 로컬 SQLite(옛 데이터) 서빙 → 이제 잉여. 새 영상은 로컬에서 `$env:DATABASE_URL=<클라우드>; jamak run`으로 클라우드에 씀.
- **로컬 정리 완료**: cloudflared·8711 serve 종료, 시작프로그램 자동기동 해제(.disabled). `DATABASE_URL` setx 영구 설정(로컬 jamak 전부 클라우드 사용).
- **백업(경로 B)**: `jamak backup-cloud`(클라우드 PG→로컬 gzip SQLite 스냅샷, pg_dump 불필요, --keep 12). 주간 Windows 태스크 `jamak-backup-cloud`(일 03:00) → `JAMAK_BACKUP_DIR`(=구글드라이브 `G:\내 드라이브\01_TMP\HKY\jamak-backups`)로 오프사이트. 현재 스냅샷 322KB(텍스트 전용이라 수백 영상도 <1GB).
- **버그수정: 클라우드 "만들기" 유령카드**: 클라우드 컨테이너는 GPU/ffmpeg 없어 ingest에서 크래시(→Job행 전이라 카드 소멸). `JAMAK_NO_PIPELINE=1`(Railway에 설정 필요) → create/retranscribe 거부 + 프론트 url박스·재인식 숨김(`/api/me can_ingest`). repair-stt는 무GPU라 유지. 영상은 로컬(`jamak run` 또는 로컬 `jamak serve` 웹UI).
- **순차 큐 → DB 요청 큐로 전환(경로 B 완성)**: 인메모리 큐 폐기. 웹앱은 GPU 안 돌리고 `JobRequest`(DB)에 **요청만 기록**(관리자, 클라우드 포함 어디서든). 로컬 `jamak worker`가 pending 요청을 가져가 **하나씩** 처리(로컬 GPU) → 클라우드 DB로. 성공 시 요청行 삭제, 실패 시 error+note. `create_job`/`retranscribe`=요청 기록, `_running_ids`/`_queue_state`=JobRequest 조회, `/api/queue` DB기반. `JAMAK_NO_PIPELINE` 폐기(can_ingest=is_admin), url박스 관리자에게 복귀. 배너=처리중/대기(워커 실행 안내)/실패. 클라우드 실검증(요청 pending→queued, 정리 완료). 병렬은 VRAM OOM이라 미채택.

## Recent Additions (2026-07-12 — 경로 B: 클라우드 웹앱 + 전용 Postgres, ADR-0008)

경로 A(터널)는 PC 절전/재부팅 시 Error 1033으로 다운(실측). 검수자가 관리자 PC와 무관하게
접속하도록 웹앱을 Railway 상시 호스팅 + 데이터는 전용 Postgres 하나로 통일. 호스트=Railway
(사용자 결정, 코드는 `DATABASE_URL`만 바꾸면 이전 가능). **코드 완료, 사용자 셋업 대기.**

- **DB 엔진 분기** (`db.py`): `DATABASE_URL` 있으면 Postgres(psycopg, `postgres://`/`postgresql://` 자동 정규화, `pool_pre_ping`), 없으면 기존 SQLite. `_ensure_columns` dialect 인지(PG BOOLEAN DEFAULT false). **`DATABASE_URL` 미설정 = 로컬 100% 그대로.** `psycopg[binary]` 의존성 추가. 검증: SQLite 무변화·URL 정규화·SttBlob 생성.
- **stt.json → DB** (`SttBlob` 테이블 + `save/load_stt_blob`): 워드맵(`/words`)·타이밍다듬기(`/tighten`)가 로컬 파일 없이 클라우드에서 동작. writer=cli `run`(직접)·retranscribe(서브프로세스 경유). reader=`_load_stt`(블롭 우선, 파일 폴백). 검증: 임시 DB에서 파일 없이 블롭으로 워드맵 서빙.
- **`jamak migrate-to-cloud`**: 로컬 SQLite(+stt.json) → Postgres 1회 복사. 소스 읽기전용, PK id 보존, PG 시퀀스 리셋, 기존 job 있으면 중단(--force). 검증: PK 보존 복사·FK·blob 왕복(두 임시 SQLite). **PG 엔드투엔드는 로컬 Docker/PG 없어 `NOT VERIFIED` — Railway에서 실행됨.**
- **배포 파일**: `Dockerfile`(node 프론트 빌드 → python serve, base 의존성만·cuda 제외), `.dockerignore`(data/·secrets 제외), `railway.json`(헬스체크 `/api/me`). serve CMD `--host 0.0.0.0 --port $PORT --backup-hours 0`. serve 비-로컬 경고가 세션 인증(JAMAK_ADMINS 등)도 인식. 검증: `uv sync --frozen`(Docker와 동일 단계) 통과·frontend build 통과. **이미지 build는 Docker 없어 `NOT VERIFIED` — Railway 빌드.**
- **문서**: `deployment.md` 경로 B/Railway 스텝바이스텝(프로젝트·PG·env·이관·새영상·자동배포), ADR-0008 Accepted(0007 확장, supersede 아님), DECISION_INDEX 갱신.
- **이연**: 클라우드 retranscribe/repair는 GPU 없음 → 관리자 로컬 STT(문서화, 버튼 가드는 후속). per-(job,lang) 잠금 여전히 이연.

## Current Objective (이전)

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

## Recent Additions (2026-07-11 — 배포: 터널 방식 (ADR-0007))

사용자 결정: 터널 노출 + 검수자 몇 명. 1차 배포 = 로컬 구조 그대로, URL만 노출.
- **앱 옵션 인증**: `JAMAK_AUTH="user:pw,..."` 환경변수 → HTTP Basic 미들웨어(web/app.py). 미설정=무인증(로컬). 검증: no-creds/bad→401, good→200, 미설정→open.
- **`serve --host`** 옵션(기본 127.0.0.1; 비-로컬+JAMAK_AUTH 미설정 시 경고).
- **가이드**: `docs/agent/deployment.md` — Cloudflare Tunnel+Access(권장)/Tailscale/임시 데모, 운영(상시가동·백업·동시성·비밀).
- **ADR-0007** Accepted + DECISION_INDEX. 동시성 완전잠금·SQLite→PG는 이연(경로 B 트리거).

## Recent Additions (2026-07-11 — 몰입·편의 애니메이션/기능 벤치마킹 추가)

기존 모션 토큰(--dur*/--ease)·prefers-reduced-motion 시스템에 맞춰 추가:
- **재생 속도 컨트롤**(0.5/0.75/1/1.5×, `usePlayer.setRate`+세그먼트 버튼): 느리게 재생해 타이밍·발음 검수 쉽게. 전사툴 표준. 검증: 버튼 4개, 1×→1.5× 전환 e2e.
- **영상 위 자막 페이드인**: cue 바뀔 때마다 span을 cue id로 remount → `cc-in`(opacity+상승) 재생. YouTube/Netflix 캡션 관례. 검증: `animationName=cc-in`.
- **재생 중 현재 큐 숨쉬기**: `.strip-track.smooth .strip-seg.active`에 `strip-breathe` 부드러운 글로우. 미디어플레이어 now-playing. 검증: `animationName=strip-breathe`.
- **발화맵 카라오케**: 재생헤드가 지나는 단어 블록 `.wm-word.on` 하이라이트(밝기·높이). DAW/Descript. 코드검증(단어시각 있는 포커스 행에서 동작).
- 전부 `prefers-reduced-motion`에서 자동 무효(기존 가드). DB 무변경.

## Recent Additions (2026-07-11 — 타임라인 스트립 드래그 개선)

사용자 요청 3건, 전부 수정·검증:
- **드래그 부드럽게**: TimingStrip 경계 드래그가 pointermove마다 setState → 백로그 렌더로 툭툭 끊김. **rAF 코얼레싱**(프레임당 1회 갱신) + `.strip-handle` `touch-action:none`(브라우저 제스처 가로채기 차단) + `will-change`.
- **연동 밀기(hybrid edge-drag)**: 새 `POST /segments/{id}/edge-drag?which=`. 가장자리를 gap 안에선 자유 이동, 이웃 벽을 넘으면 이웃을 **밀어냄**(현재 셀 시작을 이전 셀 끝보다 당기면 이전 끝도 따라옴 / 끝을 다음 시작 너머로 밀면 다음 시작도 따라옴). 독립-리사이즈+연동을 하나로 통일 → contiguous 경계도 항상 조절됨. 검증: temp-DB 3케이스(이전밀기·다음밀기·gap자유), 라이브 마지막 셀 왕복(45.202→45.5→45.202, 검수상태 무손상).
- **contiguous 경계에서 스트립 조절 안 되던 버그**: (a) 옛 timeChange가 next.start에서 clamp→무동작, (b) 겹친 핸들 중 이웃 것 잡힘. → edge-drag가 clamp 대신 밀기 + 활성 셀 핸들 `z-index:4`(faint 2)로 위에. WordMap(오른쪽) 바는 기존대로.

## Recent Additions (2026-07-11 — 번역 서브시스템 3-에이전트 감사 수정 배치)

사용자 지시: 특성 다양화한 3 에이전트(정확성/UX/DB) 루프 감사 → 통과까지 번역 품질·편의·DB 최적화 완성. 1차 감사(wf_84ab4ada): 17 제기 → 12 확정. 전부 수정·검증:

- **데이터 손실(HIGH)**: `restore_segments`가 ko undo 시 **모든 언어 Translation 삭제**하던 코드 제거. 고아 Translation은 무해(get_translations는 live 세그먼트만 조인).
- **list_jobs fork-aware**: 포크된 언어는 `Segment(lang!=ko)`에서, 미포크는 Translation에서 집계(이미 포크된 언어 스킵). 두 shape 혼재해도 정확.
- **get_translations job-scoped**: 해당 job 세그먼트 id로 한정 + `lang` 필터.
- **fork 멱등성**: `uq_segment_job_lang_idx` 유니크 인덱스 + `IntegrityError` 가드 → 재포크 시 `created:0`. 검증: 1차 124, 2차 0.
- **LlmCache 중복 제거**: 한 런에서 동일 source_hash는 캐시 행 1개(`written` set).
- **번역 프롬프트 읽기속도/글자예산**: 세그먼트별 권장 글자수(≤N자, dur×17) 주입 + 매우 빡빡할 때(≤12자) 최단 표현 규칙. 검증: ja 6/6·en 6/6 예산 내(수정 전 en 3개 초과), 품질 유지("뭐라고?"→"What?", "혹시 아는가?"→"Know it?").
- **포크 에디터 한국어 원문 참조(HIGH UX)**: 번역 트랙 편집 시 각 Row에 읽기전용 `원문`(시간 겹침 매칭, idx 분기 대응) 표시. `koRefSegs` fetch + `.ko-ref`. 검증: en 포크 124행 전부 원문 표시.
- **카드 빠른 .srt 내보내기 언어**: 선택 언어 트랙으로 export(`exportUrl(vid,'best',lang)`), 라벨 `⬇ .srt (영어)`, exportable 게이팅.
- 검증 전부 **읽기전용/정리 완료**(테스트 포크 en 124 생성→삭제, DB 상속 상태 복원, 라이브 리뷰 데이터 무변경).

### 2차 감사(wf_1ca71219): 15 제기 → 8 확정. 전부 수정·검증:

- **[HIGH·내가 넣은 회귀] split 500**: 1차에 추가한 `uq_segment_job_lang_idx` 유니크 인덱스가 split의 오름차순 idx+=1 시프트와 충돌(SQLite 즉시 검사) → 모든 트랙 split 500. **인덱스 제거**로 근본 해결.
- **[HIGH·내가 넣은 회귀] repair_stt 500**: 같은 인덱스가 gap-fill의 idx=0 다중 삽입과 충돌. 인덱스 제거로 해결. fork 멱등성은 이미 app-level 존재검사(존재 시 created:0)로 보장 — 인덱스 불필요. `IntegrityError` 가드/import 제거.
- **[HIGH UX] 미번역 트랙 fork → 빈 자막 124줄**: fork 버튼을 번역 존재(`transMap>0`) 시에만 노출. 검증: en(번역O) 버튼 보임 / de(번역X) 숨김.
- **[MED] merge/delete가 검수완료 번역 영구삭제**: Translation 하드삭제 제거 → 고아로 남김(undo가 원본 id로 복구 시 재부착, restore/split 패턴 일치).
- **[MED] 사람 작성 번역 stale 미표시**: update_translation이 저장 시 `source_hash=_hash(ko)` 스탬프 → 이후 한국어 변경 시 stale 감지.
- **[LOW] export stage=whisper가 번역 캐시 오염**: 항상 best 한국어 텍스트로 번역(stage 무관).
- **[LOW] 찾기·바꾸기 카운트 트랙 전환 시 stale**: effect deps에 `lang` 추가.
- **[LOW] 중복 단일컬럼 인덱스**: `ix_segment_lang`/`ix_segment_idx` drop + 모델 index=True 제거(job_id만 유지).
- 검증: 라이브 DB 인덱스 확인(uq/lang/idx 제거, job_id만), **격리 temp-DB로 split·repair idx 연산 무충돌 재현**, fork 게이팅 양방향, 콘솔 0.

### 3차 감사(wf_cd3bc83e): 13 제기 → 8 확정(2차 8건은 전부 해소, 이건 더 깊은 신규건). 전부 수정·검증:

- **[HIGH 데이터손실] 재실행/재인식이 모든 언어 트랙 삭제** (`cli.py`): `delete(Segment).where(job_id)` lang 무필터 → forked en/ja 몰살. **`lang=='ko'` 스코프 + insert에 `lang='ko'` 명시**, `correct_job`도 ko 스코프. 검증: 격리 temp-DB에서 ko 재삽입돼도 en(reviewed) 4줄 생존.
- **[MED] 미번역 행 '확인'→ 보호된 빈 번역이 export 공백 + 재번역 안됨**: translate_segments 보호 필터에 `and t.text.strip()` 추가.
- **[MED] 모델이 idx 누락 → 조용한 공백 자막**: 누락 idx는 한국어 원문 폴백(캐시 안함→재export 시 재시도) + 콘솔 경고.
- **[MED·내 fork 게이팅 부작용] 번역 생성 직후 fork 버튼 안뜸**: TranslateReview `onGenerated` 콜백 → 부모 transMap 재fetch(transRefresh).
- **[MED] 비-fork 번역의 영상 위 오버레이 죽어있음**: koRefSegs 타이밍 기준으로 해당 언어 번역 오버레이(포크 없이 미리보기).
- **[MED] 트랙 전환 셀렉트가 export 푸터에 라벨 없이 묻힘**: `편집·내보낼 언어` 라벨 추가.
- **[LOW] 카드 언어 선택 무시하고 항상 ko로 열림**: `initialLang` prop 스레드. 검증: 카드 en 선택→에디터 en으로 열림.
- **[MED 이연] forked 트랙 timing-done 상태 없음**: Phase 4 기능 범위(Track.timing_done 배선·lang별 엔드포인트·칩) — 의도적 보류.
- 검증: 백엔드 compile OK, 프론트 build OK, 데이터손실 fix temp-DB 재현, initialLang·트랙라벨 UI 확인, 콘솔 0, DB 정리(포크 0).
### 4차 감사(wf_3666f164): 11 제기 → 5 확정(3차 8건 전부 해소). 전부 수정·검증:

- **[HIGH·내 round-2 부작용] 고아 Translation이 rowid 재사용으로 엉뚱한 세그먼트에 재부착**: Segment.id는 AUTOINCREMENT 없는 rowid라 삭제된 max id가 재사용됨 → 고아 번역이 무관한 자막에 붙어 잘못 export. **merge는 고아 남기지 않고 생존 세그먼트로 re-point**(언어 중복 시 생존측 우선, 병합됐으니 stale 표시), **delete는 번역 삭제**(생존자 없음). 검증: 격리 temp-DB에서 merge 후 dangling 0, delete 후 dangling 0.
- **[HIGH] fork가 번역 reviewed 상태 폐기 → 검수 완료 언어가 미검수로 회귀**: fork_track이 `reviewed=False` 하드코딩. **Translation.reviewed를 forked Segment.reviewed로 이관**. 검증: reviewed 번역 fork → forked 세그먼트 reviewed=True.
- **[MED] 공유 DB idx read-modify-write 레이스**: `busy_timeout=30s` 추가(동시 writer 대기·직렬화). 완전 직렬화(BEGIN IMMEDIATE per (job,lang))는 SQLite→PG 잠금 ADR로 이연. 검증: PRAGMA busy_timeout=30000.
- **[MED] 언어 전환 시 undo 스택 미초기화 → 타 트랙 id로 restore 500**: lang/videoId 변경 effect에서 `setUndoStack([])`+ref+focus 리셋. undo는 트랙별.
- 검증: compile OK, build OK, temp-DB 실코드경로(fork/merge/delete) 테스트 통과, busy_timeout 확인, 트랙 전환 콘솔 0, 라이브 DB 무변경(222 ko).
### 5차 감사(wf_a74b518b): 9 제기 → 5 확정(4차 5건 전부 해소). 전부 수정·검증:

- **[HIGH·rowid-reuse 마지막 구멍] restore_segments 고아 → 재부착 부패**: round-1에 restore의 Translation 삭제를 뺐던 것이 3번째 고아 소스. **undo가 버리는 id(스냅샷에 없는 현재 id)의 Translation만 삭제**(생존 id는 유지). merge/delete와 동일 보호. 검증: temp-DB에서 drop된 id 4의 번역 삭제, dangling 0. → merge·delete·restore·fork 4개 고아 소스 전부 폐쇄.
- **[MED] fork가 Translation 고아화(죽은 중복 + few-shot 오염)**: fork_track이 forked Segment 생성 후 원본 Translation 미삭제 → 중복 저장 + 편집 후에도 translation_examples가 옛 텍스트를 '사람 확정 예시'로 계속 제공. **fork 시 원본 Translation 삭제** + **translation_examples가 forked reviewed Segment도 시간겹침으로 수확**(언어 학습 유지). 검증: fork 후 Translation 0, examples가 forked에서 쌍 추출.
- **[MED] wrap_korean이 모든 언어 18자 CJK 규칙 → Latin 번역 줄바꿈 깨짐/클리핑**: `to_srt(lang=)` + `line_budget`(CJK 18 / Latin·Cyrillic 42). 검증: en \"It's recorded in the Bible\" 한 줄(전엔 2줄), ko 18 유지.
- **[MED·피로↓] 비-fork 번역 검수에 진행 히어로 없음(죽은 좌측 레일)**: TranslateReview에 진행바+%+`이어서 작업하기·남은 N개`(다음 미검수로 스크롤/포커스) 자체 히어로. 검증: en 히어로 렌더("영어 번역 검수 0/124", 남은 124).
- **[LOW] 키보드 Enter/이어서가 카드 언어 무시**: Enter 핸들러가 커서 카드의 `.card-lang select` 값 반영(클릭 경로와 일치).
- 검증: compile/build OK, temp-DB 실코드경로(restore/fork/examples) + 순수함수(wrap) 통과, 번역 히어로·콘솔0, 라이브 DB 무변경(222 ko·124 en·0 fork).
### 6차 감사(wf_31487380): 10 제기 → 7 확정(5차 5건 해소; 신규 3건은 내 5차 fix 부작용). 전부 수정·검증:

- **[HIGH·내 5차 부작용] fork 되돌리기 불가 + 툴팁 거짓말("비우면 됨") + 되돌리면 작업 파괴**: 5차에 fork가 Translation을 삭제하게 만든 뒤 "비우면 됨" 안내가 파괴적이 됨. **실제 unfork 엔드포인트 추가**(`POST /unfork-track`): forked Segment.text_final을 시간겹침으로 ko별 Translation 재구성(1:1 무손실·재분할 근사) + forked 세그먼트 삭제 + Track.forked=False. 프론트 `↩ 독립 편집 해제` 버튼(confirm) + 툴팁 정직화. 검증: temp-DB fork→편집→unfork 왕복, 편집("EDITED")·reviewed 복원, 세그먼트 0.
- **[HIGH] CLI 재실행이 ko Translation 고아화**: ko 세그먼트만 지우고 그 Translation은 안 지워 매 재실행마다 누적 + rowid 재사용 오부착. **ko 세그먼트 삭제 전 그 Translation부터 삭제**(app 패턴과 동일, CLI가 유일한 누락처).
- **[MED·내 5차 부작용] forked few-shot이 겹치는 ko 큐 전부 concat → 오정렬 예시**: 재분할 후 1 forked 큐가 2-3 ko 걸침. **near-1:1만 채택**(겹침 정확히 1개 or 한 ko가 forked 큐의 ≥80% 커버). 검증: 1:1 채택, 2개 걸침 스킵.
- **[MED] few-shot 최단줄 편향 + 용어사전 미주입**: 길이순 자르면 용어 든 긴 문장이 잘림. **glossary surface form 든 쌍 우선 + 나머지 길이-계층 샘플**.
- **[MED] ko 검수 회귀가 독립(forked) 트랙을 조용히 ko로 스냅백**: lang-lock이 forked 무시. **forked(=자체 세그먼트 존재) 예외 + statusMsg 설명**(상속 트랙만 게이팅).
- **[MED 이연] fork 후 기계 재번역 경로 없음** → unfork로 복구 경로 생김(unfork→재생성→refork). Phase 4 per-row 재번역은 이연.
- **[LOW 이연] forked 트랙 timing-done 없음** → Phase 4(Track.timing_done 배선).
- 검증: compile/build OK, temp-DB 실코드경로(unfork 왕복·forked few-shot 게이트) 통과, UI(정직 툴팁·히어로) 콘솔0, 라이브 DB 무변경(222 ko·124 en·source_hash 보존).
### 7차 감사(wf_f0da8e82): 10 제기 → 6 확정, **HIGH 0** (전부 MED/LOW — 심각도 하강=수렴 신호). 전부 수정·검증:

- **[MED·내 6차 부작용] unfork가 edited 플래그 유실 → 손편집 번역 재번역돼 사라짐**: unfork 재구성 Translation에 `edited=True` (protected 분기 태워 덮어쓰기 방지). 검증: fork→unfork 후 edited=True.
- **[MED] TranslateReview Enter가 "확인+다음" 라벨과 달리 안 넘어감**: `onSaveNext`→`saveNext`(저장+continueToNext, 방금 행 제외하고 다음 미검수로). 히어로 버튼도 유지.
- **[MED·내 6차 부작용] 키보드 Enter 카드 열기 셀렉터 오류(`.card-lang select`)**: `select.card-lang`로 수정(카드 언어 반영). 검증: 셀렉터 매치.
- **[MED] 카드 빠른내보내기가 부분번역이면 동기 1~2분 무피드백 행**: exportable을 `complete`만으로 제한(항상 캐시/즉시). 검증: en(미완) .srt 버튼 없음 / ko(완료) 있음.
- **[MED] list_jobs가 카운트하려고 전체 Translation(text blob) 로드**: `select(Translation.lang, Translation.reviewed)`로 2컬럼만 프로젝션(폴링마다 낭비 제거). 검증: langs 동일 출력.
- **[LOW] forked 트랙 stage=llm/whisper export 전부 공백**: forked면 stage 무시하고 text_final. 
- 검증: compile/build OK, temp-DB(unfork edited)·API(list_jobs projection)·UI(카드 export 게이팅·셀렉터)·콘솔0, 라이브 DB 무변경(222 ko·124 en·0 fork).
### 8차 감사(wf_72a3feab): 13 제기 → 11 확정(감사가 training/eval/split까지 범위 확장). 전부 수정·검증:

- **[HIGH] training.py STT 파인튜닝이 forked 비-ko 세그먼트(한국어 오디오+영어 텍스트) 페어링 = 학습 오염**: `Segment.lang=='ko'` 필터(training 2곳).
- **[HIGH] evaluate.py CER에 forked 세그먼트 섞임**: `Segment.lang=='ko'` 필터.
- **[MED] split.py 줄길이 예산이 비-ko 텍스트로 오염**: `Segment.lang=='ko'` 필터.
- **[MED] reviewed-only 번역이 한국어 바뀌어도 영구잠금**: protected를 `edited`만으로(reviewed는 source_hash 신선도). 검증: ko 그대로면 확정 유지, ko 바뀌면 재번역.
- **[MED·내 7차 부작용] unfork가 모든 행 edited=True → 미검수 기계번역이 few-shot 오염**: **Segment.edited 필드+마이그레이션** + update_segment가 forked 편집 시 set, unfork는 실제 edited만 이관. 검증: 기계텍스트 False, 손편집 True.
- **[MED] forked 트랙 독립성 미반영(fork/dropdown/timing 4건)**: list_jobs에 lang별 `forked`·`timing_done` 노출, 타이밍 체크박스·landing 칩을 forked에도(Track.timing_done 배선, 엔드포인트 lang-aware), 드롭다운 forked 잠금 예외. 검증: en Track.timing_done 저장.
- **[MED] fork 시 unsaved 편집 레이스**: runFork 전 blur+flush.
- **[LOW] fork가 stale reviewed 동결**: source_hash 불일치면 reviewed=False 씨딩.
- **[LOW] 드롭된 ix_segment_lang 풀스캔**: 복합 인덱스 `ix_segment_lang_reviewed` 생성 + 주석 정정.
- **[LOW 이연] forked Row 에디터 stale 신호**: forked Segment에 source_hash 저장 필요 = ADR-0006 명시 미래 항목, 이연.
- 검증: compile/build OK, 마이그레이션(segment.edited·인덱스) 라이브 확인, temp-DB 실코드경로 통과, UI 콘솔0, 라이브 DB 무변경(222 ko·124 en·0 fork·0 edited).
### 9차 감사(wf_a4af6f52): 12 제기 → 9 확정, **HIGH 0** (전부 MED/LOW). 사용자 종료 기준(HIGH 0) 충족 → 커밋+루프 종료. 이 중 값싼 5건 즉시 수정, 4건 다음 배치로 이연.

**9차 즉시 수정 (build+temp-DB 검증):**
- **[MED] forked 트랙 진행% 분모가 ko 세그 수**: `denom = l.forked ? l.translated : j.segments`(칩·진행바). 재분할된 forked가 >100% 안 뜸.
- **[MED] forked 트랙에서 발화맵/발화맞춤 사라짐**(재타이밍 도구인데): `words={isKo || forked ? words : []}`.
- **[LOW] 미번역 행 '확인' 체크 → 빈 유령 Translation 영구 잔존**: 빈 텍스트면 저장 안 하고 삭제. 검증: 유령 0.
- **[LOW] forked split/merge가 edited 미이관**: split 양쪽·merge 생존자에 edited 전파. 검증: 분할 양쪽 True.
- **[LOW] 재fork 시 Track.timing_done 안 리셋 + set_timing_done이 비-fork Track 조작**: fork 시 timing_done=False, set_timing_done은 forked 세그 없으면 400. 검증: ja 저장/en 400.

**9차 이연 (다음 배치, 전부 non-blocking):**
- [MED] list_jobs '완료'가 staleness 무시 → 카드 완료지만 export 시 stale 행 재번역(unreviewed). **worst harm(잘못된 텍스트 배포)은 8차 reviewed-lock으로 이미 제거**(재번역=올바른 기계번역). 남은 건 '완료' 배지 부정확 + 폴링 쿼리에 source_hash 재도입 필요.
- [MED] TranslateReview 리스트가 재생 큐 추적/하이라이트 안 함(dead `_active`).
- [LOW] fork_track 이중생성 TOCTOU 레이스 → SQLite→PG 잠금 ADR(이연된 동시성 작업).
- [LOW] 랜딩 카드가 잠긴 언어 선택 허용 → **8차 에디터 bounce+statusMsg로 완화됨**(카드 드롭다운 비활성화는 진행상황 뷰를 막아 트레이드오프).

## 수렴 선언 (2026-07-11, 번역 서브시스템 9라운드 적대 감사)

확정수 추이: **12→8→8→5→5→7→6→11→9**. HIGH: 라운드7=0, 라운드9=0. 총 **50+ 확정 버그 수정·검증**.
- **데이터 부패/손실 클래스 전멸**: rowid-reuse 5소스(merge/delete/restore/fork/CLI), ko-only 필터 6소스(feedback/export/cli/training/eval/split), 번역 캐시 오염, reviewed-lock, unfork edited.
- **내가 낸 회귀 3건도 감사가 잡아 수정**(유니크인덱스 split/repair 500, fork-delete-Translation 되돌리기, unfork over-edited).
- 남은 9차 이연 4건 = 전부 non-blocking(표시 정확도·동시성 ADR·UX 폴리시). 적대적 생성 감사라 라운드마다 신규 표면화하나 심각도 하강 확정 → 종료.

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

- **타이밍 검수 상태(텍스트와 별개 축) + seek 키 Alt→Ctrl** (2026-07-11): 커밋 ecdec6e 이후.
  - **워크플로 확정**(사용자): 링크 → ①한국어 텍스트 검수(0~100%) → ②타이밍 조정 → ③영어/일본어 등 번역. 텍스트 완료 ≠ 타이밍 완료.
  - **타이밍 상태**: `Job.timing_done` 컬럼(+마이그레이션), `POST /jobs/{id}/timing-done`, `/api/jobs`에 필드. 에디터 export 위에 `⏱ 타이밍 검수 완료` 토글. 랜딩 카드 배지: 완료=green `⏱ ✓`, 텍스트만 끝=amber `⏱ 타이밍`(필요), 그 전=muted. 검증: 엔드포인트·배지(LI3 amber owed / lFux green)·토글 렌더.
  - **seek 키 Alt→Ctrl**: `Ctrl+←/→` 3초, `Ctrl+Shift+←/→` 10초(편집칸 밖에서만 — 텍스트 내 word-jump 보존). **`Alt+←/→`는 preventDefault로 완전 차단**(크롬 뒤로/앞으로 사고 방지, 특히 재생 중 실수). 검증: Ctrl+→ seek ✓, Alt+→ 무동작(0)·내비 없음 ✓. Shift+Tab(-3s)도 유지.
  - 서버 재시작(8716b670). 다음 큰 과제: **다중 사용자·DB·배포**(세분화 작업 분배) — 별도 설계 필요.

- **번역 stale 감지 + 미리보기 언어** (2026-07-11):
  - **재번역은 변경분만**(이미 구현 확인, `translate.py`): `source_hash`로 한국어 바뀐 구간만 재번역, 안 바뀐 건 캐시 재사용, 사람이 수정/검수한 번역은 보호.
  - **갭 보완 — stale 플래그**: `GET /translations`에 `stale`(번역 생성 후 한국어가 바뀜) 추가. TranslateReview에서 `⚠️ 원문이 바뀜` 배지(amber 좌측선)로 표시 → 보호된(검수 완료) 번역이 원문 변경으로 낡았을 때도 사람이 알 수 있음. 검증: lFux en 124개 중 실제 stale 6개 배지.
  - **미리보기 오버레이 언어**: 번역 검수 중(lang≠ko) preview 모드면 영상 위 자막을 **해당 언어**로 표시(`transMap`, showPreview 토글 시 재fetch). 검증: 영어 오버레이 "It's recorded there..." ✓(한국어 아님). 서버 재시작 56c0c8f9.

- **랜딩 카드/통계/필터 파이프라인 개편** (2026-07-11, 프론트 only): 배지 난잡·불균형·시계 불명확 해결 + 새 단계(타이밍·언어) 반영.
  - **JobCard 추출 + 단일 스테이지 칩**: 여러 배지 대신 **색=파이프라인 단계** 칩 하나. `stageFor(j,lang)` → 처리중(teal)/텍스트 N/M(blue)/`⏱ 타이밍 조정 필요`(amber)/번역 검수(blue)/완료(green). job-head 균형(칩 좌, 드롭다운 우).
  - **카드별 언어 드롭다운**: 언어별 배지 폭발 대신 `한국어/영어/일본어…`(완료엔 ✓) 선택 → 그 언어 스테이지·진행바 표시. select stopPropagation로 카드 클릭과 분리. 검증: ko"✓완료"→en"번역됨·검수 전", 에디터 안 열림.
  - **상단 통계 확장**: 영상·**텍스트 완료·타이밍 완료·번역 완료**·검수한 자막·남은 자막(+처리중) + 전체 검수 링.
  - **상태 필터 파이프라인화**: 전체/텍스트 검수 중/타이밍 필요/번역 중/완료/처리 중.
  - **정렬 추가**: 타이밍 완료순. 검증: 스테이지·드롭다운·통계·필터·정렬 전부 렌더, 빌드 PASS, 콘솔 0.

- **[진행 중] 언어별 독립 자막 트랙 (ADR-0006, L3 대공사)** (2026-07-11): 사용자 결정 "전면 도입". 각 언어=1급 트랙(자기 분할/병합/타이밍), 에디터 전 언어 재사용. `docs/agent/plans/ACTIVE_PLAN.md`.
  - 커밋 965c9d9까지 푸시 완료(그 앞 배치들).
  - **Phase 1 (스키마) 완료**: `Segment.lang`("ko" 기본) + 마이그레이션. 검증: 기존 89 세그먼트 전부 lang="ko"로 보존.
  - **Phase 2 백엔드 (lazy-fork) 완료·검증**: DB 최적화 반영 — 번역은 기본 ko 상속(Translation, 복제 없음), 필요 시만 fork. `Track` 테이블, 이웃/idx-shift 쿼리 lang-aware(split·merge·delete·redistribute, 트랙 간 오염 방지), `get_segments?lang=`, `POST /fork-track?lang=`, list_jobs ko 전용. 검증: lFux en fork→124 세그먼트, en split→**ko 124·idx 온전**, 테스트 정리 완료. 앱 정상(ko 기본). 서버 f29c81f2.
  - ⚠️ fork 엔드포인트 UI 미노출(Phase 2b에서 ko 집계 엔드포인트 `lang=="ko"` 가드 후 노출).
  - **UI 수정**(이번 배치): 썸네일 완료 배지 제거(썸네일 가림 해결), ko 카드 스테이지 = **[자막][타이밍] 2축**(단일 완료 배지 대신), 번역 필터 "영어 있는 영상"(미완 포함).
  - **사용자 제기**(ACTIVE_PLAN 반영): 배포(SQLite→PG·GPU 워커·인증·잠금 → 별도 ADR), 언어별 파인튜닝(STT/교정=ko, 번역=lang별), DB 최적화(lazy-fork·source_hash·파생가능 데이터 미저장).
  - **Phase 2b (ko 격리 가드) 완료·검증** [커밋 383552c]: 모든 집계 엔드포인트 lang 스코프(fork 영속해도 ko 안전).
  - **Phase 3 (에디터 임의 트랙 편집) 완료·검증**: 언어 선택→`✂ fork`→그 언어 세그먼트를 **같은 Row 에디터로 독립 편집**(분할·병합·타이밍·미리보기 재사용, ko 전용 도구 숨김). `fetchSegments(videoId,lang)`, `forkTrack`, `koComplete` prop. 검증: lFux en→124 영어 행·ja→124 일본어 행, ko 불변·복귀 정상, 테스트 정리. 서버 b09d6830.
  - **눈에 보이는 핵심 기능 동작**: 이제 영어/일본어 등을 한국어와 다르게 분할·타이밍 편집 가능.
  - 다음: Phase 4(랜딩 언어 축 — 트랙별 상태 태그·필터, `Track.timing_done` 이관) → Phase 5(우로보로스 언어별) + 배포 ADR.

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
