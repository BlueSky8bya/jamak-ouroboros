# 튜토리얼 연습 영상 파이프라인 — 전체 실행 계획 v3 (Codex 2차 검수 반영)

Status: v3 — Codex 감사 2라운드(2026-07-14) 반영. §9(1차)·§10(2차)에 finding별 처리 기록.
P2 착수 조건(오디오 public 계약·캐시 기준) 확정 — P2 착수 가능.
Date: 2026-07-14
Owner: User(승인·업로드) + Agent(구현)
Related: ADR-0009, docs/tutorial/README.md, docs/tutorial/MAPPING.md,
CHANGELOG CHG-20260714-001~006

이 문서는 저장소를 모르는 검토자도 감사할 수 있게 자기완결적으로 쓴다.
이 문서가 README.md의 렌더 화면 서술(자막 카드 표시)을 **supersede**한다 —
화면에 발화 문장을 표시하지 않는다(§2.5).

---

## 0. 배경 — 이미 구현돼 있는 것 (이 계획의 전제)

jamak-ouroboros = 유튜브 강연 자막 파이프라인(로컬 whisper STT → Claude 교정 →
사람 검수 웹앱 → .srt). 검수자는 고령자 다수(전체 ≤50명). 검수 웹앱(React +
FastAPI, Railway 배포, 로컬 GPU 워커가 영상 처리)에 다음이 이미 있다:

- **따라하기 투어 6코스** (`src/jamak/web/frontend/src/Editor.tsx`의 `COURSES`,
  `Tour.tsx`): 실제 UI를 어둡게 하고 컨트롤 하나만 스포트라이트, 각 단계는
  실제 그 동작이 일어나야 진행(`tourEvent(name)` 훅 ~28곳). 코스별 완료 플래그
  `localStorage jamak.tour.<id>`. 중도 이탈("그만 볼래요")은 완료로 기록하지
  않는다(CHG-20260714-006). 첫 에디터 방문 시 기본기 코스 자동 시작.
- **연습용 영상 플래그** (`Job.practice`, additive 컬럼): 관리자가 카드에서
  🎓 연습용 지정. 연습 Job은 **모든** 우로보로스 학습·평가 경로에서 제외된다:
  `absorb_job`(교정쌍/용어), `learned_line_budget`(줄 길이 학습),
  `translation_examples`(번역 few-shot), STT/교정 학습 export, CER 평가
  (CHG-20260714-005). 에디터에 연습용 배너 표시.
- **대본 6개** (`docs/tutorial/scripts/연습N-*.md`): 코스별 전용 영상 대본,
  총 **77대사** (2026-07-14 사용자 피드백 반영: 컨트롤의 화면 위치 안내,
  Shift+Tab 3초 뒤, "타이밍은 글자 검수 후" 권장, 미리보기 중 타임라인
  조절 안내). 표(대사/스타일/뒤 쉼)가 사람 검토 문서이자 렌더 파이프라인의
  기계 입력. 각 코스가 요구하는 조작이 필요해지도록 연습 재료를 일부러 심음
  (속사포→되감기·0.75×, 5초 침묵→건너뛰기, 초장문→나누기, 토막말→합치기,
  웅얼→🙉, "뭉치" 반복→찾기·바꾸기). 매핑 검증표는 MAPPING.md.
- **플레이어 제약**: 앱은 YouTube IFrame 플레이어를 쓴다(`usePlayer.ts`).
  → 연습 영상도 **유튜브에 올라가 있어야** 한다. mp4 직접 재생 경로는 없고
  만들 계획도 없다(파이프라인 전체가 video_id 기준).

## 0.1 목표

코스 1~6 각각에 전용 연습 영상을 붙여서, 어르신 검수자가
"연습 영상 열기 → 파란 불 따라 하기"만으로 전 기능을 손으로 익히게 한다.

비목표(스코프 밖): 화면 녹화형 강의 영상, 앱 내 mp4 플레이어, 유튜브 업로드
자동화(OAuth 필요 — 사용자 수동), 다국어 튜토리얼, 사용자별 완전 격리
연습 세션(§4.4의 스냅샷·초기화로 갈음 — §9 B1 참고).

---

## 1. 전체 흐름 (5단계)

```
P1 대본 확정(완료) ─→ P2 렌더 파이프라인(TTS+Remotion→mp4 6개)
   ─→ P3 유튜브 업로드(사용자) ─→ P4 앱 연결(코스↔영상 바인딩+스냅샷)
   ─→ P5 리허설·미끼 조정 ─→ 롤아웃
```

| 단계 | 담당 | 산출물 | 예상 규모 |
|---|---|---|---|
| P1 | 완료 | scripts/연습1~6.md (총 77대사) | — |
| P2 | Agent | `tools/tutorial-video/` 렌더 프로젝트 + mp4 6개 | 코드 ~500줄 |
| P3 | User | 유튜브 영상 6개 (미등록 공개) + video_id 목록 | 10분 |
| P4 | Agent | 바인딩 + 스냅샷·초기화 + seek 앵커 + 핸드오프 | 코드 ~300줄 |
| P5 | User+Agent | 미끼별 predicate 검사 → 대본 조정 → 재렌더 (최대 2회) | 반나절 |

---

## 2. P2 — 렌더 파이프라인 상세

### 2.1 위치·구조

```
tools/tutorial-video/
├── package.json            # remotion + @remotion/cli (버전 고정, lockfile 커밋)
├── requirements.txt        # edge-tts 버전 고정
├── build.py                # 오케스트레이터: 파싱 → TTS → PCM 합성 → 렌더 호출
├── parse_scripts.py        # docs/tutorial/scripts/*.md 표 → lines.json
├── tts.py                  # edge-tts 호출, 대사별 mp3 (+웅얼 후처리)
├── src/
│   ├── Root.tsx            # RemotionRoot: Composition 6개 (id: practice-1 … practice-6)
│   └── Practice.tsx        # 공용 컴포지션 (props: 코스 메타 + 타이밍 JSON)
└── out/
    ├── practice-N/lines/*.mp3   # 대사별 음성 (content-hash 캐시)
    ├── practice-N/audio.wav     # 합쳐진 트랙 (48kHz mono s16, 침묵 포함)
    ├── practice-N/timing.json   # [{i, text, style, start, end}] — P4 seek 앵커의 근거
    └── practice-N.mp4           # 최종 (유튜브 업로드 대상)
```

의존성: Node(이미 있음), `edge-tts`(pip — **온라인 MS TTS 클라이언트**),
`ffmpeg`(이미 있음), Remotion(npm, 이 폴더에만).

### 2.2 대본 파싱 (parse_scripts.py)

- 입력: `docs/tutorial/scripts/연습N-*.md`의 표. 열: `대사 | 스타일 | 뒤 쉼(초)`.
- 파싱 규칙: `|`로 split, 헤더/구분행 무시, 스타일 ∈ {보통, 빠르게, 느리게, 웅얼, 침묵}.
  검증 실패(모르는 스타일, 쉼이 숫자 아님) 시 파일·행 번호와 함께 즉시 에러
  (조용한 스킵 금지). 파싱 총 대사 수는 77과 assert (대본 변경 시 상수 갱신).
- 출력: `lines.json` — `[{i, text, style, pause_after}]`.

### 2.3 TTS (tts.py) — 재현성 계약

- 엔진: `edge-tts`, 목소리 `ko-KR-SunHiNeural`(여, 차분) — 확정 전 샘플 2개
  (SunHi/InJoon)를 사용자에게 들려주고 결정. rate 매핑:

| 스타일 | edge-tts rate | 후처리 |
|---|---|---|
| 보통 | `-5%` (또박또박) | — |
| 빠르게 | `+40%` | — |
| 느리게 | `-20%` | — |
| 웅얼 | `+30%` | ffmpeg `volume=0.35` + lowpass 필터 (알아듣기 어렵게 — 🙉 미끼) |
| 침묵 | TTS 없음 | 무음 구간만 |

- 온라인 서비스 대응(한 방 실행·멱등 보장):
  - 시작 시 voice 목록 preflight — 지정 voice 없으면 즉시 에러.
  - 대사별 재시도 최대 3회(지수 backoff), 실패 시 어느 대사인지 명시하고 중단.
  - 출력은 임시 파일에 쓰고 완성 후 atomic rename — 부분 파일이 캐시로 안 남게.
  - 캐시 키 = SHA256(대사 텍스트+스타일+voice+rate+**후처리 파라미터(웅얼
    volume/lowpass)+렌더 파이프라인 버전 상수**) — 대본·설정 수정 시 해당
    줄만 재생성, 설정 변경 후 낡은 음성 재사용 없음.
  - `edge-tts`/Remotion 버전 고정(requirements.txt, package-lock.json 커밋).
- 콘솔 출력은 ASCII 상태 로그(cp949 안전), 파일 경로는 `practice-N` ASCII 이름.
  자식 프로세스(edge-tts/ffmpeg/Remotion)의 stdout/stderr는 **UTF-8로 캡처 후
  cp949 안전 치환**해 출력(실패 경로 인코딩 예외 방지). Windows에서 npx는
  `shutil.which("npx")` 결과로 호출.

### 2.4 오디오 합성 + 타이밍 — PCM 계약

MP3 그대로 concat하지 않는다(인코더 딜레이 누적·샘플레이트 불일치 위험 —
§9 M3). 계약:

1. 모든 대사 mp3를 **48kHz mono s16 PCM**으로 디코드.
2. 무음은 파일이 아니라 **정확한 샘플 수**(`round(pause × 48000)`)로 생성.
3. `audio.wav` = 머리 무음 1.5s + Σ(대사 PCM + 뒤 쉼 PCM) + 꼬리 무음 1.5s.
4. 타이밍은 ffprobe 추정이 아니라 **PCM 샘플 오프셋**에서 계산 →
   `timing.json`의 [start, end)는 정의상 오차 0.
5. 기대 총 길이 = `3.0 + Σ(대사 샘플수/48000 + pause)` — 산출 wav 길이와
   샘플 단위 일치 assert. (TTS 개별 길이는 예측 불가이므로 실측만 사용.)

### 2.5 Remotion 컴포지션 (Practice.tsx)

- **1920×1080, 30fps** (앱 플레이어는 가로 영상 전제).
- Composition id는 `practice-1`~`practice-6` (Remotion id는 영숫자와 `-`만
  허용 — 한글 불가, §9 M4). 코스별 길이는 `calculateMetadata`로
  `durationInFrames = ceil(audio_samples / 48000 × 30)` 주입.
- 화면 설계 — **핵심 제약: 말한 문장을 화면에 그대로 보여주지 않는다.**
  검수 연습은 "귀로 듣고 자막과 대조"가 본질. 화면에는:
  - 상단: 코스 배지 ("연습 1 · 기본기"), 진행 점 (n/총)
  - 중앙: 말하기 애니메이션(원형 파형 펄스 — timing.json으로 발화 중에만
    움직임) + 스타일 아이콘(빠르게=⚡, 웅얼=🙉, 침묵=🤫)
  - 하단: 고정 안내 "귀로 듣고, 자막과 맞는지 확인하세요"
  - 잘 안 들리는 분을 위한 보조는 영상이 아니라 **앱 투어 버블**이 담당:
    미끼 단계 버블에 이미 목표 단어가 적혀 있고(예: "깻잎"), 필요 시 P4에서
    "힌트 보기" 토글 추가 검토(§7-4). 유튜브 자동 CC가 정답을 노출할 수 있는
    리스크는 §6-9.
- 오디오 자산 계약: audio.wav를 Remotion **public 디렉터리**에 배치하고
  `staticFile("practice-N/audio.wav")`로 참조(로컬 절대경로 직접 참조 금지 —
  번들러가 못 봄). build.py가 render 전에 out/ → public/으로 복사.
- 렌더: `npx remotion render practice-N out/practice-N.mp4 --codec h264`
  (오디오 AAC 48kHz — 소스와 동일 SR 유지). **6개 일괄 렌더 전에 1코스
  preview render로 오디오·화면 동기부터 확인**(전량 렌더 후 실패 발견 방지).

### 2.6 P2 완료 기준 (acceptance — 전부 기계 assert, 사람 귀 항목만 User)

- [ ] `python build.py` 한 방에 mp4 6개 생성. 재실행 시 **TTS 합성 호출
      0회**(캐시 히트 — voice 목록 preflight 1회는 허용, 멱등 확인 로그).
- [ ] 파싱 대사 수 == 77 assert.
- [ ] 각 audio.wav 길이 == 기대 공식(§2.4-5)과 샘플 단위 일치.
- [ ] 각 mp4: ffprobe로 1920×1080/30fps/오디오 스트림 존재, 길이가 wav와
      1프레임(33ms) 이내.
- [ ] 무음 구간 assert: 연습2의 5초 침묵, 연습4의 0.75초 토막 간격 —
      해당 PCM 구간 RMS < 임계(파형을 사람이 보는 게 아니라 코드로 검사).
- [ ] 웅얼 대사가 실제로 알아듣기 어려움 — **User** (사람 귀).
- [ ] 콘솔 cp949 안전 (Windows — 프로젝트 규칙).

---

## 3. P3 — 유튜브 업로드 (사용자, 수동)

1. mp4 6개를 유튜브에 업로드. **미등록(unlisted)** 권장 — 링크로만 접근.
2. 제목 규칙: `[자막연습 1] 기본기` … `[자막연습 6] 마무리`.
3. 업로드 체크리스트(코스 전체가 이 영상 하나에 걸리는 단일 장애점 — §6-8):
   - [ ] **퍼가기(임베드) 허용** 켬 — 꺼져 있으면 앱 플레이어가 아예 못 튼다.
   - [ ] "아동용 아님" 설정.
   - [ ] 연령 제한 없음.
   - [ ] 업로드 직후 앱이 아닌 브라우저 시크릿 창에서 임베드 재생 확인.
4. video_id 6개를 에이전트에게 전달.

유튜브 자동자막(CC)이 생기면 파이프라인 crosscheck에는 이득이지만, 시청자가
CC를 켜면 정답이 노출될 수 있다(§6-9) — 안내 문구로 대응(끄고 연습 권장).

## 4. P4 — 앱 연결 (코스↔영상 바인딩 + 연습 상태 관리)

### 4.1 데이터 모델

- `Job.practice_course: str = ""` — additive 컬럼 (`_ensure_columns`에
  `VARCHAR DEFAULT ''`). 값 = 코스 id (`basic|playback|fast|structure|timing|finish`).
  기존 `Job.practice: bool`은 유지. practice_course를 설정하면 practice도 자동
  True. **바인딩을 해제해도 practice는 자동 False로 내리지 않는다**(합성 연습
  영상은 영구히 학습 제외 — §9 B3).
- **코스당 활성 영상 1개 계약**: `POST /api/jobs/{vid}/practice`(body
  `{on, course?}`)가 같은 course를 가진 다른 Job의 practice_course를 **같은
  트랜잭션에서 해제**하고, DB 차원에서 **부분 UNIQUE 인덱스**
  (`practice_course WHERE practice_course <> ''` — PG·SQLite 둘 다 지원)로
  동시 지정 레이스까지 차단(§10 M4). 프론트가 jobs를 순회해 추측하지 않도록
  `GET /api/tutorials` → `{course_id: video_id}` 맵을 서버가 반환(§9 M1).
- **코스 key는 영구 불변**(`basic|playback|fast|structure|timing|finish`) —
  코스 개편 시에도 key는 재사용·개명하지 않고 새 key를 만든다.
- API 의미 분리: "코스 해제"(practice_course='')와 "연습 해제"(practice=False)는
  별개 — 합성 연습 영상은 코스를 떼도 practice=True 영구 유지.
- 지정 UI: 관리자 카드의 🎓 토글을 소형 선택(코스 1~6/일반 연습/해제)으로.

### 4.2 코스 메뉴 연동 (프론트) — 핸드오프는 React 상태로

- App이 `GET /api/tutorials` 결과를 들고 Editor에 prop 전달.
- 코스 메뉴(`Editor.tsx` tour-menu)에서:
  - 현재 영상이 그 코스의 전용 영상이면: 그냥 시작 (지금과 동일).
  - 전용 영상이 따로 있으면: "전용 연습 영상에서 시작 →" — App의 일회성 상태
    `pendingCourse: {courseKey, videoId, nonce}`를 세팅하고 selected 교체.
    Editor는 **`key={videoId}`로 재마운트**(mode/lang/tour 등 이전 영상 상태
    누출 원천 차단, §10 M5)하고, **세그먼트 로드 + 플레이어 ready가 모두 그
    videoId로 일치**할 때만 pendingCourse 소비(ready 전 seek는 조용히 유실됨
    — usePlayer에 videoId별 ready 노출). timeout·다른 영상 선택 시 즉시 폐기.
    (localStorage 아님 — 실패한 전환 값의 오발 방지, §9 M2. 새로고침 유실은
    fail-closed로 수용.)
  - 전용 영상이 없으면: 지금처럼 현재 영상에서 시작 (동작 저하 없음).
- 첫 방문 자동 시작(기본기)은 현재 영상 그대로 — 영상 강제 전환은 어르신에게
  혼란 (명시 클릭일 때만 전환).

### 4.3 사용자별 연습 세션 = Job 복제 (v4 — 사용자 요구로 격리 승격)

**2026-07-14 사용자 확정**: "A가 아무리 연습·수정해도 B·C가 들어오면 동시에
병렬로 각자 처음부터" — v3의 스냅샷·초기화+소프트 가드(동시 1명 운영)를
**supersede**. 코덱스 1차 B1이 제안했던 사용자별 세션을 채택하되, 별도
스냅샷 테이블 대신 **기준 Job 복제** 방식(스냅샷 = 기준 Job 그 자체):

- **기준(baseline) Job**: practice_course가 바인딩된 Job. 리허설 통과 후
  **불변** — 어떤 검수자도 여기에 직접 쓰지 않는다. 코스5 결함 주입은
  바인딩 시 기준 Job에 1회 주입(모든 복제본이 물려받음).
- `Job.clone_of: int|None`, `Job.session_key: str` — additive 컬럼.
  `POST /api/jobs/{vid}/practice-session` → 기준 Job의 세그먼트 전체 +
  SttBlob을 새 Job 행(clone_of=기준 id, session_key=클라이언트 UUID,
  practice=True)으로 깊은 복사. 이미 그 session_key의 복제본이 있으면 재사용.
- **API 스코프 (구현 확정: 합성 video_id)**: 복제본의 video_id =
  `"<base>~sha256(session_key)[:10]"` — 기존 video_id 키 엔드포인트 전부가
  무수정으로 복제본에 동작(ps 파라미터 플럼빙 불필요). 플레이어만 `~` 접미사를
  떼고 실제 YouTube id를 로드. 접미사는 절단이 아니라 **해시**(접두 절단은
  UNIQUE video_id 충돌 — E2E에서 실증되어 수정).
- **처음부터 다시** = 복제본 삭제 후 재복제 (기준본이 원본이므로 항상 동일
  시작 상태 — 사용자 요구 충족). 저장 큐 flush + undo 초기화는 유지(§10 M3).
- **격리 결과**: A·B·C 동시 연습 = 서로 다른 clone Job → 세그먼트 충돌
  원천 불가. reset 경합·소프트 가드·"동시 1명" 운영 규칙 전부 불필요해짐.
- 목록·학습 위생: `/api/jobs`와 `GET /api/tutorials`는 `clone_of IS NULL`만
  노출. 복제본은 practice=True라 학습·평가 제외(CHG-20260714-005)에 자동
  포함. **TTL 청소**: worker가 시작 시(및 일 1회) updated_at 7일 지난
  복제본 삭제 — practice 복제본만 삭제 가능(BR-DATA-001: clone_of NOT NULL
  + practice=True 이중 조건 없이는 DELETE 금지).
- **연습 Job은 ko 단일 트랙 계약** 유지: 기준 Job에 번역/포크가 있으면
  복제 거부(§10 M3 — FK 복원 계약을 만들지 않고 원천 봉쇄).
- **코스 5 결정적 결함 주입**: 자동 정리(✨)가 침묵 패딩을 지워버리므로
  (split.py가 발화 단어 경계로 재발행) 초기 STT 상태만으로는 "문제 큐"가
  비어 코스 5가 막힐 수 있다(§9 M10). 스냅샷 생성 시 서버가 의도적 결함을
  주입해 저장: 한 행의 end를 다음 발화까지 늘려 침묵 걸치게 + 속사포 행
  유지(cps 초과는 자동 정리로도 안 사라짐 — 확장 여지 없을 때). 초기화하면
  항상 같은 결함으로 복원 → 리허설과 실사용이 같은 상태.

### 4.4 투어 신뢰성 (기존 코스 개선 — 연습 영상 도입 전제 조건)

- **tourEvent를 성공 후 발생 — 전수 분류**(§9 M13 + §10 M6): 모든 tourEvent
  호출을 두 부류로 나눈다. ① 동기 UI 동작(play/seek/rate/loop/nav/bigtype/
  mode 전환 등)은 현행 유지. ② **서버 변이**(confirm 저장, split, merge,
  delete, set-times, start-here, next-here, edge-drag 커밋, repair,
  auto-timing, tighten, confirm-safe, absorb, export-check)는 성공 응답 +
  기대 변경 확인 후에만 발생. P4에서 전수 목록 작성 후 일괄 이동.
- **앵커 = {t, focus}**(§9 B2 → §10 B2 확장): seek만으로는 조작 대상 행이
  보장 안 됨(seek는 focused row를 안 바꿈 — 코스4에서 엉뚱한 행 merge 가능).
  전용 연습 영상에서 앵커 있는 단계 진입 시: ① 플레이어를 t로 seek,
  ② **t 시간대 세그먼트를 찾아 focusSegment**, ③ 그 단계의 스포트라이트
  target은 `.row.focused`(첫 매칭 아님). 앵커 시각은 P2 timing.json에서
  도출. 일반 영상에서는 무시.
- **플레이어 에러 게이트**: `usePlayer`에 onError 추가 — 삭제/임베드 금지/
  지역 제한 코드면 코스 시작 대신 "연습 영상을 열 수 없어요. 관리자에게
  알려주세요" 안내(§9 M11).
- 버블 배치(§9 M14 → §10 M9: 검증 확대 대신 코드로 해결): Tour.tsx에
  **위·아래 모두 공간 부족 시 중앙 배치 폴백 + viewport clamp** 구현
  (현재는 아래 부족이면 무조건 위). 검증은 확대 상태 스팟체크(전 코스
  전수 검증은 과설계로 기각).

### 4.5 P4 완료 기준

- [ ] 마이그레이션: 기존 DB(SQLite 복사본+클라우드 PG 패턴) additive.
      전후 `SELECT count(*)`(jobs/segments/translations) 동일 assert.
- [ ] 코스당 활성 영상 1개: 같은 코스 재지정 시 이전 Job 바인딩 해제 확인.
- [ ] 코스 메뉴 → 영상 전환 → 세그먼트 로드 후 해당 코스 자동 시작 (E2E:
      scratch DB + 실브라우저, 전환 실패 시 오발 없음 확인).
- [ ] 전용 영상 미지정 시 기존 동작 그대로 (코스 메뉴 스냅샷 비교).
- [ ] 세션 격리 E2E: 브라우저 A(세션키 α)에서 편집 → 브라우저 B(세션키 β)로
      같은 코스 진입 → B는 기준 상태 그대로(A 편집 안 보임); 기준 Job
      세그먼트 checksum 불변. "처음부터 다시" → 재복제로 기준 상태 복원.
      일반 Job에 practice-session 호출 시 403. 저장 큐 flush + undo 초기화
      후 reset(늦은 PUT이 새 복제본 오염 안 함).
- [ ] 앵커 E2E: 코스4·5의 앵커 단계에서 실제 조작된 행의 시간 구간이 미끼
      구간과 겹치는지 assert (§10 B2).
- [ ] 부분 UNIQUE 인덱스: 같은 코스 동시 지정 시 한쪽 IntegrityError →
      API가 재시도/에러 안내.
- [ ] practice_course 해제 후에도 practice=True 유지 (학습 제외 영구).
- [ ] 학습 제외 회귀 테스트: practice Job에 reviewed 세그먼트를 만들고
      learned_line_budget/translation_examples/training export/CER 결과에
      안 들어오는지 assert (CHG-20260714-005 고정용).

## 5. P5 — 리허설 (필수, 최대 2회 반복)

1. 유튜브 링크 6개를 평소처럼 등록하고 **등록 직후, 어떤 확인·편집 동작보다
   먼저 🎓 "일반 연습"(practice=True) 지정**(§10 M1 — 리허설 중 세그먼트가
   학습·평가에 새는 것 방지; practice_course 코스 연결만 리허설 통과 후).
   그 다음 로컬 워커가 STT+교정 처리.
2. **검사 대상 = 화면에 뜨는 초안** (표시 규칙: text_final → text_llm →
   text_whisper — Editor.tsx). whisper 원문이 아니라 교정 후 초안 기준으로
   판정한다(§9 M9). predicate에는 항상 **"조작 가능한 화면 행 존재"**가
   포함된다 — 예: 웅얼 대사가 STT에서 아예 빈 텍스트가 되면 splitter가 행
   자체를 안 만들어 🙉 누를 행이 없음(§10 M7) → 이 경우 볼륨을 올려 재TTS
   (행은 생기되 내용이 어긋나게).
3. 미끼별 predicate (MAPPING.md 대조):

| 미끼 | 기대 조건 (화면 초안 기준) | 불발 시 대안 |
|---|---|---|
| 연습1 오인식 4종 (깻잎·밤나무·축지법·공중부양) | ≥2개 행에서 초안 ≠ 대본 원문 | ⚠ 축지법·공중부양은 **이미 hotwords/용어사전에 있어 맞게 인식될 확률 높음** — 불발 시 용어사전에 없는 미끼로 교체(예: 유사 발음 일반어). 정 안 되면 "맞는지 확인하고 넘어가기" 연습으로도 코스 성립 |
| 연습1 웅얼 | 해당 행 초안이 비었거나 명백히 어긋남 | volume/lowpass 강화 후 해당 대사만 재TTS·재렌더 |
| 연습2 속사포 | 해당 행 cps ⏩ 빨간 배지 | rate +40%로 부족하면 +60% |
| 연습2 5초 침묵 | 침묵에 걸친 자막 없음(스냅 여지) | 침묵 7초로 확대 |
| 연습3 상식 문장 5개 | 안심(✅) 배지 ≥3개 | 문장을 더 흔한 관용구로 |
| 연습3 "뭉치" 4회 | 동일 오철자로 ≥3회 등장 | 더 흔들리는 이름으로 교체 |
| 연습4 초장문 | 한 행 길이 > soft budget (나누기 재료) | 문장 더 길게 |
| 연습4 토막말 0.75s | 별도 행 ≥3개로 잘림 | 간격 0.9s로 |
| 연습5 결함 | 스냅샷 주입으로 **결정적** (§4.3) — STT 결과 무관 | — |
| 연습6 | 미끼 없음 (도구 버튼 연습) | — |

4. 어긋난 미끼는 대본 수정 → 해당 영상만 재렌더(TTS 캐시로 수정 줄만 재생성)
   → 재업로드(새 video_id) → 재등록 → 재검사. **최대 2회 반복**. 2회로도
   불발인 미끼의 종결 대안은 **재렌더가 필요 없는 것만** 유효(§10 M7):
   ① 스냅샷에 결정적 결함 주입(코스5 방식 확장 — 텍스트를 서버가 직접
   어긋나게), ② 해당 단계를 "확인하고 넘어가기" 연습으로 전환(투어 문구만
   수정). 종결 후 마지막 pass 검증 1회.
5. 통과 상태에서 practice_course 지정(=이 시점 스냅샷 촬영, §4.3) →
   검수자 1명에게 파일럿.

리허설 없이는 배포하지 않는다: 오인식은 확률적이라 미끼가 안 터지면
코스 3(찾기·바꾸기)·코스 1(고치기)이 헛돎.

---

## 6. 리스크와 대응

| # | 리스크 | 가능성 | 대응 |
|---|---|---|---|
| 1 | 미끼 단어가 오인식 안 됨 (STT가 너무 잘함 / hotwords가 미끼를 교정) | **높** | P5 predicate 표 + 대안 열. 축지법·공중부양은 hotwords 소속이라 특히 위험 → 리허설 1순위 확인 |
| 2 | TTS가 너무 깨끗해 실제 강연(잡음·사투리)과 괴리 | 중 | 튜토리얼 1차 목적은 UI 조작 학습 — 허용. 듣기 감각은 실영상에서 자연 습득. 원하면 v2에서 배경 소음 트랙 |
| 3 | 웅얼 처리로도 여전히 잘 들림 / 아예 STT가 빈 자막 생성 | 중 | 빈 자막이어도 OK — 🙉 대신 "빈 자막" 연습이 됨. 리허설에서 volume/lowpass 조정 |
| 4 | 유튜브 자동자막 미생성 (짧은 TTS 영상) | 중 | crosscheck 없이도 파이프라인 정상(whisper 단독). 안심 배지 미부착 가능 → 코스3 안심 단계는 missingHint+건너뛰기 있음 |
| 5 | Remotion 라이선스 | 낮 | 운영 주체가 개인(1인) — 무료 대상(개인/3인 이하 회사). P2 시작 시 최신 라이선스 문서 재확인 후 버전·확인일 기록 |
| 6 | edge-tts 서비스 변경/차단 | 낮 | 렌더는 1회성 배치 — mp4는 영구. 버전 고정 + 재렌더 필요 시 대체 TTS(로컬 melo-tts 등) |
| 7 | 코스 개편 시 영상과 어긋남 | 중 | MAPPING.md가 계약 문서 — 코스 단계 변경 시 MAPPING 갱신 필수. seek 앵커는 timing.json에서 도출되므로 대본이 바뀌면 재도출 |
| 8 | **유튜브 영상 자체가 죽음** (삭제/비공개/임베드 금지/지역·연령 제한) — 코스 전체 단일 장애점 | 중 | P3 업로드 체크리스트(임베드 확인) + P4 onError 게이트 + 관리자 재바인딩 UI. 분기 1회 링크 점검 |
| 9 | 시청자가 유튜브 CC를 켜서 정답 노출 | 낮 | 안내 문구. 강제 불가 — 허용 (연습 효과만 감소, 데이터 피해 없음) |
| 10 | 두 검수자가 동시에 같은 코스 연습 → 서로 간섭 | — | **해소(v4)**: 사용자별 Job 복제 세션(§4.3) — 동시 연습은 서로 다른 복제본이라 간섭 원천 불가 |
| 11 | 연습 영상 신호가 학습 데이터 오염 | — | **차단 완료**: absorb + line_budget + translation_examples + training export + CER 전부 practice 제외 (CHG-20260714-005) + P4 회귀 테스트. **LlmCache는 제외 범위 밖**(§10 Q2 기각): 캐시는 학습이 아니라 메모이제이션 — 같은 입력 텍스트면 같은 출력 재사용은 API 재호출과 의미상 동일, 오염 아님 |

## 7. 열린 질문 (사용자 결정 필요)

1. ~~TTS 목소리~~ **결정(2026-07-14): InJoon(남)** — SunHi/InJoon/Hyunsu
   샘플 청취 후 사용자 확정.
2. 영상 화면 톤: 미니멀(파형+배지) — 이의 없으면 확정.
3. 유튜브 채널: 본 채널 vs 별도 연습용 채널(미등록이면 어디든 무방).
4. 접근성 "힌트 보기": 미끼 단계 버블에 정답 문장 토글(잘 안 들리는 분용).
   Codex 2차도 지적(§10 Q1 — 청력 저하면 목표 단어만으론 비교 자체가 불가).
   **Agent 추천: P4 필수 포함**(구현 작음 — 버블에 접힌 "정답 문장 보기" 한 줄).
   사용자 확정 필요.

## 8. 검증 총괄 (Agent 직접 실행 / User 위임 — 경계 명시)

| 검증 | 방법 (측정 기준) | 주체 |
|---|---|---|
| 파서·TTS·타이밍 | 유닛 스모크: 대사 수 76, wav 길이 샘플 일치, 무음 RMS assert | Agent |
| mp4 산출 | ffprobe: 1920×1080/30fps/오디오 스트림/길이 wav±1프레임 | Agent |
| 웅얼 가청성, 목소리 톤 | 사람 귀 | User |
| STT 미끼 적중 | §5 predicate 표 — 세그먼트 덤프에서 조건별 pass/fail 출력 | Agent(덤프+판정 스크립트) + User(교체 승인) |
| P4 E2E | scratch DB + 실브라우저: §4.5 체크리스트 전항 | Agent |
| 실제 유튜브 임베드 재생 | 앱에서 연습 영상 6개 재생 (Agent 환경에선 iframe 재생 NOT VERIFIED 관례) | **User** |
| 확대 화면 버블 | 125/150/200% zoom + 1366×768에서 코스 1개 완주, target 가림 없음 | User (Agent가 체크리스트 제공) |
| 파일럿 | 검수자 1명 코스 1~6 완주 — 완료 플래그 6개 확인(중도 이탈은 이제 완료로 안 찍힘), 건너뛰기 사용 횟수 청취 | User |

---

## 9. Codex 감사(2026-07-14) finding 처리 기록

| ID | 처리 | 내용 |
|---|---|---|
| B1 사용자별 연습 격리 | **부분 수용** | 완전한 per-user 세션은 과설계로 기각(≤50명·1회성). 스냅샷+초기화(§4.3)로 대응, 동시 충돌은 리스크 문서화(§6-10) |
| B2 단계↔영상 구간 앵커 | **부분 수용** | 전체 manifest는 기각(대본이 미끼 행을 유일하게 설계). timing.json 기반 선택적 seek 앵커(§4.4)만 채택 |
| B3 학습 경로 practice 누수 | **수용·수정 완료** | line_budget/translation_examples/training×2/CER 전부 필터 (CHG-20260714-005) + P4 회귀 테스트 |
| M1 코스당 1영상 계약 | **수용** | 서버 트랜잭션 해제 + GET /api/tutorials (§4.1). 별도 바인딩 테이블은 기각 — 컬럼+서버 계약으로 충분 |
| M2 localStorage 핸드오프 | **수용** | React 상태 + 로드 후 소비 (§4.2) |
| M3 PCM/concat 계약 | **수용** | §2.4 전면 개정 (샘플 오프셋 타이밍) |
| M4 Remotion id/duration | **수용** | practice-N + calculateMetadata (§2.5) |
| M5 재현성(edge-tts 온라인) | **수용** | §2.3 재현성 계약 |
| M6 문장 비표시 과함 | **부분 수용** | 원칙 유지(버블이 목표 단어 표기). 힌트 토글은 열린 질문 §7-4. CC 노출은 §6-9 |
| M9 "STT 결과" 정의 + hotwords 충돌 | **수용** | §5 화면 초안 기준 + predicate 표 + hotwords 경고(§6-1) |
| M10 코스5 침묵 제거됨 | **수용** | 스냅샷 결함 주입으로 결정화 (§4.3) |
| M11 YouTube 단일 장애점 | **수용** | §3 체크리스트 + §4.4 onError + §6-8 |
| M12 중도이탈=완료 | **수용·수정 완료** | exit는 완료 플래그 안 씀 (CHG-20260714-006). 건너뛰기-완주는 완료로 유지(의식적 완주로 간주) |
| M13 tourEvent 선발생 | **수용** | P4 §4.4에서 성공 후로 이동 |
| M14 버블 배치 | **부분 수용** | P5 확대 화면 점검 항목화, 실측 collision 배치는 점검 결과에 따라 |
| M15 완료 기준 측정성 | **수용** | §2.6/§4.5/§8 측정 기준 명시 |
| MINOR README 상충 | **수용** | 본 문서가 supersede 명시(머리말) + README 수정 |
| MINOR 76대사 | **수용** | 76으로 정정 |
| MINOR 코스6 학습 0건 | **수용·수정 완료** | 투어 버블에 "연습 영상은 0개가 정상" 문구 추가 |
| Q Remotion 라이선스 | **수용** | §6-5: 개인 1인 확인, P2 시작 시 재확인·기록 |

## 10. Codex 감사 2라운드(2026-07-14) finding 처리 기록

1차 §9의 처리 자체를 재검수받은 결과. 해소 확인 11건 외 신규/재지적:

| ID | 처리 | 내용 |
|---|---|---|
| B1 동시 충돌 lease/409 | ~~부분 수용~~ → **전면 수용(2026-07-14 사용자 확정)** | 사용자가 병렬 격리를 명시 요구 → Job 복제 기반 사용자별 세션으로 §4.3 v4 재설계. 코덱스 원안이 옳았음 |
| B2 seek만으론 행 미보장 | **수용** | 앵커 {t, focus}로 확장 — seek + t 시간대 세그먼트 focus + target=.row.focused. 조작 행↔미끼 구간 겹침 E2E (§4.4, §4.5) |
| M1 practice 지정 시점 늦음 | **수용** | 등록 직후 일반 연습 지정 먼저, 코스 연결만 리허설 후 (§5-1). 실제 구멍이었음 |
| M2 스냅샷 생명주기 | **수용** | course_id+source_rev 메타, 재인식·재바인딩 시 무효화+재촬영, 결함 주입은 baseline 순수 함수 (§4.3) |
| M3 reset 경합·FK | **수용** | flush+undo 초기화, source_rev 검사, ko 단일 트랙 계약(번역/포크 있으면 거부 — FK 복원 계약 대신 원천 봉쇄) (§4.3, §4.5) |
| M4 코스당 1영상 레이스 | **수용** | 부분 UNIQUE 인덱스 + course key 영구 불변 + 해제 API 의미 분리 (§4.1) |
| M5 핸드오프 재사용 인스턴스 | **수용** | key={videoId} 재마운트 + 플레이어 ready 게이트 (§4.2) |
| M6 tourEvent 전수 미분류 | **수용** | 동기 UI vs 서버 변이 전수 분류, 서버 변이 전부 성공 후 (§4.4) |
| M7 웅얼 빈 행 + 종결 대안 재렌더 모순 | **수용** | predicate에 "조작 가능한 행 존재", 종결 대안은 재렌더 불필요한 것만(스냅샷 주입/문구 전환) (§5) |
| M8 Remotion 오디오 자산 계약 | **수용** | public 디렉터리 + staticFile + 1코스 preview render 선행 (§2.5) — P2 착수 조건 |
| M9 확대 검증 6코스 전수 | **부분 수용** | 검증 확대 대신 버블 중앙 폴백+clamp를 코드로 구현, 검증은 스팟체크 (§4.4) |
| MINOR 캐시 키·preflight 모순 | **수용** | 키에 후처리 파라미터+파이프라인 버전, 기준 "합성 호출 0회" (§2.3, §2.6) — P2 착수 조건 |
| MINOR 자식 프로세스 cp949 | **수용** | UTF-8 캡처→안전 치환, shutil.which("npx") (§2.3) |
| Q1 접근성 힌트 | **수용 권고** | §7-4를 "P4 필수 추천"으로 승격, 사용자 확정 대기 |
| Q2 LlmCache 격리 | **기각(문서화)** | 캐시=메모이제이션, 같은 입력→같은 출력 재사용은 무해. §6-11에 명시 |
