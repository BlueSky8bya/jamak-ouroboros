# ADR-0007: 검수 웹앱 배포 = 터널 노출 + 소수 검수자 로그인

Status: Accepted
Date: 2026-07-11
Decision Owners: User

## Context

검수자 몇 명이 URL로 접속해 검수하길 원함. 현재 앱은 로컬 단일 사용자 전제:
GPU STT(faster-whisper, RTX 4060 Ti), 로컬 파일 저장소(audio.wav·stt.json·jamak.db),
SQLite(단일 writer), 인증 없음. 완전 클라우드(GPU 포함)는 비용·작업 최대이고,
클라우드 웹앱+로컬 GPU 분리(B)는 SQLite→PG·파일→오브젝트스토리지·인증 리팩터가 필요한 큰 작업.

## Decision

**1차 배포는 터널 방식.** 로컬 구조(GPU·SQLite·파일)를 그대로 두고, 로컬에서
`jamak serve`(127.0.0.1:8710)를 돌린 뒤 그 앞에 터널을 세워 URL로 노출한다.

- **권장 경로**: Cloudflare Tunnel + Cloudflare Access(이메일 OTP)로 지정 검수자만 입장.
- **앱 자체 인증**(방어 이중화): `JAMAK_AUTH="user:pw,..."` 환경변수 → HTTP Basic 미들웨어.
  미설정 시 무인증(로컬 개발). 외부 노출 시 필수.
- `serve`에 `--host` 옵션 추가(기본 127.0.0.1 유지; 비-로컬 바인딩 + JAMAK_AUTH 미설정이면 경고).
- 절차·운영은 `docs/agent/deployment.md`.

## Consequences

- (+) 오늘 배포 가능, 무료, 인프라 변경 0, GPU·데이터 로컬 유지.
- (+) 학습 데이터(jamak.db·seeds)가 로컬에 남아 유출/이전 리스크 없음.
- (-) 검수 중 로컬 PC 상시 가동 필요(서비스화로 완화).
- (-) SQLite 단일 writer: 소수 검수자·서로 다른 영상은 `busy_timeout=30s`로 안전하나,
  **같은 영상 구조 편집 동시성**은 미보장(idx 경합 — 영상 분담으로 회피).

## Revisit Conditions

- 검수자 증가 / 상시 가동 부담 / 동시 편집 충돌 발생 → 경로 B(클라우드 웹앱 + 로컬 GPU):
  SQLite→Postgres, 파일→오브젝트스토리지(R2/S3), 세션 인증, per-(job,lang) 잠금.
  → **발동됨: ADR-0008(Railway + 전용 Postgres). 이 ADR은 로컬 전용 배포에 여전히 유효.**
- 파이프라인까지 클라우드로 옮길 필요 → 경로 C(Modal/RunPod GPU 워커).
- 동시성 잠금은 translate-audit 감사가 남긴 이연 항목과 함께 그때 처리.
