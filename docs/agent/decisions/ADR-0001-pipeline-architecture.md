# ADR-0001: 로컬 Whisper + 자동자막 교차검증 + Claude 교정 파이프라인

Status: Accepted
Date: 2026-07-10
Decision Owners: User + Agent-assisted

## Context

허경영 강연(1~2시간, 한국어 + 종교 용어/한자어/경상도 사투리/청중 소음)의 자막을 자동 생성해야 한다. 후보: 유튜브 자동자막 중심, 클라우드 STT, 로컬 Whisper, 즉시 파인튜닝.

## Decision

faster-whisper large-v3 로컬(GPU, int8_float16)을 주 STT로, 유튜브 자동자막은 교차검증(불일치 → 검수 우선순위 플래그) 보조로, Claude API를 문맥 교정으로 사용한다. 파인튜닝은 검수 데이터 축적 후로 미룬다 (M5).

## Rationale

- RTX 4060 Ti 8GB 보유 → 로컬 무료·무제한, 단어 타임스탬프 확보 (자동자막은 타임스탬프 뭉개짐)
- 두 독립 엔진의 불일치 = 저비용 오류 검출 신호
- 고유어휘 오인식은 STT 교체보다 어휘 주입(prompt) + LLM 문맥 교정이 비용 효율적
- 파인튜닝은 초기 데이터 부족 상태에서 과투자

## Consequences

- (+) 영상당 비용 = Claude 교정비만 (수백 원대)
- (-) CUDA/Windows DLL 관리 부담 (CHG-20260710-002)
- (-) CPU 환경 폴백 매우 느림

## Revisit Conditions

- 검수 완료 강연 30개+ 축적 시 파인튜닝 재평가
- whisper 계열보다 한국어 사투리에 유의미하게 강한 STT 등장 시
