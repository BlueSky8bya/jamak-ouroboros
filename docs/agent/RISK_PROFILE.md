# Risk Profile

Default: GENERAL

## Active Profiles

- GENERAL
- ML_EVALUATION

## Detection Rationale

- ML_EVALUATION: 프로젝트의 핵심 가치가 "회차별 CER 하락"이라는 측정 가능한 정확도 지표. 평가 정규화 규칙, 홀드아웃 처리, few-shot 선별 로직 변경은 지표를 조용히 왜곡할 수 있다 → 평가 관련 변경은 L2 취급, 기준 변경은 ADR.
- 학습 데이터(`data/jamak.db`, `data/seeds/`)는 재생성 불가 자산 — DESTRUCTIVE_DATA 프로파일 대신 protected_paths + Critical Invariant로 관리 (production migration 개념이 없는 로컬 SQLite이므로 전체 프로파일은 과함).

## Inactive Profiles Reviewed

- RESEARCH: 학술 재현성 목적 아님 — Not detected
- HEALTH / FINANCE / PAYMENTS / AUTH: Not detected
- PRIVACY: 처리 데이터가 공개 유튜브 강연 — Not detected (단, 검수 코퍼스 공개 여부는 ISSUE-001로 별도 관리)
- SECURITY: 일반 위생 수준 (API 키는 env로만, 저장소·문서에 기록 금지)
- PRODUCTION_INFRA: 로컬 실행 전용 — Not detected

## Re-evaluation Triggers

- 검수 웹앱을 로컬 밖으로 배포 (→ SECURITY/AUTH)
- 타인의 검수 노동력 참여, 개인정보 수집 (→ PRIVACY)
- Whisper 파인튜닝 도입 (→ ML_EVALUATION 규칙 강화: 데이터 분할, 리키지 체크)
