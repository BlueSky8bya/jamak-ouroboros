# ACTIVE PLAN — 언어별 독립 자막 트랙 (ADR-0006)

Status: In progress
Started: 2026-07-11
Owner: User + Agent

목표: 모든 언어를 1급 자막 트랙(자기만의 분할/병합/타이밍)으로. 기존 에디터를 전 언어에 재사용.

## 불변 제약
- `data/jamak.db` 기존 검수 데이터 파괴 금지 — 전부 `ko` 트랙으로 보존. 마이그레이션은 추가형만.
- 각 단계는 앱이 계속 동작하는 상태로 커밋(반쯤 깨진 상태 금지).
- 공유 DB: 사용자가 실시간 검수 중일 수 있음 — 실 데이터 쓰기 검증 최소화.

## Phase 1 — 스키마 (추가형, 무해)
- [x] `Segment.lang: str = "ko"` 컬럼 + `_ensure_columns` 마이그레이션(DEFAULT 'ko'). 기존 행 전부 ko.
- [ ] `Track` 테이블: `(id, job_id, lang, timing_done, created_at)`, unique(job_id,lang). (Phase 2에서 배선)
- 검증: 서버 기동·기존 세그먼트 로드·현행 앱 무변화.

## Phase 2 — lazy-fork 트랙 (DB 최적화 반영)
DB 중복 최소화: 번역은 **기본 ko 구조·타이밍 상속**(`Translation` 행 = 텍스트만, 세그먼트 복제 없음). 언어별로 **다른 분할/타이밍이 필요할 때만** 그 (job,lang)을 **fork** → 자기 세그먼트로 독립.
- [x] `Track(job_id, lang, forked, timing_done)` 테이블.
- [x] 이웃/idx-shift 쿼리 전부 lang-aware(`_next/_prev`, split·merge·delete·redistribute) → 트랙 간 idx 오염 방지. (ko-only 데이터엔 no-op)
- [x] `get_segments?lang=`(기본 ko), `POST /fork-track?lang=` (ko 복사 + 번역 텍스트로 lang 세그먼트 생성, Track.forked=true, 멱등, API 0).
- [x] `list_jobs` 카운트 ko 전용.
- [x] 검증: lFux en fork→124 세그먼트(ko 타이밍+en 텍스트), en split→ko 124·idx 온전, 정리 완료(비-ko 삭제). 앱 정상.
- [x] **Phase 2b — ko 격리 가드 완료·검증**: confirm-safe/replace/restore = lang 파라미터(기본 ko); retranscribe·make_translations·get_translations·repair·tighten·export·feedback.absorb = `lang=="ko"` 스코프; export는 fork면 lang 세그먼트 직접·아니면 ko+번역. 검증: fork 영속 시 list_jobs=124(ko만), replace?lang=en=67곳(en만), **ko 텍스트 불변**, 정리 완료. fork를 UI 노출해도 안전.
- [ ] `Job.timing_done`(ko) → `Track` 이관; timing 토글 (job,lang)별. (Phase 3~4)

## Phase 3 — 에디터가 임의 트랙 편집 [완료·검증]
- [x] `get_segments?lang=`로 현재 트랙 로드(`fetchSegments(videoId, lang)`, lang 바뀌면 재fetch). 모든 refetch/restore/replace에 lang 전달.
- [x] lang≠ko & 미포크 → TranslateReview + **`✂ 이 언어를 따로 분할·타이밍 편집` fork 버튼**. 포크되면 그 언어 세그먼트를 **같은 Row 에디터**로 편집(분할·병합·삭제·타이밍·미리보기 전부 재사용).
- [x] ko 전용 도구 숨김(비-ko): WordMap/발화맞춤(words=[]), 무음다듬기·복구채우기·안심확인·학습(tools), 타이밍토글. sources/safe/suspect는 비-ko에서 자연히 빈값.
- [x] `koComplete`를 prop으로(현재 트랙이 아니라 ko 트랙 완료 기준으로 언어 잠금). 미리보기 오버레이 = 포크/ko면 세그먼트 텍스트.
- [x] 검증(lFux): en 전환→fork버튼→클릭→**124 영어 행**("It's recorded..."), 도구 숨김. ja도 동일(124 일본어 행). ko 불변(124)·ko 복귀 정상. 테스트 fork 정리.

## Phase 4 — 랜딩을 언어 축으로
- 언어 선택 → (영상×언어) 트랙 카드. 단계 태그: 텍스트 검수중/완료, 타이밍 작업중/완료.
- 트랙 기준 필터·정렬·통계.

## Phase 5 — 내보내기·우로보로스
- export는 선택 lang 트랙 세그먼트 직접 사용(이미 lang 태그) + gap-join per track.
- 교정쌍·용어 학습은 ko 유지. 번역 few-shot(`translation_examples`)는 트랙 reviewed에서.

## 위험·주의
- 세그먼트 쿼리 회귀(전수 lang 반영). 단계별 검증 필수.
- ko↔번역 sync: 트랙 갈라진 뒤엔 시간 겹침 기반 "원문 바뀜" 신호만.
- **fork 영속 금지(현재)**: ko 집계 엔드포인트 가드 전엔 fork 세그먼트가 남으면 ko가 오염됨. fork 엔드포인트는 UI 미노출 + 테스트는 정리. Phase 2b 가드 후 노출.

## 사용자 제기 사항 (별도 반영 예정)
- **배포(URL 실서비스)**: 현재 로컬 SQLite + 로컬 GPU whisper. 실배포 = (a) 프론트/백엔드 호스팅(백엔드는 whisper GPU 필요 → GPU 인스턴스 또는 STT를 큐/워커로 분리), (b) DB SQLite→Postgres(다중 사용자 동시 쓰기), (c) 인증·작업 잠금(동시 검수 충돌 방지 — 이미 겪음), (d) 오디오/stt.json 등 파일은 오브젝트 스토리지. ADR-0002 revisit(다중 사용자) + ADR-0006 다음 단계. → 별도 ADR 필요.
- **언어별 파인튜닝**: STT는 ko 소스 전용(오디오=한국어). 교정/문맥 검토는 ko. 번역 파인튜닝은 언어별(`translation_examples` 이미 lang별). 트랙 모델이 언어별 학습 데이터 분리를 자연히 지원.
- **DB 용량 최적화**: (1) 번역 lazy-fork로 세그먼트 중복 회피(적용). (2) `LlmCache`·`Translation` source_hash로 재계산/중복 저장 회피(기존). (3) 파인튜닝 데이터는 원본 재파생 가능한 건 저장 안 함(오디오·stt.json은 job_dir 파일; DB엔 메타·교정쌍·용어만). (4) 대량 텍스트 중복(text_whisper/llm/final) 검토 — 대부분 동일하면 diff/참조화 고려(추후).
