# 튜토리얼 연습 영상 파이프라인 — 전체 실행 계획 (외부 감사용)

Status: Draft for review (Codex 검사 대상)
Date: 2026-07-14
Owner: User(승인·업로드) + Agent(구현)
Related: ADR-0009, docs/tutorial/README.md, docs/tutorial/MAPPING.md,
CHANGELOG CHG-20260714-001~004

이 문서는 저장소를 모르는 검토자도 감사할 수 있게 자기완결적으로 쓴다.

---

## 0. 배경 — 이미 구현돼 있는 것 (이 계획의 전제)

jamak-ouroboros = 유튜브 강연 자막 파이프라인(로컬 whisper STT → Claude 교정 →
사람 검수 웹앱 → .srt). 검수자는 고령자 다수. 검수 웹앱(React + FastAPI,
Railway 배포, 로컬 GPU 워커가 영상 처리)에 다음이 이미 있다:

- **따라하기 투어 6코스** (`src/jamak/web/frontend/src/Editor.tsx`의 `COURSES`,
  `Tour.tsx`): 실제 UI를 어둡게 하고 컨트롤 하나만 스포트라이트, 각 단계는
  실제 그 동작이 일어나야 진행(`tourEvent(name)` 훅 ~28곳). 코스별 완료 플래그
  `localStorage jamak.tour.<id>`. 첫 에디터 방문 시 기본기 코스 자동 시작.
- **연습용 영상 플래그** (`Job.practice`, additive 컬럼): 관리자가 카드에서
  🎓 연습용 지정. 연습용 영상은 `absorb_job()`이 no-op → 연습 편집이 학습
  데이터(교정쌍/용어사전)를 오염하지 못함. 에디터에 연습용 배너 표시.
- **대본 6개** (`docs/tutorial/scripts/연습N-*.md`): 코스별 전용 영상 대본.
  표(대사/스타일/뒤 쉼)가 사람 검토 문서이자 렌더 파이프라인의 기계 입력.
  각 코스가 요구하는 조작이 필요해지도록 연습 재료를 일부러 심음
  (속사포→되감기·0.75×, 5초 침묵→건너뛰기, 초장문→나누기, 토막말→합치기,
  웅얼→🙉, "뭉치" 반복→찾기·바꾸기). 매핑 검증표는 MAPPING.md.
- **플레이어 제약**: 앱은 YouTube IFrame 플레이어를 쓴다(`usePlayer.ts`).
  → 연습 영상도 **유튜브에 올라가 있어야** 한다. mp4 직접 재생 경로는 없고
  만들 계획도 없다(파이프라인 전체가 video_id 기준).

## 0.1 목표

코스 1~6 각각에 전용 연습 영상을 붙여서, 어르신 검수자가
"연습 영상 열기 → 파란 불 따라 하기"만으로 전 기능을 손으로 익히게 한다.

비목표(스코프 밖): 화면 녹화형 강의 영상, 앱 내 mp4 플레이어, 유튜브 업로드
자동화(OAuth 필요 — 사용자 수동), 다국어 튜토리얼.

---

## 1. 전체 흐름 (5단계)

```
P1 대본 확정(완료) ─→ P2 렌더 파이프라인(TTS+Remotion→mp4 6개)
   ─→ P3 유튜브 업로드(사용자) ─→ P4 앱 연결(코스↔영상 바인딩)
   ─→ P5 리허설·미끼 조정 ─→ 롤아웃
```

| 단계 | 담당 | 산출물 | 예상 규모 |
|---|---|---|---|
| P1 | 완료 | scripts/연습1~6.md (총 78대사) | — |
| P2 | Agent | `tools/tutorial-video/` 렌더 프로젝트 + mp4 6개 | 코드 ~400줄 |
| P3 | User | 유튜브 영상 6개 (미등록 공개) + video_id 목록 | 10분 |
| P4 | Agent | `Job.practice_course` 컬럼 + 코스 메뉴 연동 | 코드 ~150줄 |
| P5 | User+Agent | STT 결과 검수 → 미끼 단어/대본 조정 → 재렌더 (최대 1회 반복) | 반나절 |

---

## 2. P2 — 렌더 파이프라인 상세

### 2.1 위치·구조

```
tools/tutorial-video/
├── package.json            # remotion + @remotion/cli (로컬 devDeps, 앱과 분리)
├── build.py                # 오케스트레이터: 대본 파싱 → TTS → 타이밍 JSON → 렌더 호출
├── parse_scripts.py        # docs/tutorial/scripts/*.md 표 → lines.json
├── tts.py                  # edge-tts 호출, 대사별 mp3 생성 (+웅얼 후처리)
├── src/
│   ├── Root.tsx            # RemotionRoot: 코스별 Composition 6개 등록
│   └── Practice.tsx        # 공용 컴포지션 (props: 코스 메타 + 타이밍 JSON)
└── out/
    ├── 연습N/lines/*.mp3   # 대사별 음성
    ├── 연습N/audio.wav     # 합쳐진 트랙 (침묵 포함)
    ├── 연습N/timing.json   # [{i, text, style, start, end}] — 화면 표시용
    └── 연습N.mp4           # 최종 (유튜브 업로드 대상)
```

의존성: Node(이미 있음 — 프론트 빌드에 사용), `edge-tts`(pip, 무료 MS TTS),
`ffmpeg`(이미 있음 — 파이프라인이 사용), Remotion(npm, 이 폴더에만).

### 2.2 대본 파싱 (parse_scripts.py)

- 입력: `docs/tutorial/scripts/연습N-*.md`의 표. 열: `대사 | 스타일 | 뒤 쉼(초)`.
- 파싱 규칙: `|`로 split, 헤더/구분행 무시, 스타일 ∈ {보통, 빠르게, 느리게, 웅얼, 침묵}.
  검증 실패(모르는 스타일, 쉼이 숫자 아님) 시 파일·행 번호와 함께 즉시 에러
  (조용한 스킵 금지).
- 출력: `lines.json` — `[{i, text, style, pause_after}]`.

### 2.3 TTS (tts.py)

- 엔진: `edge-tts`, 목소리 `ko-KR-SunHiNeural`(여, 차분) — 확정 전 샘플 2개
  (SunHi/InJoon)를 사용자에게 들려주고 결정. rate 매핑:

| 스타일 | edge-tts rate | 후처리 |
|---|---|---|
| 보통 | `-5%` (또박또박) | — |
| 빠르게 | `+40%` | — |
| 느리게 | `-20%` | — |
| 웅얼 | `+30%` | ffmpeg `volume=0.35` + lowpass 필터 (알아듣기 어렵게 — 🙉 미끼) |
| 침묵 | TTS 없음 | 무음 구간만 |

- 대사별 mp3 저장 + `ffprobe`로 실측 길이 취득 → 타이밍 계산의 근거.
  (TTS 길이는 예측 불가이므로 **실측만** 사용. 추정치 금지.)

### 2.4 오디오 합성 + 타이밍

- `audio.wav` = concat(대사1, 침묵(뒤 쉼1), 대사2, …). ffmpeg concat demuxer.
- 영상 머리/꼬리에 1.5초 무음 패딩(유튜브 인트로 잘림 대비).
- `timing.json`에 각 대사의 [start, end) 초 기록 → Remotion 화면 동기화.

### 2.5 Remotion 컴포지션 (Practice.tsx)

- 1080×1920 아님 — **1920×1080, 30fps** (앱 플레이어는 가로 영상 전제).
- 화면 설계 — **핵심 제약: 말한 문장을 화면에 그대로 보여주지 않는다.**
  검수 연습은 "귀로 듣고 자막과 대조"가 본질이라, 문장이 화면에 보이면
  읽기만 하고 듣기 연습이 안 됨. 화면에는:
  - 상단: 코스 배지 ("연습 1 · 기본기"), 진행 점 (n/총)
  - 중앙: 간단한 말하기 애니메이션(원형 파형 펄스 — timing.json으로 발화
    중에만 움직임) + 스타일 아이콘(빠르게=⚡, 웅얼=🙉, 침묵=🤫)
  - 하단: 고정 안내 "귀로 듣고, 자막과 맞는지 확인하세요"
- `<Audio src={audio.wav} />` 하나로 오디오 전체 재생.
- 렌더: `npx remotion render Practice연습N out/연습N.mp4 --codec h264`.

### 2.6 P2 완료 기준 (acceptance)

- [ ] `python build.py` 한 방에 mp4 6개 생성 (재실행 멱등)
- [ ] 각 mp4 길이가 대본 합계(대사 실측 + 쉼)와 ±1초 이내
- [ ] 연습2의 5초 침묵, 연습4의 0.75초 토막 간격이 파형에서 확인됨
- [ ] 웅얼 대사가 실제로 알아듣기 어려움 (사람 귀 확인 — 사용자)
- [ ] 콘솔 cp949 안전 (Windows — 프로젝트 규칙)

---

## 3. P3 — 유튜브 업로드 (사용자, 수동)

1. mp4 6개를 유튜브에 업로드. **미등록(unlisted)** 권장 — 링크로만 접근.
2. 제목 규칙: `[자막연습 1] 기본기` … `[자막연습 6] 마무리` (검색·식별용).
3. video_id 6개를 에이전트에게 전달.

주의: 유튜브가 TTS 콘텐츠를 차단하진 않지만, "아동용 아님" 설정.
자동자막(유튜브측)이 생기면 파이프라인 crosscheck에 오히려 이득(2엔진 비교).

## 4. P4 — 앱 연결 (코스↔영상 바인딩)

### 4.1 데이터 모델

- `Job.practice_course: str = ""` — additive 컬럼 (`_ensure_columns`에
  `VARCHAR DEFAULT ''`). 값 = 코스 id (`basic|playback|fast|structure|timing|finish`).
  기존 `Job.practice: bool`은 유지(절제된 의미: 연습 샌드박스 + absorb 차단).
  practice_course를 설정하면 practice도 자동 True.
- `/api/jobs` 응답에 `practice_course` 추가.
- 지정 UI: 기존 `POST /api/jobs/{vid}/practice` 확장 — body `{on, course?}`.
  관리자 카드의 🎓 토글을 소형 선택(코스 1~6/일반 연습/해제)으로.

### 4.2 코스 메뉴 연동 (프론트)

- App이 jobs를 이미 들고 있음 → `tutorials: Record<courseId, videoId>` 계산해
  Editor에 prop으로 전달.
- 코스 메뉴(`Editor.tsx` tour-menu)에서:
  - 현재 영상이 그 코스의 전용 영상이면: 그냥 시작 (지금과 동일)
  - 전용 영상이 따로 있으면: 버튼 라벨 "전용 연습 영상에서 시작 →" —
    `localStorage.setItem("jamak.pendingCourse", id)` 후 `onOpenVideo(videoId)`
    (App이 selected 교체). Editor 마운트 시 pendingCourse 있으면 그 코스 자동
    시작 + 키 제거.
  - 전용 영상이 없으면: 지금처럼 현재 영상에서 시작 (동작 저하 없음 — 바인딩은
    부가 기능).
- 첫 방문 자동 시작(기본기)은 현재 영상 그대로 유지 — 영상 강제 전환은
  어르신에게 혼란 (명시 클릭일 때만 전환).

### 4.3 P4 완료 기준

- [ ] 마이그레이션: 기존 DB(SQLite 복사본+클라우드 PG 패턴) additive, 행 무손실
- [ ] 코스 메뉴에서 전용 영상 클릭 → 영상 전환 → 해당 코스 자동 시작 (E2E)
- [ ] 전용 영상 미지정 시 기존 동작 그대로 (회귀 없음)
- [ ] 연습 영상 absorb 차단 유지 (practice_course 설정 시 practice=True 강제)

## 5. P5 — 리허설 (필수 1회)

1. 유튜브 링크 6개를 평소처럼 등록 → 로컬 워커가 STT+교정 처리.
2. 각 영상의 STT 결과를 MAPPING.md와 대조:
   - 미끼가 **실제로 오인식**됐나? (깻잎/축지법/공중부양/뭉치/웅얼 문장)
   - 연습4 토막말이 **별도 자막으로 잘렸나**? (합치기 재료)
   - 연습5 속사포에 **⏩빨간 배지**가 붙었나? 침묵 패딩이 스냅 여지를 만들었나?
   - 연습3 상식 문장에 **안심 배지**가 붙었나?
3. 어긋난 미끼는 대본 수정(예: "뭉치"→더 흔들리는 이름) → 해당 영상만 재렌더
   → 재업로드(새 video_id) → 재등록. **1회 반복으로 수렴 목표.**
4. 통과 후 각 영상에 practice_course 지정 → 검수자 1명에게 파일럿.

리허설 없이는 배포하지 않는다: 오인식은 확률적이라(README 명시) 미끼가
안 터지면 코스 3(찾기·바꾸기)·코스 1(고치기)이 헛돎.

---

## 6. 리스크와 대응

| # | 리스크 | 가능성 | 대응 |
|---|---|---|---|
| 1 | 미끼 단어가 오인식 안 됨 (STT가 너무 잘함) | 중 | P5 리허설로 검출, 대본 조정. 최악의 경우에도 코스는 진행 가능(모든 단계에 건너뛰기 있음) |
| 2 | TTS가 너무 깨끗해 실제 강연(잡음·사투리)과 괴리 | 중 | 튜토리얼 목적은 UI 조작 학습이지 청취 훈련이 아님 — 허용. 원하면 v2에서 배경 소음 트랙 믹스 |
| 3 | 웅얼 처리로도 여전히 잘 들림 / 아예 STT가 빈 자막 생성 | 중 | 빈 자막이어도 OK — 🙉 대신 "빈 자막" 연습이 됨. 리허설에서 volume/lowpass 조정 |
| 4 | 유튜브 자동자막 미생성 (짧은 TTS 영상) | 중 | crosscheck 없이도 파이프라인 정상 동작(whisper 단독). 안심 배지가 안 붙을 수 있음 → 코스3 안심 단계는 missingHint+건너뛰기 이미 있음 |
| 5 | Remotion 라이선스 | 낮 | 개인/소규모(연매출 기준 미만) 무료. 해당 없음 확인됨. 걸리면 ffmpeg 슬라이드 합성으로 대체 (시각 품질만 하락) |
| 6 | edge-tts 서비스 변경/차단 | 낮 | 렌더는 1회성 배치 — 산출물 mp4는 영구. 재렌더 필요 시 대체 TTS(로컬 melo-tts 등) |
| 7 | 코스 개편 시 영상과 어긋남 | 중 | MAPPING.md가 계약 문서 — 코스 단계 변경 PR은 MAPPING 갱신 필수(체크리스트化). 대본·영상은 "재료"라 단계 순서 변화에 둔감하게 설계됨 |
| 8 | 연습 영상 신호가 학습 데이터 오염 | — | 이미 차단: practice면 absorb no-op. P4에서 practice_course→practice 강제로 이중 보장 |

## 7. 열린 질문 (사용자 결정 필요)

1. TTS 목소리: 여(SunHi) vs 남(InJoon) — P2 시작 때 샘플 듣고 결정.
2. 영상 화면 톤: 현재 설계는 미니멀(파형+배지). 더 꾸밀지(일러스트 등)는
   v2로 미룸 — 이의 없으면 미니멀 확정.
3. 유튜브 채널: 본 채널 vs 별도 연습용 채널(미등록이면 어디든 무방).

## 8. 검증 총괄 (에이전트가 직접 실행할 것 / 위임)

| 검증 | 방법 | 주체 |
|---|---|---|
| 파서·TTS·타이밍 | 유닛 스모크(합성 대본 → 길이·순서 assert) | Agent |
| mp4 산출 | ffprobe 길이·해상도·오디오 스트림 assert | Agent |
| 웅얼 가청성, 목소리 톤 | 사람 귀 | User |
| STT 미끼 적중 | 리허설 후 세그먼트 덤프 대조 | Agent(덤프)+User(판단) |
| P4 E2E | scratch DB + 실브라우저 (기존 검증 패턴) | Agent |
| 파일럿 | 검수자 1명 코스 1~6 완주 | User |
