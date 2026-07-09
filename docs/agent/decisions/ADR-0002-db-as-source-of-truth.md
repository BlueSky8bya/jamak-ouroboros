# ADR-0002: SQLite DB가 학습 데이터의 유일한 원본

Status: Accepted
Date: 2026-07-10
Decision Owners: User + Agent-assisted

## Context

우로보로스 루프의 학습 자산(용어사전, 교정쌍, 세그먼트별 단계 텍스트)을 어디에 둘 것인가. 후보: 마크다운 파일, 프롬프트 파일 내 하드코딩, SQLite.

## Decision

`data/jamak.db` (SQLite + SQLModel)가 유일한 원본. 프롬프트는 실행 시점에 DB에서 조립(`glossary.py`). 마크다운은 뷰/스냅샷으로만 허용.

## Rationale

- 루프가 돌 때마다 데이터가 자동 갱신·집계돼야 함 (빈도 카운트, 승인 플래그) — 파일 편집으로는 드리프트 필연
- 세그먼트 4단계 텍스트 나란히 보존 → diff 학습이 쿼리 한 번
- 단일 사용자 로컬 → 서버 DB 불필요

## Consequences

- (+) 학습 데이터와 코드의 분리, 프롬프트 하드코딩 금지 강제 가능
- (-) DB 파일이 재생성 불가 자산이 됨 → protected_paths 지정, 백업 정책 필요 (Open Decision)

## Revisit Conditions

- 다중 사용자/원격 검수 도입 시 (서버 DB로 마이그레이션)
