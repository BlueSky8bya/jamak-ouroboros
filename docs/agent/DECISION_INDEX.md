# Decision Index

| ADR | Status | Area | Decision | Revisit Trigger |
|---|---|---|---|---|
| [ADR-0001](decisions/ADR-0001-pipeline-architecture.md) | Accepted | pipeline | 로컬 Whisper 주 STT + 자동자막 교차검증 + Claude 교정 | 검수 30개+ 축적(파인튜닝), 더 나은 한국어 STT 등장 |
| [ADR-0002](decisions/ADR-0002-db-as-source-of-truth.md) | Accepted | data | SQLite DB = 학습 데이터 유일 원본, 프롬프트는 런타임 조립 | 다중 사용자/원격 검수 |
| [ADR-0003](decisions/ADR-0003-srt-export-no-api-upload.md) | Accepted | delivery | .srt 파일 전달, API 업로드 스코프 밖 | 채널 권한 확보 |
| [ADR-0004](decisions/ADR-0004-whisper-finetune-roadmap.md) | Accepted | stt/ml | 검수 데이터로 Whisper 파인튜닝 로드맵 (hotwords→데이터셋→LoRA) | 검수 오디오 10시간 축적 |
| [ADR-0005](decisions/ADR-0005-local-correction-model-roadmap.md) | Accepted | correction/ml | 교정을 로컬 파인튜닝 소형 LLM으로 점진 이전(번역은 API 유지); 결정적 층+스킵→데이터 축적→LoRA+CER 게이트 | 교정쌍 2~5천 축적 |
| [ADR-0006](decisions/ADR-0006-per-language-subtitle-tracks.md) | Accepted | data/editor | 모든 언어=1급 자막 트랙(Segment.lang, 번역=트랙 시드, 에디터 전 언어 재사용); 랜딩 언어 축 | 번역 트랙 divergence 데이터 확인, 다중 사용자 설계 |
