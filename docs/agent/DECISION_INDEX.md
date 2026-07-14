# Decision Index

| ADR | Status | Area | Decision | Revisit Trigger |
|---|---|---|---|---|
| [ADR-0001](decisions/ADR-0001-pipeline-architecture.md) | Accepted | pipeline | 로컬 Whisper 주 STT + 자동자막 교차검증 + Claude 교정 | 검수 30개+ 축적(파인튜닝), 더 나은 한국어 STT 등장 |
| [ADR-0002](decisions/ADR-0002-db-as-source-of-truth.md) | Accepted | data | SQLite DB = 학습 데이터 유일 원본, 프롬프트는 런타임 조립 | 다중 사용자/원격 검수 |
| [ADR-0003](decisions/ADR-0003-srt-export-no-api-upload.md) | Accepted | delivery | .srt 파일 전달, API 업로드 스코프 밖 | 채널 권한 확보 |
| [ADR-0004](decisions/ADR-0004-whisper-finetune-roadmap.md) | Accepted | stt/ml | 검수 데이터로 Whisper 파인튜닝 로드맵 (hotwords→데이터셋→LoRA) | 검수 오디오 10시간 축적 |
| [ADR-0005](decisions/ADR-0005-local-correction-model-roadmap.md) | Accepted | correction/ml | 교정을 로컬 파인튜닝 소형 LLM으로 점진 이전(번역은 API 유지); 결정적 층+스킵→데이터 축적→LoRA+CER 게이트 | 교정쌍 2~5천 축적 |
| [ADR-0006](decisions/ADR-0006-per-language-subtitle-tracks.md) | Accepted | data/editor | 모든 언어=1급 자막 트랙(Segment.lang, 번역=트랙 시드, 에디터 전 언어 재사용); 랜딩 언어 축 | 번역 트랙 divergence 데이터 확인, 다중 사용자 설계 |
| [ADR-0007](decisions/ADR-0007-deploy-via-tunnel.md) | Accepted | deploy | 1차 배포=터널(Cloudflare Tunnel+Access) 노출 + JAMAK_AUTH 이중화; 로컬 GPU·SQLite·파일 유지 (로컬 전용엔 유효) | ADR-0008로 확장됨 |
| [ADR-0008](decisions/ADR-0008-cloud-app-local-gpu.md) | Accepted | deploy/data | 경로 B: 검수 웹앱 클라우드 상시(Railway) + 전용 Postgres(단일 DB, stt.json→SttBlob); 로컬 GPU 유지, DATABASE_URL 미설정 시 기존 SQLite 그대로 | 파이프라인 클라우드화(경로 C), stt 블롭이 DB 지배 시 오브젝트스토리지, 동시편집 충돌 시 행잠금 |
| [ADR-0009](decisions/ADR-0009-review-modes-and-auto-timing.md) | Accepted | editor/ux | 에디터 내용/타이밍 모드 분리(기본값 상태 파생+탭, 잠금 없음), review_flag(잘 안 들림 단일 플래그), 흘려듣기, 자동 타이밍=absorb→발화스냅+초과분할(reviewed 보존, 프리미티브 조합) | 자동 분할 수정률 높으면 forced alignment(worker), 보류 상시 누적 시 전용 화면 |
| [ADR-0010](decisions/ADR-0010-practice-clone-isolation.md) | Accepted | tutorial/data | 연습 영상은 사용자별 Job 복제 샌드박스(합성 video_id=base~hash, 기준 불변, 초기화=재복제, 코스당 1영상 부분 UNIQUE, bind 시 결함 주입) | 클론 볼륨 증가, 연습 영상 번역 필요, video_id 접미사 가정 확산 |
