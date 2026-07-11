# ACTIVE PLAN — 경로 B: 클라우드 웹앱 + 전용 Postgres (ADR-0007 후속)

Status: Code complete — 사용자 Railway 셋업·이관 실행 대기 (PG 엔드투엔드 NOT VERIFIED: 로컬 Docker/PG 없음)
Started: 2026-07-12
Owner: User + Agent
Host 결정: **Railway** (앱 + Postgres 한 프로젝트, 깃헙 자동배포, 종량제). 코드는 `DATABASE_URL`만 바꾸면 Neon/Render 등으로 이전 가능하게 짠다.

(이전 플랜 = 언어별 독립 자막 트랙 ADR-0006, 완료 → git 이력·DECISION_INDEX 참조.)

목표: 검수 웹앱을 클라우드에 상시 호스팅 → **검수자는 관리자 PC가 꺼져 있어도 접속·검수·내보내기**. 유튜브→자막 생성(로컬 GPU STT)만 관리자 PC 필요.

## 아키텍처 (단일 DB)

```
로컬 GPU 파이프라인 ──STT/교정──┐
   (DATABASE_URL=클라우드)      ├─→ [Railway Postgres] ←─ 검수앱(Railway 상시) ←─ 검수자(PC 꺼도 OK)
stt.json → SttBlob(DB) ────────┘
```

- 로컬·클라우드 앱이 **같은 클라우드 Postgres 하나**를 봄 → 별도 sync/push 명령 불필요.
- 로컬은 `DATABASE_URL` 설정 후 `jamak run` → 세그먼트 + stt.json 블롭을 클라우드 DB에 직접 씀. `audio.wav`는 로컬에만(안 올림, 기본 삭제).
- **stt.json → DB(text)**: 오브젝트스토리지 불필요. 워드맵(`/words`)·타이밍다듬기(`/tighten`)가 클라우드에서 동작.

## 불변 제약
- 로컬 `data/jamak.db` 파괴 금지 — 이관은 **읽기만**. 마이그레이션은 로컬→클라우드 단방향 복사.
- 각 단계는 앱이 계속 동작하는 상태로 커밋(반쯤 깨진 상태 금지). SQLite 로컬 경로는 계속 동작해야 함(`DATABASE_URL` 없으면 기존과 100% 동일).
- 시크릿(`ANTHROPIC_API_KEY`, `JAMAK_*_PASSWORD`, `JAMAK_SECRET`, `DATABASE_URL`)은 호스트 환경변수로만. 프론트 번들·레포에 절대 넣지 않음.

## Phase 1 — DB 레이어 PG 대응 (무해, 로컬 SQLite 불변)
- [ ] `get_engine()`: `DATABASE_URL` 있으면 Postgres(`postgresql+psycopg://`, `pool_pre_ping`), 없으면 기존 SQLite. `postgres://`·`postgresql://` → `+psycopg` 정규화.
- [ ] `SttBlob` 테이블 `(id, job_id unique fk, data: str, created_at)` + `save_stt_blob`/`load_stt_blob` 헬퍼.
- [ ] `_ensure_columns` dialect 인지(PG `BOOLEAN DEFAULT false`; 신규 PG DB는 create_all이 전부 만들어 ALTER는 no-op).
- [ ] `psycopg[binary]>=3.2` base 의존성 추가. (faster-whisper=ctranslate2 경량, cuda extra는 optional → 클라우드 이미지 가벼움)
- 검증: `DATABASE_URL` 없이 기존 SQLite 앱 무변화. 임시 DB로 엔진 분기 스모크.

## Phase 2 — stt.json → DB 블롭
- [ ] stt.json 재생성 3곳(cli `run`, app `retranscribe`, app `repair-stt`)에서 `save_stt_blob` 동기화.
- [ ] `/words`·`/tighten`: `load_stt_blob` 우선, 없으면 로컬 파일 폴백(로컬 개발 유지).
- 검증: 로컬 파일 지워도 블롭으로 워드맵 로드. 임시 DB로.

## Phase 3 — `jamak migrate-to-cloud`
- [ ] 로컬 SQLite → `DATABASE_URL` 대상. 모든 테이블 PK id 보존 복사, PG 시퀀스 setval 리셋.
- [ ] 기존 `data/jobs/*/stt.json` → SttBlob 임포트.
- 검증: 이관 후 클라우드에서 3영상 로드·세그먼트 수·timing_done·번역 일치. 로컬 원본 무변화(읽기전용).

## Phase 4 — Railway 배포 파일
- [ ] 멀티스테이지 `Dockerfile`(node로 frontend build → python serve). base 의존성만(cuda extra 제외).
- [ ] serve `--host 0.0.0.0 --port $PORT`. `.dockerignore`(data/, node_modules, .git). `railway.json`(선택).
- [ ] 쿠키 `secure=True` 이미 설정됨(HTTPS 도메인).
- 검증: 로컬 `docker build` 통과 + 컨테이너 기동 → `/api/me` 200.

## Phase 5 — 문서
- [ ] `deployment.md` 경로 B 절 + Railway 스텝바이스텝(env, 로컬 `DATABASE_URL`로 파이프라인, 배포).
- [ ] ADR-0007 "future"→ 경로 B Accepted 갱신(supersede 아님, 확장). CURRENT_STATE 갱신.

## 되돌리기
`DATABASE_URL` 미설정 = 전부 기존 로컬 SQLite 경로. 클라우드는 추가 레이어일 뿐, 로컬 워크플로 파괴 없음.
