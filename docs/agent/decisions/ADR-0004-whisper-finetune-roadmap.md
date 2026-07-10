# ADR-0004: Whisper 파인튜닝 로드맵 (검수 데이터로 STT 자체 개선)

Status: Accepted
Date: 2026-07-10
Decision Owners: User + Agent-assisted
Related: ADR-0001 (파이프라인), ADR-0002 (DB 원본)

## Context

교정은 두 층이다: (1) Whisper가 애초에 잘못 들음 → (2) Claude가 문맥으로 고침. (2)는 영상마다 API 비용이 든다. 검수 데이터가 쌓이면 Whisper를 도메인(허경영 강연: 종교/한자어/경상도 사투리/고유어휘)에 맞게 파인튜닝해 (1)의 오류 자체를 줄일 수 있고, 그러면 (2) 의존도와 API 비용이 함께 내려간다.

## Decision

검수 완료 자막을 STT 학습 코퍼스로 축적한다. 3단계 로드맵:

1. **Zero-cost 즉효 (지금 적용됨)**
   - `initial_prompt` + `hotwords`에 승인된 용어사전 주입 → Whisper 음향 디코더가 도메인 어휘 쪽으로 편향. 학습·API 0.
   - **용어사전 공급원 확장** (`jamak glossary-mine`): 1년치 검수 코퍼스에서 빈도 후보를 결정적으로 뽑고 Claude 1회(일회성 ~$0.06)로 정제해 도메인 어휘를 `approved=True`로 채움. 교정쌍은 기계 초안이 없어 불가하지만 hotwords/prompt는 코퍼스에서 대량 확보. 주의: 이 경로는 사람 `/glossary-review` 승인을 Claude 자동 승인으로 대체 — 소스가 사람이 이미 검수한 코퍼스라 방어 가능하나, 잔여 노이즈는 `/glossary-review`로 사후 정리.
2. **데이터셋 축적 (지금 구축됨)**
   - `jamak export-training-data`: 사람이 검수한 세그먼트를 (오디오 클립, 정답 텍스트) 쌍으로 슬라이스 → `data/training/manifest.jsonl`. 검수할수록 자동 증가.
3. **파인튜닝 (미래, 트리거 도달 시)**
   - HuggingFace `transformers` + `peft`(LoRA)로 Whisper large-v3를 코퍼스에 파인튜닝 → CTranslate2로 변환해 faster-whisper에 로드 (`JAMAK_WHISPER_MODEL`로 교체).
   - RTX 4060 Ti 8GB: LoRA/8bit로 large-v3 가능.

## Decision Drivers

- API 비용 하락 (교정 의존도↓)
- 도메인 정확도 (사투리/고유어휘는 프롬프트 편향만으론 한계)
- 이미 있는 자산(검수 audio+text)을 골수까지 활용

## Trigger (3단계 시작 조건)

- 검수 완료 오디오 **≥ 10시간** 축적 (`export-training-data`의 minutes로 확인). 현재 ~0.13시간.
- 또는 특정 어휘/사투리 오인식이 프롬프트+hotwords+교정으로도 반복될 때.

## Consequences

- (+) 회차가 쌓일수록 STT 자체가 좋아지는 진짜 우로보로스 (교정은 안전망으로 축소)
- (+) 학습은 로컬 GPU → 추가 API 0
- (-) 학습/변환 파이프라인 유지비, 평가(CER 홀드아웃) 필수 — 나빠지면 롤백
- (-) 데이터 편향 주의: 검수본이 특정 화자/주제에 치우치면 일반화 저하

## Validation

- 파인튜닝 후 홀드아웃 검수본으로 CER 측정 (`jamak eval` 확장), base large-v3 대비 개선 확인. 개선 없으면 base 유지.

## Revisit Conditions

- 트리거 도달, 또는 large-v3보다 한국어 사투리에 강한 오픈 STT 등장 시.
