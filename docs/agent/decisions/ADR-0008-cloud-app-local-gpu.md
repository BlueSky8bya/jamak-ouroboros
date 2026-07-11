# ADR-0008: 경로 B — 클라우드 웹앱 + 전용 Postgres (로컬 GPU 유지)

Status: Accepted
Date: 2026-07-12
Decision Owners: User
Relates to: ADR-0007 (터널 방식의 "Revisit" 조건이 발동 — supersede 아님, 확장. 로컬 전용엔 여전히 터널이 유효)

## Context

ADR-0007(터널)은 검수 중 관리자 PC 상시 가동을 요구한다. 실제로 PC 절전/재부팅 시
Cloudflare Error 1033(터널 데몬 부재)로 사이트가 죽는 것을 확인. 검수자가 **관리자 PC와
무관하게** 접속하려면 웹앱을 클라우드에 상시 호스팅해야 한다. 단, 유튜브→자막 생성은
로컬 GPU(faster-whisper, RTX 4060 Ti)에 묶여 있어 그대로 로컬에 남는다.

저장 규모: 앞으로 1~2시간 영상 수백 개. 로컬 디스크에 수십 GB를 계속 쌓기보다
관리형 DB로 옮기고, 무료 한도 초과분만 종량 과금하는 편이 낫다(사용자 결정).

## Decision

**검수 웹앱을 클라우드에 상시 배포하고, 데이터는 전용 Postgres 하나로 통일한다.**

- **호스트: Railway** (앱 + Postgres 한 프로젝트, GitHub 푸시 자동배포, 종량제).
  코드는 `DATABASE_URL`만 바꾸면 Neon/Render 등으로 이전 가능하게 작성 → 락인 없음.
- **단일 DB 아키텍처**: 로컬 파이프라인과 클라우드 앱이 **같은 Postgres**를 본다.
  로컬은 `DATABASE_URL`을 클라우드로 지정한 뒤 `jamak run` → 세그먼트를 클라우드 DB에 직접
  기록. 별도 push/sync 명령 불필요.
- **stt.json → DB(SttBlob 테이블)**: 워드맵(`/words`)·타이밍 다듬기(`/tighten`)가
  로컬 파일 없이 클라우드에서 동작. 오브젝트스토리지(R2/S3) 도입 보류 — 단일 데이터스토어 유지.
- **audio.wav는 로컬에만.** 기본 삭제(ADR-0007 운영 메모) → 로컬에 대용량 안 쌓임.
- **엔진 분기**: `DATABASE_URL` 있으면 Postgres(psycopg), 없으면 기존 SQLite. 로컬 개발·
  터널 방식(ADR-0007)은 `DATABASE_URL` 미설정으로 **100% 그대로** 동작.
- **이관**: `jamak migrate-to-cloud` 로 로컬 SQLite(+stt.json)를 1회 복사. 소스는 읽기전용,
  PK id 보존, PG 시퀀스 리셋.
- **인증**: 기존 세션 쿠키(JAMAK_ADMINS/NAMES + 역할별 비번). 관리자 전용 파이프라인
  엔드포인트 게이팅 그대로. 시크릿은 Railway 환경변수로만.

## Consequences

- (+) 검수자는 **관리자 PC가 꺼져 있어도** 접속·검수·내보내기 가능.
- (+) 로컬 디스크에 수십 GB 안 쌓임(자막 데이터는 관리형 DB, audio는 삭제).
- (+) 스토리지 종량: 무료 초과분만 과금(Railway/Neon 모두 ~$0.35/GB급).
- (+) GitHub 푸시 → 자동 재배포(관리자가 매번 프로세스 살릴 필요 없음).
- (-) 앱 상시 호스팅 고정/종량 비용 발생(월 $5~9 수준).
- (-) 유튜브→자막 생성은 여전히 로컬 GPU 필요(관리자가 로컬에서 `jamak run`).
- (-) 클라우드 인스턴스의 retranscribe/repair는 GPU 없음 → 관리자는 STT를 **로컬에서**
  수행(문서화). 클라우드 버튼 사용 시 실패(후속: 클라우드에서 GPU 작업 UI 숨김/가드).
- (-) SQLite→PG로 동시성은 개선되나 per-(job,lang) idx 경합 잠금은 여전히 이연(translate-audit 항목).

## Revisit Conditions

- 파이프라인까지 클라우드로 → 경로 C(Modal/RunPod GPU 워커).
- stt.json 블롭이 DB 용량을 지배 → 오브젝트스토리지로 분리.
- 동시 편집 충돌 발생 → per-(job,lang) 행 잠금 도입.
