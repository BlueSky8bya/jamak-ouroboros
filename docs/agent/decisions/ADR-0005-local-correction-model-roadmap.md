# ADR-0005: 로컬 파인튜닝 교정 모델 로드맵 (교정 API 대체, 번역은 API 유지)

Status: Accepted
Date: 2026-07-10
Decision Owners: User + Agent-assisted
Related: ADR-0001 (파이프라인), ADR-0002 (DB 원본), ADR-0004 (whisper 파인튜닝)

## Context

파이프라인에서 Claude API를 쓰는 곳은 정확히 3개: 교정(매 영상), 번역(언어별), 용어 마이닝(일회성). 이 중 **교정**이 반복 비용의 핵심이다.

교정 작업을 분해하면 대부분은 이미 API 없이 결정적으로 처리된다:
- 잡음/청중응답 → 규칙 필터 (`noise.py`)
- gap/echo 처리, 한쪽 비었을 때 whisper↔youtube 택1 → `crosscheck.py`
- 알려진 오인식(축제법→축지법) → pre-pass 무료 치환 (`correct.load_prepass_pairs`)
- 저위험 세그먼트(플래그 없음 + 도메인어 없음) → LLM 스킵 (`correct._needs_llm`, 실측 ~40% 절감)

진짜 LM이 필요한 잔여는 **문맥 의존 오인식 교정 + 불일치 자연스런 병합**뿐이다. 이 잔여는 좁고 패턴적이라 소형 로컬 모델이 파인튜닝으로 충분히 감당할 수 있는 범위다.

핵심 제약: 이 작업은 "구어체·사투리 유지, 대명사·지시어 안 건드림" 같은 **하지 마 제약**이 있다. Generic 한국어 교정(GEC) 모델은 사투리를 표준어로 정규화해서 오히려 프로젝트 철학을 위반한다. 따라서 generic 모델은 부적합하고, **검수 데이터로 파인튜닝**해야 한다 — 학습 타깃이 "사투리 살린 사람 교정본"이므로 모델이 제약을 데이터로 학습한다.

## Decision

교정을 점진적으로 로컬 파인튜닝 모델로 이전한다. **번역은 추론·유창성·뉘앙스가 필요하므로 API(강한 모델) 유지.**

단계 로드맵 (데이터 게이트):

1. **Phase 0 — 결정적 층 최대화 (진행 중)**
   - pre-pass 변형 치환 + `_needs_llm` 스킵으로 LLM 물량 축소. 검수 흡수할수록 무료층 증가. 모델 0.
2. **Phase 1 — 학습 데이터 축적 (지금 구축됨)**
   - `jamak export-correction-data`: 검수 완료 세그먼트에서 (whisper 초안, youtube 참고, 사람 최종) 쌍을 `data/training/corrections/manifest.jsonl`로 export. changed(교정)+unchanged(유지) 둘 다 — 유지 쌍이 "안 고치는 법"을 가르침. gap/echo 세그먼트 제외.
3. **Phase 2 — 파인튜닝 + 라우팅 (트리거 도달 시)**
   - 소형 한국어 instruction LLM(EXAONE 3.5 2.4B/7.8B, Qwen2.5 3B/7B, Gemma-2 2B 등)을 교정쌍으로 LoRA/QLoRA 파인튜닝. RTX 4060 Ti 8GB로 3~7B 양자화 추론 + 3B QLoRA 학습 가능. llama.cpp(GGUF q4) 서빙, whisper와 순차라 메모리 안 겹침.
   - `jamak eval`(CER)로 게이트: **로컬 CER ≤ Claude CER**일 때만 교정 라우팅을 로컬로 전환.
   - **하이브리드**: 로컬이 쉬운 것, uncertain·저신뢰만 Claude 또는 사람 에스컬레이션 (안전망 유지).
4. **Phase 3 — 지속 개선**
   - 검수 쌓일 때마다 재학습. 교정 로컬화 완료 → API = 번역 전용.

## Decision Drivers

- 교정 API 비용을 0으로 (반복 비용 제거)
- 도메인·사투리 특화 (파인튜닝만이 "하지 마 제약"을 지킴)
- 이미 있는 자산(검수 교정쌍) 골수까지 활용 — ADR-0004(audio)와 대칭
- 번역은 성격이 달라 API 유지가 합리적

## Trigger (Phase 2 시작 조건)

- 교정쌍 **≥ ~2,000~5,000** 축적 (`export-correction-data`의 pairs). 현재 113 (완료본 1개 기준).
- 또는 특정 오인식 유형이 pre-pass+스킵으로도 반복될 때.

## Consequences

- (+) 회차 쌓일수록 교정이 API 없이 좋아지는 우로보로스 (교정=STT와 함께 로컬화)
- (+) 학습·추론 로컬 GPU → 추가 API 0
- (-) 콜드스타트: 데이터 부족하면 로컬이 Claude 못 이김 → 반드시 데이터 게이트 + CER 게이트
- (-) 과교정/사투리 정규화 위험 → generic 모델 금지, 파인튜닝만, CER 홀드아웃 필수
- (-) 학습·양자화·서빙·버전 유지비, 하이브리드 라우팅 복잡도

## Validation

- 파인튜닝 후 홀드아웃 검수본으로 CER 측정(`jamak eval`), raw whisper·Claude 교정과 3자 비교. 로컬이 Claude 이하 CER + 제약(사투리/대명사) 위반 없을 때만 채택. 아니면 Claude 유지.

## Revisit Conditions

- 트리거 도달, 또는 이 태스크에 강한 오픈 한국어 소형 모델 등장 시.
