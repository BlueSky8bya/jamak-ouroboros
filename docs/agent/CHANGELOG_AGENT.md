# Agent Change Log

## v0.8.4 — 2026-07-15 (번역 UX 3종 — 진행바·찾기바꾸기·뒤로가기 스택)

### CHG-20260715-024 — FEAT/UX — 사용자 요청 3건
Change:
(a) **동적 번역 진행바**: 정적 "번역 중... 1932/2231" 텍스트 → 진행바(부드러운 채움 + 움직이는 광택 애니메이션, reduced-motion 존중) + 퍼센트 + "남은 N개" + 카운트. 첫 생성·일괄 채우기 두 곳 모두.
(b) **번역 검수 찾기·바꾸기**: /replace 엔드포인트가 비포크 번역 트랙(Translation 행)도 처리(바꾼 행은 edited=True로 보호), 번역 검수 헤더에 ko와 동일한 찾기바꾸기 바(입력 멈추면 N곳 미리보기 → 모두 바꾸기 → 초록 완료 알림).
(c) **브라우저 뒤로가기 = 앱 페이지 스택**: 에디터 열 때 history.pushState, popstate로 목록↔에디터 복원 — 뒤로가기가 사이트 이탈이 아니라 이전 화면. ← 목록 버튼도 history 경유(스택 정합), 앞으로가기로 에디터 재진입 가능.
Validation: 실브라우저 E2E — back→목록, ←버튼→목록, forward→에디터 / 번역 찾기바꾸기 "Take care"→"Goodbye" 1곳 미리보기·적용·알림 / 진행바는 코드 경로 공유(기존 1563행 실전과 동일 루프).

## v0.8.3 — 2026-07-15 (빈·바뀐 번역 일괄 채우기 버튼)

### CHG-20260715-023 — FEAT — 번역 검수 상단 "한 번에 다 채우기"
Change: .srt 구조 교체 후 2시간 영상에 산발적으로 남는 빈/stale 번역 셀을 셀마다 "다시 번역" 누르던 것 → 번역 검수 상단에 경고 배너 "번역이 비었거나 원문이 바뀐 자막 N개" + **🔄 한 번에 다 채우기 (N개만 과금)** 버튼. 서버 배치 번역(fresh-skip)이 원래 빈 곳·바뀐 곳만 과금하므로 그대로 재사용 — 진행률 표시·배치 커밋·이중 실행 잠금 전부 상속. 채워지면 배너 자동 소멸.
Validation: 실브라우저 E2E — 3행(이어받기 1·빈 2) 상태에서 배너 "2개" → 클릭 → 실제 API로 빈 2행만 번역·이어받은 행 불변·배너 소멸.

## v0.8.2 — 2026-07-15 (침묵 구간 전수 방어 — 전역 진행 pill + 미리보기 가속)

### CHG-20260715-022 — FIX/UX — "진행 중인지 거부인지 모르는" 공백 제거 (사용자 원칙화)
Change: .srt 드롭 → 미리보기 모달까지도 무표시 공백(대형 파일에서 수십 초).
(a) **미리보기 가속**: 이어받기 매칭이 (기존 풀 × 새 큐) 정규화 반복 — 2231×1563에서 350만 회 → norm 텍스트 키 딕셔너리 직조회 O(1)로. 미리보기 즉답.
(b) **전역 진행 pill**: 화면 상단 고정 스피너+문구 컴포넌트 신설 — 네트워크를 기다리는 사용자 동작은 즉시 표시한다를 프로젝트 원칙으로. 연결: .srt 미리보기("읽고 미리보기 만드는 중"), 연습판 준비("처음 상태로 준비하는 중"), .srt 되돌리기. (기존 인라인 피드백 있는 곳은 그대로: 번역 진행률·statusMsg류·모달 busy들.)
Validation: TestClient 스모크 재통과. 실브라우저 — 연습 카드 클릭 시 pill 등장("연습판을 처음 상태로 준비하는 중...") 후 에디터 오픈을 MutationObserver로 캐치.

## v0.8.1 — 2026-07-15 (.srt 적용 침묵 실패 수정 — 속도·잠금·명시 피드백)

### CHG-20260715-021 — FIX — 2231행 .srt 적용이 조용히 실패하고 버튼만 풀리던 것
Change: 실사용 보고("적용 눌렀는데 버튼이 다시 활성화, 됐는지 모르겠음") — DB 확인 결과 미적용(1563 유지). 원인: v0.8.0 구현이 큐마다 flush → 클라우드 PG 왕복 수천 번 → 프록시 타임아웃 → 롤백, 프론트는 에러를 모달 뒤 상단 배너에 써서 안 보임.
(a) **속도**: 행 단위 삭제/삽입 → 벌크 delete 2문 + add 일괄 + flush 1회(executemany) — 수천 왕복이 수 회로.
(b) **이중 실행 잠금**: `_exclusive` 컨텍스트 매니저(예외 포함 전 경로 해제) — 재클릭 409 "이미 진행 중".
(c) **명시 피드백**: 적용 결과를 모달 '안'에 — 성공 초록 "✅ 자막 N개 구조로 교체, 번역 M개 이어받음"(+닫기), 실패 빨강 "❌ … 저장된 것 없음, 재시도 안전" + 다시 시도 버튼. 진행 중 라벨에 "큰 파일은 몇 초".
(d) **스윕**: 같은 패턴(모달 열린 채 상단 배너에만 에러) 전수 점검 — 담당 지정 모달도 실패를 모달 안에 표시하도록 수정. 나머지 긴 작업(번역 진행률·자동정리·복구·학습·맞춤법·내보내기·다시 인식)은 기존에 인라인 피드백 확인.
Validation: TestClient 스모크 재통과(교체·이어받기·undo). 실 2231행 적용은 사용자 재시도로 확인 예정.

## v0.8.0 — 2026-07-15 (.srt 임포트 = 구조 교체 + 번역 이어받기)

### CHG-20260715-020 — FEAT — .srt가 구조까지 갈아엎고, 번역은 이어받는다
Change: (사용자 확정: "임포트하는 .srt는 이미 검수 완료본 — 기존 기계 분할 무시하고 구조까지 교체, 안 바뀐 부분 번역은 재사용") import-srt 재설계:
(a) **구조 교체**: 기존 ko 행 전체 삭제 → .srt 큐(분할·타이밍·텍스트, reviewed=True)로 재생성. 기계 참조(whisper/llm/유튜브)는 시간 겹침으로 이어 붙여 이관 — absorb·학습쌍이 새 구조에서도 초안 대비 diff 가능.
(b) **번역 이어받기**: (정규화 텍스트 동일 + 시작시각 ±20초) 큐는 기존 번역을 새 행으로 복사(source_hash 갱신, reviewed/edited 보존) — 동일 문장 반복은 시간으로 구분. 바뀐 큐만 비고 남아 기존 증분 번역(fresh-skip 배치·클러스터 재번역)이 그 부분+문맥만 과금. 2시간 영상 전체 재번역 제거.
(c) **undo v2**: 스냅샷에 행 전체+번역 저장(v2 스키마), 되돌리기 = 현재 구조 삭제 후 재삽입(id 리매핑). v1 스냅샷도 계속 복원 가능.
(d) 미리보기 문구: "N개 구조로 통째 교체 + 번역 M개 이어받기".
Validation: TestClient 스모크 — 4행+en 4건에 3큐 srt(1 동일·1 수정·2 병합): preview{srt_count 3, carry 1} → apply 후 행 3·병합행 whisper 참조 "w2…w3" 결합·en 1건만 생존(동일 문장) → undo 후 행 4·번역 4 완전 복원.

### (감사) API 비용 누수 전수 점검 — 잔여 경로 이상 없음
교정(LlmCache+프롬프트 캐시), 번역(행 캐시+fresh-skip 배치+클러스터), 맞춤법(줄 캐시), 용어 채굴(청크+캐시), STT(로컬·stt.json 캐시) 전부 재실행 시 증분 과금 확인. 가장 큰 누수였던 ".srt 재임포트 → 전량 stale → 전량 재번역"이 (b)로 봉합. 잔여 소액: retranslate_span 단건 재시도 무캐시(클릭당 1콜 — 의도된 UX, 방치).

## v0.7.0 — 2026-07-14 (튜토리얼 탭 분리 + 입장 시 무조건 리셋)

### CHG-20260714-019 — FEAT — 튜토리얼은 전용 탭에서, 열 때마다 처음 상태 (사용자 확정)
Change: (a) **입장 = 리셋**: 연습 영상을 열 때 practiceSession(reset=true) — 본인이 아무리 고쳐도 나갔다 들어오면 항상 깨끗한 처음 상태(클론 재복제, 세그 id 교체라 늦은 저장도 무효). 세션 중 "↺ 처음부터 다시"는 유지. (b) **랜딩 상단 탭 분리**: 📋 작업 영상 / 🎓 튜토리얼 연습 — 연습 영상은 강연 카드·통계·필터·이어서 검수에서 완전 제외(workJobs), 튜토리얼 탭에 코스 1~6 카드(완료 ✓, 미바인딩 코스는 "준비 중", 카드 클릭 = 리셋된 클론에서 해당 코스 자동 시작) + 자유 연습 목록. 관리자용 코스 지정 select·연습 해제 버튼은 튜토리얼 탭 카드 아래로 이동.
Validation: 실브라우저 E2E — 작업 탭에 연습 카드 0(강연만), 튜토리얼 탭 코스 카드 6(바인딩 1·준비 중 5)+관리 select, 카드 클릭→클론+투어 자동 시작, **행 오염 후 재입장→text_final ''·reviewed false (리셋 확인)**. 통계·이어서 검수도 연습 제외.

## v0.6.7 — 2026-07-14 (유튜브 꼬리 자막 유령 행 차단)

### CHG-20260714-018 — FIX — 침묵 구간마다 직전 문장 꼬리가 중복 행으로 들어오던 것
Change: 사용자가 연습 영상 검수 중 발견("왜 이렇게 중복 셀이 많지?"). 원인: 유튜브 자동자막은 문장이 끝난 뒤 쉬는 구간에도 그 문장 꼬리를 계속 표시 → whisper가 조용한 갭을 유튜브 자막으로 채우는 `youtube_gap_rows`가 그 꼬리를 성실히 행으로 수입("…먹었습니다." 다음에 "먹었습니다." 행). 연습 영상은 문장마다 침묵이라 대량 발생, 실영상에서도 간헐 발생(CER 분석의 '구조 편집 소음' 정체 — 검수자들이 손으로 지우던 것). 수정: 갭 후보의 정규화 텍스트가 직전 행 텍스트에 포함되면 스킵(에코 가드) — 파이프라인·수동 복구(/repair) 두 경로 모두. 트레이드오프: 침묵 직후 똑같은 문장을 진짜로 반복한 경우도 스킵되나, 이 행들은 원래 flagged 추정치라 허용. 기존 연습 기준본 6개에서 유령 행 59개 일괄 제거(whisper 빈칸+flagged+미검수+직전 행에 포함된 것만) + idx 재정렬.
Validation: 유닛 스모크 — 꼬리 에코 스킵·진짜 놓친 문장 유지. 기준본 정리 후 행 수: 40→30/48→33/41→32/29→22/41→30/30→23. 다음 워커 처리 영상부터 파이프라인 자체가 차단.

## v0.6.6 — 2026-07-14 (모바일 HCI 재배치 — 데스크톱 압축 탈피)

### CHG-20260714-017 — FEAT/UX — 중복 제거·바텀 시트·헤더 수리 (사용자 실기기 피드백)
Change: 실폰 스크린샷 피드백("모바일 특화가 아니라 어색") 반영, ≤700px에서:
(a) **중복 컨트롤 제거**: 상단 재생 줄(구간처음·3초·재생·3초)은 하단 바와 중복이라 숨김 — 이동/재생은 하단 바 전담, **배속 줄만 유지**(자주 씀 + 튜토리얼이 위치 언급). 구간처음은 ⚙ 시트로.
(b) **⚙ 재생 설정 바텀 시트**: 체크박스 2줄(구간반복·편집 시작 시 멈춤·자동 따라가기·미리보기)은 데스크톱 문법 → 모바일 표준 바텀 시트로 이동(같은 상태 공유, 행 높이 50px).
(c) **랜딩 헤더 수리**: 역할/계정 칩이 폭 부족으로 낱글자 세로 쌓임 → nowrap+wrap, 배포 SHA 태그 숨김(검수자에게 개발 정보), 타이틀 34→24px.
(d) 모드 탭 슬림(2줄 카드→46px).
주의: 코스2·3 투어가 가리키는 토글이 모바일에선 시트 안에 있음 — 투어는 PC 전제(연습 영상 안내도 PC 위치 기준), 모바일 투어는 missingHint로 안내됨.
Validation: 실브라우저 375×812 — 재생 줄·토글 숨김, 배속 유지, ⚙→시트 오픈(바닥 밀착·safe-area)·토글 상태 동기·닫힘, 모드 탭 52px, 랜딩 배포 태그 숨김·h1 24px. 1280px — ⚙ 숨김·재생 줄/토글 복원·그리드 회귀 없음. 실기기 재확인은 User.

## v0.6.5 — 2026-07-14 (모바일 버튼 줄바꿈 전수 수정)

### CHG-20260714-016 — FIX — 좁은 화면에서 버튼 라벨이 두 줄로 꺾이던 곳 전부
Change: 텍스트 노드 단위 줄 수 측정 스크립트로 랜딩·에디터(내용/타이밍)·찾기바꾸기·투어 메뉴·QC 모달 전수 스캔. 실제 줄바꿈: 하단 바 "⟲ 3초"/"▶ 재생"(공백에서 꺾임), QC 모달 액션 3개(닫기·맞춤법 검사·자막 받기). 수정: `.mb-btn` white-space nowrap+패딩·폰트 조정, `.srt-actions` flex-wrap(버튼 안이 아니라 줄이 꺾이게)+버튼 nowrap, 도구·찾기·보류·이어듣기·드롭다운 라벨 일괄 nowrap, dd-val ellipsis. 모바일 블록 한정 — 데스크톱 불변.
Validation: 375×812 + 320×700 재스캔 — 실제 줄바꿈 0건(모드탭·코스 카드 등 의도된 다단 제외), 하단 바 오버플로 없음, 가로 스크롤 없음.

## v0.6.4 — 2026-07-14 (용어사전 재구축 — DB diff 채굴)

### CHG-20260714-015 — FEAT — 검수 DB에서 실제 오인식 쌍까지 캐는 glossary-mine --from-db
Change: (사용자 지시: "검수 완료 DB에는 실제 발언 시간+텍스트가 있으니 파일보다 정확") 파일 코퍼스 빈도 추출만 하던 마이너에 DB 소스 추가 — 검수 완료 비연습 세그먼트의 text_final(빈도 후보) + **text_whisper와의 토큰 정렬 diff로 (오인식→정답) 쌍 추출**(1:1 치환만, 2회 이상 반복만). diff 쌍은 큐레이션 첫 청크에 "실제 오인식 기록"으로 주입 → variants 정확도 급상승. 구 빈도 노이즈 후보 482개는 사용자 승인 하에 일괄 삭제.
Validation: 실행 — 후보 761 + diff 쌍 28, Claude 큐레이션 $0.03, 승인 65→**99개**. variants에 실측 오인식 반영(수가성←수로보가네 — CER 분석에서 잡았던 그 단어, 허경영←허경형, 하늘궁←하늘공, 축지법←축제법 등). 다음 jamak run부터 hotwords+교정 프롬프트 자동 반영.

## v0.6.3 — 2026-07-14 (모바일 터치 편집)

### CHG-20260714-014 — FEAT — 키보드 단축키의 터치 대체 (간략 편집)
Change: 메인은 PC, 모바일은 간략 수정 가능 원칙. (a) 내용 모드 포커스 행에 **모바일 전용 구조 버튼** ✂ 나누기(커서 위치)·⇣ 합치기·✕ 지우기 — Ctrl+Enter/Ctrl+Shift+Enter/Alt+Delete의 터치판, 기존 onStructure 핸들러 재사용. 데스크톱 내용 모드는 ADR-0009대로 계속 숨김(CSS 미디어 쿼리로만 노출). (b) 하단 바에 **↶ 되돌리기**(Alt+Z 대체, 스택 비면 비활성). (c) 확인 체크박스 22px·보류 버튼 42px 터치 타겟.
Validation: 실브라우저 375×812 — 포커스 행에 버튼 3개(42px), 나누기 탭→6행→7행, 바의 ↶ 활성화→탭→6행 원복, undo 스택 비면 비활성. 1280px 데스크톱 — 전부 숨김·그리드 레이아웃 회귀 없음.

## v0.6.2 — 2026-07-14 (CER 계기판 수리 + 교정 큐 이탈 규칙)

### CHG-20260714-012 — FIX — 교정이 이웃 세그먼트 문장을 끌어와 큐를 늘리던 것
Change: CER 회귀 분석에서 발견 — Claude 교정이 문맥 세그먼트의 문장을 현재 큐 text에 이어붙임(예: 뒤 큐의 "알겠죠?" 추가, 앞 문장 전체 복사) → 자막이 발화 구간을 벗어나 검수자가 도로 잘라내야 했음. correct.py 규칙 9 추가: "각 세그먼트의 text는 그 세그먼트에서 들린 말만, 문맥은 판단 근거일 뿐". (대명사 풀어쓰기 회귀는 규칙 8이 7/10에 이미 차단 — 문제 영상은 7/9 처리분.)
Validation: 프롬프트 규칙 추가 — 효과는 다음 영상 처리분의 matched CER로 관찰(NOT VERIFIED yet).

### CHG-20260714-013 — FIX — CER 지표 오염 분리 (src 표시 + 매칭 CER)
Change: 지표가 (a) .srt 임포트(사람 최종본이 다른 분할·출처 — 58%가 모델 탓처럼 보임) (b) 검수자의 구조 편집(에코·중복 삭제)에 오염. `jamak eval`에 src 컬럼(app/srt — SrtBackup 존재로 판정)과 **매칭 CER**(길이비 0.5~2.0 세그먼트만 — 오인식 신호 분리) 추가. 기존 컬럼·정규화 불변(비교 가능성, RISK_PROFILE).
Validation: 실행 — lFuxxOlgl5Y 전량 26%→매칭 13.5%(98/124행), srt 임포트 영상 명시 표시. 구조 편집 소음과 오인식이 분리됨.

## v0.6.1 — 2026-07-14 (모바일 친화 + PWA)

### CHG-20260714-011 — FEAT — 모바일 레이아웃·하단 액션 바·PWA 설치
Change: 리서치 근거(고령 터치 타겟 ≥48px·수전증 여유, iOS 16px 미만 입력 자동 확대, 스티키 플레이어가 이탈 감소, 하단 고정 바가 고령자 표준 내비, PWA 매니페스트 요건) 반영.
(a) **모바일 레이아웃**(≤700px): `.left`를 `display:contents`로 해체해 세로 흐름 재배치(JSX 무변경) — 영상 **스티키 상단**(16:9, ≤34dvh) → 재생 줄 → 자막 목록 → 진행 카드 → 도구 → 내보내기. 단축키 패널·orientation 줄 숨김(터치 무의미). 터치 타겟: 재생 버튼 48px, 모드 탭 56px, 내보내기 52px. 입력칸 16px 강제(!important — 상태별 규칙에 밀리지 않게), 큰 글씨 모드 20px.
(b) **하단 액션 바**(내용 모드·ko/포크 트랙): ⟲3초 / ▶재생 / 🙉 / **✔ 맞아요**(=입력칸 밖 Enter의 터치 대체 — confirmActive 재사용, 흘려듣기 루프를 엄지 영역에). fixed + safe-area inset, 자막 목록에 하단 여백.
(c) **PWA**: manifest.webmanifest(standalone, ko, theme #1b2a45) + 아이콘 192/512/maskable/apple-touch(Pillow 생성 — 남색 타일+"자"+자막 바 모티프) + theme-color/viewport-fit=cover. 홈 화면 추가 시 앱처럼 열림. SW는 의도적 생략(index no-cache 정책과 충돌 위험, 오프라인 불필요).
Validation: 실브라우저 375×812 — 하단 바 4버튼 노출·바닥 고정, 풀스크롤 후 영상 sticky top 0(214px), 마지막 행이 바에 안 가림, 가로 스크롤 0, 포커스된 입력칸 16px, 랜딩 카드 풀폭, manifest/theme-color 태그 확인. 데스크톱 뷰 회귀 없음(미디어 쿼리 격리). 실기기(iOS/Android) 확인은 User 위임.

## v0.6.0 — 2026-07-14 (P4: 사용자별 연습 클론 + 코스 바인딩 + 결함 주입)

### CHG-20260714-010 — FEAT — 튜토리얼 연습이 사용자별 병렬 격리 샌드박스로
Change: (PLAN v4 §4 구현, 사용자 확정 요구 "A·B·C 동시에 각자 처음부터")
(a) **클론 세션**(`src/jamak/practice.py`): 연습 기준 Job을 열면 브라우저별 UUID(`jamak.practiceKey`)로 세그먼트+SttBlob 깊은 복사 — video_id=`base~sha256(key)[:10]`이라 기존 엔드포인트 전부 무수정 동작, 플레이어만 접미사 제거. 편집·reset은 자기 복제본에만; 기준 Job 불변. "↺ 처음부터 다시" 버튼 = 재복제(세그 id 공간 교체라 늦은 PUT 자연 무효). 가드: 비연습/클론의 클론/번역 트랙 존재 시 403·400, TTL 7일 워커 청소(clone_of+practice 이중 조건 없인 삭제 불가 — BR-DATA-001).
(b) **코스 바인딩**: `Job.practice_course` + 부분 UNIQUE 인덱스(코스당 활성 1개, 동시 지정 레이스는 IntegrityError), 관리자 카드에 코스 선택기, `GET /api/tutorials`. 코스 해제해도 practice는 영구 유지.
(c) **결정적 결함 주입**(bind 시 1회): P5에서 hotwords가 대본 미끼를 전부 이겨서(깻잎·축지법·뭉치 전부 정확 인식) 서버가 기준 Job에 주입 — basic: 깻잎→깨입·밤나무→밥나무·축지법→축제법·공중부양→공중부용 각 1행, fast: 뭉치→몽치 2행, timing: 침묵 1.5s+ 앞 행 end 연장. 모든 클론이 같은 결함 상속 → 전 사용자 동일 시작 상태.
(d) **코스 딥링크**: 코스 메뉴에서 전용 영상이 따로면 "전용 연습 영상에서 열려요 →" — App이 클론 부트스트랩 후 전환, 세그먼트 로드 뒤 해당 코스 자동 시작(React 상태 일회성 핸드오프+nonce, localStorage 아님). Editor `key={videoId}` 재마운트로 상태 누수 차단.
(e) **FIX**: YT 위젯이 잘못된/차단된 영상에서 동기 throw → 에디터 전체 백지. try/catch+onError로 "재생만 없음"으로 강등(자막 목록은 동작).
Validation: scratch 스모크(격리·reset fresh id·가드·부분 UNIQUE·TTL·주입 멱등) + 실브라우저 E2E(사용자 α 편집 → β 클론·기준 모두 pristine / ↺ 버튼 원복 / norm→코스1 딥링크 → 클론+투어 자동 시작 / 목록에 클론 안 뜸) + 실 DB 사본 ALTER 마이그레이션(4 job/1067 seg 무손실 + 새 컬럼). 접두 절단 충돌 버그를 E2E에서 잡아 해시로 수정. 미검증(다음 배치): seek 앵커, tourEvent 성공 후 발생, 버블 중앙 폴백, 힌트 보기.

## v0.5.2 — 2026-07-14 (긴 영상 번역 502 수정 — 배치 번역)

### CHG-20260714-009 — FIX — 전체 번역이 2시간 영상에서 프록시 502로 전멸하던 것
Change: `/api/jobs/{vid}/translate`가 동기 단일 요청으로 전 세그먼트를 번역(2h≈1563세그=Claude 직렬 ~26회, 수십 분) → Railway 프록시 타임아웃 502, 커밋은 마지막 한 번이라 전부 유실. 수정: (a) `translate_segments`에 `limit` — 미캐시 세그먼트를 그만큼만 번역·커밋. (b) 엔드포인트 `?batch=` 파라미터 + 응답에 `remaining/done`. (c) 프론트가 60개(모델 호출 1회)씩 루프 돌며 진행률 표시("번역 만드는 중... 540/1563"), 중간 실패해도 완료된 배치는 저장돼 이어서 재시도 가능. (d) (video,lang) 인메모리 잠금 — 더블클릭/재시도 중복 실행 409 (단일 인스턴스 전제 주석).
Validation: scratch SQLite+실제 API 스모크 — limit=2 3행: 1회차 2행, 2회차 캐시 2+신규 1=3행, 3회차 전량 캐시(수렴). 프론트 빌드 클린. 실전 검증은 p_9m8r1bZSM(1563세그) 배치 번역 실행으로.

## v0.5.1 — 2026-07-14 (대본 보강: 위치 안내 + 권장 순서, 4코스 재렌더)

### CHG-20260714-008 — DOCS/FEAT — 내레이션에 컨트롤 화면 위치 안내 (사용자 피드백)
Change: 처음 보는 사람이 버튼을 못 찾는다는 피드백 반영, 실제 레이아웃 확인 후 대본 수정(76→77대사): 배속("영상 바로 아래 재생 단추 옆")·구간반복("배속 아래 체크 칸 줄")·안심 확인/자동 정리/복구/학습("왼쪽 아래 도구 줄")·찾기바꾸기("자막 목록 맨 위, 탭 바로 아래")·멈춤/따라가기("체크 칸 줄")·이어서("영상 왼쪽 아래")·미리보기("체크 칸 줄 맨 오른쪽")·자막 받기("왼쪽 맨 아래")·타임라인("영상 바로 아래 막대"). 추가: Shift+Tab 3초 뒤(연습2 #5), "타이밍은 글자 검수를 끝낸 뒤 권장 — 같이 하면 버겁다"(연습5 #1), 미리보기 중 타이밍 탭이면 타임라인 손잡이로 바로 조절(연습6 #3 신규 — 코드 확인: TimingStrip은 !textMode 조건이라 미리보기 토글과 공존). EXPECTED_TOTAL 77, PLAN/MAPPING 정합.
Validation: parse OK 77, 코스 2·3·5·6 재렌더+ffprobe 통과(변경 대사 17개만 재합성 — 캐시 키 검증), 코스 1·4 불변.

## v0.5.0 — 2026-07-14 (P2 렌더 파이프라인 — 연습 영상 6개 산출)

### CHG-20260714-007 — FEAT — tools/tutorial-video: 대본→TTS→PCM→Remotion mp4
Change: PLAN v3 §2 구현. `parse_scripts.py`(표 파싱, file:line 에러, 76대사 계약 assert) / `tts.py`(edge-tts 7.2.8 고정, 캐시 키=파이프라인 버전+voice+rate+웅얼 필터+텍스트, 재시도 3회 backoff, atomic 쓰기, voice preflight; 웅얼=클린 합성 후 volume 0.35+lowpass 700) / `audio.py`(전 mp3→48kHz mono s16 PCM, 무음은 정확 샘플 수, 큐 타이밍=샘플 오프셋, 머리/꼬리 1.5s) / `build.py`(cp949 안전 로그, 길이 공식·침묵 RMS assert, public/ 복사, --render+ffprobe 검사) / Remotion `practice-1~6`(calculateMetadata가 실제 오디오에서 길이 도출, 화면=배지·진행점·펄스·아이콘만 — 발화 문장 비표시). 목소리 = **InJoon**(사용자가 SunHi/InJoon/Hyunsu 샘플 청취 후 확정).
Validation: 76대사 파싱 OK, mp4 6개(87~135초) ffprobe 통과(1920×1080/30fps/오디오/길이 wav±1프레임), 멱등 재실행 합성 호출 0회, 렌더 프레임 육안 확인(말하는 중/조용한 구간 상태 전환). 웅얼 가청성은 User 귀 확인 대기(NOT VERIFIED by agent).

## v0.4.3 — 2026-07-14 (Codex 감사 반영: practice 누수 차단 + 투어 완료 semantics)

### CHG-20260714-005 — FIX — practice Job이 모든 우로보로스 학습·평가 경로에서 제외
Change: 연습용(practice) Job의 "검수된" 세그먼트는 튜토리얼 드릴이지 감독 데이터가 아닌데, 차단이 `absorb_job`에만 있었음(Codex 감사 BLOCKER). 추가 차단 4곳: `learned_line_budget`(줄 길이 학습 — Job join+필터), `translation_examples`(번역 few-shot — 비포크·포크 쿼리 둘 다), `training.py` STT·교정 학습 export 2종(`if job.practice: continue`), `evaluate.py` CER 평가(합성 TTS가 지표 왜곡). PLAN.md §4.5에 회귀 테스트 항목 추가.
Validation: scratch SQLite 스모크 — 긴 문장 60행 practice Job이 budget/CER에 안 들어옴(budget (18,24) 유지), practice=False로 뒤집으면 (25,34)로 상승(필터가 정확히 practice 플래그 기준임 확인), "SMOKE OK".

### CHG-20260714-006 — FIX — 투어 "그만 볼래요"가 완료로 기록되던 것 분리
Change: `endTour()`가 이탈·완주 구분 없이 완료 플래그를 써서 중도 포기 코스도 메뉴에 ✓ 표시(Codex 감사). `endTour(markDone)`으로 분리 — onExit=false(플래그 안 씀), onFinish=true. 건너뛰기로 마지막 단계 도달 후 완료는 유지(의식적 완주 간주). 부수: 코스6 📚 학습 버블에 "연습 영상은 0개가 정상" 문구(absorb no-op을 고장으로 오해 방지).
Validation: 프론트 빌드 클린(tsc+vite). 실브라우저 회귀는 다음 배포 확인에 포함.

### (문서) PLAN.md v3 — Codex 감사 2라운드 15 finding 처리
2차 감사(1차 처리의 재검수)에서 해소 확인 11건 + 신규 15건 → §10 처리표. 수용: practice 지정 시점을 등록 직후로(리허설 중 학습 누수 — 진짜 구멍), 앵커 {t, focus}(seek는 focused row를 안 바꿈), PracticeSnapshot 생명주기(source_rev·재인식 무효화·결함 주입 멱등), reset 경합 가드(저장 큐 flush+undo 초기화+ko 단일 트랙 계약), practice_course 부분 UNIQUE 인덱스, Editor key={videoId} 재마운트+플레이어 ready 게이트, tourEvent 서버 변이 전수 분류, 웅얼 빈 행 predicate, Remotion staticFile/public 계약(P2 착수 조건), 캐시 키 확장+"합성 호출 0회" 기준(P2 착수 조건), 자식 프로세스 cp949 캡처. 부분 수용: 동시 연습은 lease 대신 소프트 가드(10분 편집 감지 409)+운영 규칙, 확대 검증은 버블 중앙 폴백 코드로 갈음. 기각: LlmCache practice namespace(캐시=메모이제이션, 무해 — §6-11 명시).

### (문서) PLAN.md v2 — Codex 감사 20개 finding 처리
docs/tutorial/PLAN.md 전면 개정: PCM 샘플 오프셋 렌더 계약, Remotion `practice-N` id+calculateMetadata, edge-tts 재현성(버전 고정·캐시·재시도·atomic), 스냅샷·초기화(`PracticeSnapshot`+practice-reset — 다중 사용자 연습 재료 보호), 코스5 결정적 결함 주입, timing.json 기반 seek 앵커, tourEvent 성공 후 발생(P4), YouTube 단일 장애점(체크리스트+onError 게이트), 미끼별 predicate 표(화면 초안 기준, hotwords 충돌 경고), 완료 기준 측정화, 76대사 정정, README supersede. §9에 finding별 수용/부분 수용/기각 기록.

## v0.4.2 — 2026-07-14 (투어 커버리지 100% + 연습 영상 파이프라인 계획)

### CHG-20260714-004 — FEAT/DOCS — 미커버 단축키 3종 투어 편입 + PLAN.md
Change: (a) 투어 단계 3개 추가 — 코스1 **글씨 크게**(`bigtype` 이벤트), 코스2 **Alt+↑↓ 자막 이동**(`nav`), 코스3 **Alt+Shift+↑↓ 미검수 이동 / 이어서 버튼**(`nav-unreviewed`, 두 경로 모두 훅). 대본(연습1/2/3)에 유도 문장 각 1줄 추가, MAPPING.md 갱신 — 주요 단축키·기능 커버리지 100%(의도적 생략: WordMap·◀▶ 미세조정=코스5 타임라인으로 갈음, 번역/관리자 기능=대상 아님). (b) `docs/tutorial/PLAN.md` — 연습 영상 파이프라인 전체 실행 계획(외부 감사용 자기완결 문서): P2 렌더(edge-tts+Remotion, 파일 트리·스타일→rate 매핑·타이밍 실측 원칙·화면에 문장 비표시 원칙) / P3 업로드(사용자) / P4 앱 연결(`Job.practice_course` additive + 코스 메뉴 전용 영상 딥링크 설계) / P5 리허설(미끼 적중 검증 필수) + 리스크 8종·완료 기준·검증 주체 표.
Validation: 실브라우저 — 코스1 글씨 크게 단계(버튼 클릭으로 진행), 코스2 nav(Alt+↓), 코스3 nav-unreviewed(Alt+Shift+↓) 전부 실키로 통과, 콘솔 에러 0.

## v0.4.1 — 2026-07-14 (클러스터 재번역 + 잘림·저장 500 수정)

### CHG-20260714-003 — FEAT/FIX — 다시 번역이 주변의 이어진 stale·빈 셀까지 문맥 번역
Change: (a) **클러스터 재번역**: 번역 후 한국어를 재분할/재타이밍하면 그 언저리 셀들이 stale/빈칸이 되는데, `POST /retranslate`가 클릭한 셀 + **연속된 stale·빈 이웃**(각 방향 최대 6, 사람이 편집한(edited) 행과 fresh 행에서 확장 중단)을 묶어 **한 번의 문맥 호출**(`retranslate_span` — 앞뒤 4행 컨텍스트, `retranslate_one` 대체)로 재번역 → `{updated:[...]}` 반환, 프론트가 여러 행 패치. 빈 셀에도 "🔄 다시 번역" 버튼("번역이 비어 있어요 — 주변 문맥으로 채울 수 있어요"). (b) **FIX: 번역 수동 편집 저장 500** — `update_translation`의 source_hash 스탬프 브랜치가 `_hash` import 누락으로 NameError → 텍스트가 바뀌는 모든 수동 저장·빈칸 삭제가 500이던 실버그(이전 세션 유입), local import로 수정. (c) **FIX: 재생 토글줄 잘림** — `.pc-settings`에 flex-wrap 없어 좁은 패널에서 🔁구간반복·미리보기가 좌우로 잘림 → wrap+nowrap 토글.
Validation: 합성 5셀(fresh|stale|빈칸|stale|edited) 실 API 스모크 — 클릭(빈칸)→클러스터 정확히 stale+빈 3셀, 문장 흐름 이어짐, fresh·edited 불가침, hash=현재 ko·미검수. 실브라우저 E2E — 편집 저장 200(기존 500), 빈 셀 배너+버튼→클릭→문맥 채움, 토글 4개 경계 안(overflow 0), 콘솔 에러 0.

## v0.4.0 — 2026-07-14 (따라하기 6코스 + 연습용 영상)

### CHG-20260714-002 — FEAT — 따라하기 레슨 6코스 (전 기능) + 🎓 연습용 영상
Change: 단일 투어 → **코스 6개**(각 단계는 실제 동작해야 진행 — `tourEvent(이름)` 훅 ~25곳): 1️⃣기본기(재생·Enter·고치기·🙉·undo) 2️⃣재생 다루기(Tab·Shift+Tab·Ctrl+←→·Ctrl+Shift+←→ 10초·Ctrl+\·0.75×·🔁 Alt+R) 3️⃣빠르게 훑기(Alt+S 멈춤 끄기 언제·자동 따라가기 언제 끄나·✅안심 일괄·🔎 Alt+B) 4️⃣나누기·합치기(Ctrl+Enter·Ctrl+Shift+Enter·각각 undo로 원복 — 연습이 데이터 안 남김) 5️⃣타이밍(②탭·✨자동 정리·문제 큐·Alt+[·Alt+]·Alt+\·타임라인 드래그·무음 다듬기) 6️⃣마무리(Alt+P 미리보기·복구·채우기·📚학습·자막 받기 점검표). 🎓 버튼 → **코스 메뉴**(완료 ✓ 표시, localStorage `jamak.tour.<id>`, 구 tourDone은 기본기 완료로 인정). 첫 방문 자동 시작 = 기본기만.
**연습용 영상**: `Job.practice` additive 컬럼 + 관리자 카드 토글(🎓 연습용) + 썸네일 배지 + 에디터 배너("마음껏 만져도 돼요"). **absorb_job이 연습 영상에선 no-op** — 연습 편집이 교정쌍/용어사전을 오염 못 함. 코스 메뉴가 연습용 영상 권장 문구 표시.
Validation: 마이그레이션+absorb 차단 스모크(practice 컬럼 추가, absorb 0 반환), 실브라우저 — 연습 토글→배지→배너, 메뉴 6코스+완료 표시, 코스2 전 단계 실키 순회(Tab/Shift+Tab/Ctrl+→/Ctrl+Shift+←/Ctrl+\/0.75×/Alt+R 정확 진행), 코스3·4 전 단계(나누기→undo→합치기→undo 실 데이터 원복), 코스5·6 순회(자동정리·문제큐·Alt+[]\·미리보기·복구·학습·점검표), 콘솔 에러 0.

## v0.3.5 — 2026-07-14 (따라하기 투어 — 실습형 온보딩)

### CHG-20260714-001 — FEAT — 에디터 따라하기 투어 (실제 동작해야 진행)
Change: `Tour.tsx` 신규 — 실제 에디터를 어둡게 하고 **컨트롤 하나만 스포트라이트**(dim 패널 4개 + 파란 링, 구멍 안만 클릭 가능, 대상 rect 250ms 폴링·스크롤 추적), 큰 말풍선(진행 점·건너뛰기·그만 볼래요). **6단계, 각 단계는 실제 그 동작을 해야 진행**: ①▶재생 클릭 ②Enter 확인(save reviewed 훅) ③자막 글 클릭(onOpenRow 훅 — 프로그램적 포커스와 구분) ④🙉(hold 훅) ⑤Alt+Z/↶(undoLast 훅) ⑥완료 카드. 첫 에디터 방문 시 자동 1회(`jamak.tourDone`, 내용 모드·자막 있는 트랙만), 좌상단 **🎓 따라하기**로 언제든 재시작. 📖 사용법(참고서)과 상보 — 이건 실습편. 의존성 0(직접 구현).
Validation: 실브라우저 E2E — 자동 시작, 실제 액션으로 ①→⑥ 전 단계 진행(재생 클릭→확인→글 클릭→🙉→↶→완료), 완료/그만 모두 기록 저장, 재방문 시 자동 안 뜸, 🎓 재시작 동작, 콘솔 에러 0.

## v0.3.4 — 2026-07-13 (어르신 사용법 화면 + 워커 자동시작 무창)

### CHG-20260713-012 — FEAT — 앱 내 사용법 튜토리얼 화면 (어르신 검수자용)
Change: `Guide.tsx` 신규 — 전체화면 오버레이 사용법. 큰 글씨(본문 17px/제목 24px), 쉬운 말, **시나리오별("이럴 때→이렇게")** 8개 카드(맞음=Enter, 틀림=클릭후고침, 안들림=🙉, 카라오케, 낱말클릭 재생, Alt+Z, 글씨크게, 타이밍은 나중에), 큰 키캡, "물 흐르듯 요령", 단축키표 6행, 루프 CSS 데모 2개(확인=초록체크, 카라오케=낱말 하이라이트 이동, prefers-reduced-motion 존중). 랜딩 헤더 "📖 사용법" 버튼 + **첫 방문 자동 1회 오픈**(localStorage `jamak.guideSeen`). 백엔드 무관, 순수 프레젠테이션.
Validation: 실브라우저(scratch) — 첫 방문 자동 오픈, 8시나리오/26키캡/6단축키/데모2 렌더, 큰 버튼 닫기→기록 저장→헤더 버튼 재오픈, 본문 17px·가로 넘침 0·카라오케 애니 작동·콘솔 에러 0.

### CHG-20260713-013 — CHORE — 워커 로그온 자동시작 무창(VBScript) + 재시작 루프
Change: Startup 폴더 `.cmd`(부팅 때 콘솔 번쩍임) → **VBScript**(`WScript.Shell.Run …,0`=완전 숨김)로 교체. `run-worker.ps1`에 **자동 재시작 루프**(죽으면 10초 후 재기동) + **중복 방지 가드**(GPU 하나) + **DATABASE_URL 레지스트리 폴백** + UTF-8 BOM(PS5.1 한글 파싱). 배너 워커 명령도 `uv run --project "<dir>" jamak worker`(홈에서 실행돼도 됨). `scripts/jamak-worker-autostart.vbs` 템플릿 커밋(라이브 사본은 Startup 폴더, 옛 .cmd는 .disabled).
Validation: .vbs로 부팅과 동일 실행 → 워커 숨김 기동(보이는 창 0)·PID 안정(크래시 루프 아님)·루프 런처 생존. 명령은 홈 디렉토리에서 `jamak --help` 확인.

## v0.3.3 — 2026-07-13 (셀 단위 재번역 + UX 정리)

### CHG-20260713-010 — FEAT — stale 번역 셀만 문맥 재번역 (`POST /retranslate`)
Change: 원문(한국어)이 바뀌어 stale 표시된 번역 행에 **🔄 다시 번역** 버튼. `pipeline/translate.py`에 `retranslate_one(ko, ctx_before, ctx_after, lang, budget)`(앞뒤 각 4행 문맥 + 글자 예산, 1 API 호출). 엔드포인트가 그 셀만 재번역해 Translation 덮어씀(source_hash=현재 ko, reviewed·edited=False → stale 해제, 재확인 대상). 전체 트랙 재번역 없음. 키 없으면 503. TranslateReview가 응답으로 해당 행 로컬 패치.
Validation: 합성 3행 실 API 스모크(문맥의 암세포·양산 반영, stale→fresh, hash 갱신, 단일 행) + 실브라우저 E2E(ko 편집→stale 배지→🔄 클릭→바뀐 원문 맞춰 재번역·배지 소멸, 콘솔 에러 0).

### CHG-20260713-011 — FEAT/UX — 형식 토글 · 워커 명령 복사 · 라벨 정리
Change: (a) 랜딩 "형식" 드롭다운(전체/롱폼/쇼츠) → **세그먼트 토글**(유튜브는 롱폼·쇼츠뿐이라 토글이 더 빠름, view-toggle 스타일 공유). (b) 큐 배너의 워커 안내에 `uv run jamak worker` **복사 버튼**(WorkerCmd, navigator.clipboard, "복사됨 ✓" 피드백) — 자동시작 실패 시 사용자가 바로 복사. (c) 에디터 "가 크게/가 보통" → **"글씨 크게/글씨 보통"**(의미 명확).
Validation: 실브라우저 — 형식 토글 3버튼 선택·localStorage 유지, bigtype 라벨 "글씨 …", 빌드 클린.

## v0.3.2 — 2026-07-13 (내보내기 전 QC + AI 맞춤법)

### CHG-20260713-009 — FEAT — 내보내기 전 점검 모달 (규칙 QC 0원 + 선택적 AI 맞춤법)
Change: "자막 받기" → 점검 모달 먼저. **QC**(`GET /qc`, 순수 규칙·API 0원): 미확인/보류/빈 자막/너무 빠름(>17cps)/두 줄 초과(>36자)/지속시간 이상/중복 공백 — 카테고리별 카운트+"보기→"(해당 자막으로 점프). 문제 있어도 "자막 받기"로 그대로 진행 가능(차단 아님, 권고). **맞춤법**(`POST /spellcheck`, ko 전용, 모달 안 옵트인 버튼): `pipeline/spellcheck.py` — Claude(`JAMAK_SPELL_MODEL`, 기본 CLAUDE_MODEL)로 맞춤법·띄어쓰기·오타만 제안(구어체·사투리·내용 절대 불변 프롬프트 규칙), `LlmCache kind="spell"`로 줄 단위 캐시(재검사는 수정된 줄만 과금), 키 없으면 503 안내. 제안은 diff 체크리스트(기본 전체 선택)→"선택 N곳 적용"→기존 세그먼트 PUT 경로(낙관적+직렬 큐)+**일괄 1 undo 스텝**(Alt+Z 전체 원복). 상속(비포크) 번역 뷰는 기존처럼 바로 내보냄.
Validation: scratch DB — QC 844건 분류(보류 1·빠름 4·초과 295 등) 일치, 합성 3줄 실 API 스모크(오타 "업는→없는" 잡음, 사투리 "마이 왔네" 보존, 정상 줄 무변경, 2회차 완전 캐시 sent=0), 실브라우저 E2E(모달·점프·받기·맞춤법 diff→적용→DB 반영→Alt+Z 원복, 콘솔 에러 0).
Rollback: 해당 커밋 revert (LlmCache "spell" 행은 잔존해도 무해).

## v0.3.1 — 2026-07-13 (벤치마킹 UX 배치: 읽기 뷰·신호등·큰 글씨)

### CHG-20260713-008 — FEAT — 읽기 뷰(카라오케·단어 클릭 재생·의심 단어 인라인) + cps 신호등 + 큰 글씨
Change: 벤치마킹(Descript/Otter/Auphonic/Ooona/고령자 UI 리서치) 반영. **읽기 뷰**: 내용 모드의 비포커스 행이 textarea 대신 단어 span — ① 재생 중 지금 말하는 단어 하이라이트(whisper 단어 타임스탬프→편집된 텍스트 비례 매핑, active 행만 틱 갱신이라 렌더 비용 불변), ② 단어 클릭=그 단어부터 재생(무단어 행은 글자 비율 폴백), ③ suspect 단어 인라인 빨강 물결 밑줄(별도 경고줄 교차 확인 제거), 빈 곳 클릭=편집 진입(textarea 스왑+자동 포커스 effect — 부모 setTimeout(0)보다 늦게 마운트되는 문제 대응). 확인(reviewed) 행은 기존 접힘 유지. **cps 신호등**(타이밍 모드): 행마다 초록(≤14)/주황(≤17)/빨강(>17) 점 — 숫자 대신 색(Ooona/EZTitles 관례). **가 크게**: 좌상단 토글(localStorage) — 자막 글자 15→19px, 체크박스·보류 버튼·탭 확대(고령자 터치 타겟 리서치).
Validation: 실브라우저(scratch SQLite) — 읽기 뷰 844행, 의심 단어 1,134개 인라인, 단어 클릭≠편집 진입, 빈 곳 클릭→textarea+포커스, 큰 글씨 15→19px 토글, 타이밍 모드 신호등 838초록/2주황/4빨강 + 읽기 뷰 0(전부 textarea 복귀), 콘솔 에러 0. 카라오케 하이라이트 실재생은 YT iframe 미지원으로 DELEGATED.
Rollback: 해당 커밋 revert.

## v0.3.0 — 2026-07-13 (검수 모드 분리 + 자동 타이밍, ADR-0009)

### CHG-20260713-007 — FEAT — 에디터 내용/타이밍 모드 + 잘 안 들림 보류 + 흘려듣기
Change: 에디터에 큰 탭 2개(① 내용 확인 / ② 타이밍) — 기본값은 상태 파생(ko 미완→내용), 잠금 없음. **내용 모드**: TimingStrip·시간 필드·nudge·WordMap·타이밍 도구·구조 버튼·⏩빠름 배지·무음다듬기·타이밍완료 전부 숨김(시간은 읽기전용 라벨). **🙉 잘 안 들림**(Alt+H): `Segment.review_flag`("hold") 토글 → 다음 미검수·미보류로 이동, 확인 시 서버가 자동 해제, 완료는 막힘("남은 건 보류 N개뿐" 표시), 히어로의 "보류 N개 다시 듣기"가 0.75×+구간반복 프리셋으로 재방문. nextWorkTarget이 보류를 뒤로 미룸. **흘려듣기**(내용 모드, 기본 ON): active 자막 중앙 따라 스크롤(preview 센터링 재사용) + 입력칸 밖 Enter=지금 나온 자막 확인(재생 유지). **타이밍 모드**: 문제 자막(⏩빠름·0.35s↓·7s↑) 카운트 + "다음 문제 →" 순회 바. DB는 additive 1컬럼(`review_flag VARCHAR DEFAULT ''`, SQLite/PG 겸용), restore-rows 스냅샷에도 포함(undo가 플래그 안 지움).
Validation: scratch SQLite(합성 스모크 + 실 스키마 복사본 1067행 마이그레이션 무손실) + 실브라우저(내용 모드 렌더/보류 플로우/탭 전환/타이밍 모드 복귀). 흘려듣기 Enter 실동작·실재생은 인앱 브라우저가 YT iframe 못 열어 DELEGATED(사용자 확인).
Rollback: 해당 커밋 revert (컬럼은 additive라 잔존해도 무해).

### CHG-20260713-006 — FEAT — ✨ 타이밍 자동 정리 (`POST /auto-timing`)
Change: `pipeline/retime.py`(순수 계획 함수) + 엔드포인트 — **absorb 먼저**(분할이 machine 텍스트를 왼쪽 조각에만 남겨 교정쌍 유실 방지) → 발화 스냅(/tighten 규칙) → 36자/7초 초과 자막을 내부 최대 침묵에서 재귀 분할(시간비→공백 스냅 텍스트 분할) → 너무 빠른(>17cps) 자막 끝을 뒤 침묵으로 연장(다음 발화 -0.08s·+2s 한도; 분할은 cps를 못 낮추므로 연장이 정답). **분할돼도 reviewed·review_flag 보존**(내용은 동일, 잘리기만 — ko_complete 후퇴 방지). Translation은 원(왼쪽) 행 유지+stale 처리, idx (start,end,id)순 재정규화. 응답에 before-rows+created_ids → 에디터가 pushOpUndo 1스텝으로 **Alt+Z 전체 되돌리기**(restore-rows 재사용, 서버측 스냅샷 테이블 없음). 권한=로그인 사용자(tighten과 일관)+확인 모달.
Validation: 합성 스모크 20/20(스냅·분할 글자 무손실·reviewed 보존·번역 생존·무겹침·idx dense·undo 원복·재실행) + 실브라우저(844→1264 분할 372·스냅 441, ↶로 844 복귀·보류 유지).
Rollback: auto-timing/retime 커밋 revert.

## v0.2.1 — 2026-07-13 (동시편집 안전 + 편집 반응성)

### CHG-20260713-005 — HARNESS — 프로토콜 260710→260712 마이그레이션 (MODE D)
Change: `agent-harness.yaml` schema 1.1 + BLOCKING 규칙 5개 등록(BR-DOCS-001 MACHINE=doc-drift 훅, 나머지 4개 UNENFORCED+manual gate). DoD에 Verification Capability Boundary(DIRECT/DELEGATED 표 — YT 재생·GPU 파이프라인은 DELEGATED). `verify_harness.py` 신설(문서·경로·링크·규칙 무결성). AGENTS.md에 Decision Write-Through / WH-CHANGE 표준 주석(신규 변경부터) / Continuity-Break Handoff 트리거. `HARNESS_MIGRATION.md`에 감사·격차·미변경 기록.
Validation: `uv run python scripts/agent-harness/verify_harness.py` → OK.
Rollback: 이 커밋 revert (기존 문서 무손실).

### CHG-20260713-004 — FIX — 행 ▶ 버튼이 재생까지 (seek-only였음)
Change: 큐별 ▶가 위치 이동만 해서 정지 중엔 죽은 버튼처럼 보임 → seek+play (replayCurrent와 동일 패턴). 배포 b8cd8b2.
Validation: 빌드·클릭 배선 OK; 실재생은 인앱 브라우저가 YT iframe을 못 열어 DELEGATED(사용자 확인 대기).
Rollback: 해당 커밋 revert.

### CHG-20260713-001 — FIX/FEAT — Undo v2: 작업 단위 되돌리기 (동시편집 안전)
Change: 에디터 undo를 전체-트랙 스냅샷 복원(→ 트랙 전부 DELETE-재삽입, 동시 검수자 작업 파괴 + "여러 개 한 번에 되돌아감")에서 **작업 단위**로 전환. `UndoEntry{upsert(변경 전 행들), deleteIds(작업이 만든 행)}` + 신규 `POST /segments/restore-rows`(해당 행만 upsert/삭제 + idx (start,end,id)순 재정규화 — `_next/_previous_segment`가 dense idx 요구). **텍스트 편집도 undo 등록**(같은 셀 연속 타이핑은 세션 단위 coalesce — "안 먹힘" 증상 해결). 구 `restore` 전체-트랙 엔드포인트 제거. 라벨 Ctrl+Z 오표기→Alt+Z 정정.
Validation: API 13항목(텍스트/split/merge/delete/boundary 각 undo + idx dense) + 실브라우저(텍스트 Alt+Z 원복, split→undo 10→9행) — 격리 temp DB.
Rollback: restore-rows/UndoEntry 관련 revert.

### CHG-20260713-002 — PERF/UX — 편집 뚝딱거림 제거 (낙관적 UI + 행 단위 렌더)
Change: (a) 변이 엔드포인트가 **영향받은 행을 반환**(split/merge/delete/boundary-prev·next/edge-drag/redistribute) → 프론트는 로컬 패치, 전체-트랙 refetch 제거(작업당 RTT 2→1, 800행 재렌더 제거). (b) **낙관적 저장**: 텍스트/Enter확정/시간 nudge/발화맞춤이 즉시 화면 반영+포커스 이동, PUT은 세그먼트별 직렬 큐로 백그라운드(실패 시 롤백+에러). (c) `React.memo(Row)` + ref-트램폴린 안정 콜백 + `currentTime`은 active/focused 행에만 전달 → 재생 중 틱당 1행만 재렌더. (d) 전역 keydown 리스너 1회 등록(기존: 틱마다 재등록). undo 전 대기 큐 flush로 순서 보장.
Validation: 실브라우저 — Enter 즉시 다음 이동(<80ms)+낙관 reviewed, split refetch 0회, 콘솔 에러 0.
Rollback: 해당 web/app.py 커밋 revert.

### CHG-20260713-003 — FEAT — 담당자 검색 + "내 담당만" / PG 풀 확장
Change: 랜딩 검색이 제목+담당자 매칭(placeholder "제목·담당자 검색"). `👤 내 담당만` 토글 칩(me.name 기준, localStorage 유지, 초기화 포함). PG 엔진 풀 `pool_size=10, max_overflow=20`(검수자 ≤50명 대비).
Validation: 실브라우저 — 담당 지정 후 칩 필터 1개·이름 검색 매칭·리로드 유지.
Rollback: mine-chip/pool 커밋 revert.

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
