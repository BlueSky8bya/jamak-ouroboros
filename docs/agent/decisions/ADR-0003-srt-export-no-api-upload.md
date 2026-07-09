# ADR-0003: 산출물은 .srt 파일 전달 (유튜브 API 업로드 안 함)

Status: Accepted
Date: 2026-07-10
Decision Owners: User

## Context

자막을 올릴 채널이 제3자(허경영 공식) 소유. 유튜브는 2020년 커뮤니티 자막 기여를 폐지 → 타인 채널 영상에 API(captions.insert) 자막 업로드 불가.

## Decision

파이프라인 최종 산출물은 검수 완료 `.srt`(필요시 `.vtt`) 파일. 채널 편집자에게 파일로 전달한다. 업로드 자동화는 스코프 밖.

## Consequences

- (+) OAuth/채널 권한 관리 불필요
- (-) 배포 마지막 단계는 수동 (편집자 전달)

## Revisit Conditions

- 채널 관리 권한 확보 시 (captions.insert 자동화 = M5+ 후보)
- 자체 채널 재업로드(하드섭) 전략 채택 시
