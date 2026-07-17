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
| [ADR-0009](decisions/ADR-0009-review-modes-and-auto-timing.md) | Accepted (자동 타이밍만 ADR-0012로 폐지) | editor/ux | 에디터 내용/타이밍 모드 분리(기본값 상태 파생+탭, 잠금 없음), review_flag(잘 안 들림 단일 플래그), 흘려듣기, 자동 타이밍=absorb→발화스냅+초과분할(reviewed 보존, 프리미티브 조합) | 자동 분할 수정률 높으면 forced alignment(worker), 보류 상시 누적 시 전용 화면 |
| [ADR-0010](decisions/ADR-0010-practice-clone-isolation.md) | Accepted | tutorial/data | 연습 영상은 사용자별 Job 복제 샌드박스(합성 video_id=base~hash, 기준 불변, 초기화=재복제, 코스당 1영상 부분 UNIQUE, bind 시 결함 주입) | 클론 볼륨 증가, 연습 영상 번역 필요, video_id 접미사 가정 확산 |
| [ADR-0011](decisions/ADR-0011-hanja-pipeline-order.md) | Accepted | correction/editor/learning | 한자어 3층 분리: API 맞춤법(1차)=고유어 분절/표기 **정규화만**, 漢 한자 채우기(2차)=무-API 결정적 **병기**, 학습(3차)=사람이 단 `단어(漢字)` 감지해 사전 등록(기본 tier=common). 판단만 API, 치환은 무료 | 1층 정규화가 오교정 유발, HanjaTerm 수천 종(정규식 성능), 3층 오등록률 높음 |
| [ADR-0012](decisions/ADR-0012-drop-auto-timing.md) | Accepted | editor/timing | ✨ 타이밍 자동 정리 폐지 (실측: 셀 66%·검수완료 영상 98% 변경, 근거 약한 18% 중 544셀도 변경. 시간비례 분할이라 사람이 고칠수록 악화). 실검수 버튼 제거 + 실영상 410 차단, 연습은 재렌더까지 유지 | 워커에 diarization 도입 시, ✂ 무음 다듬기에서 같은 불만 관측 시 |
| [ADR-0013](decisions/ADR-0013-proper-noun-official-spelling.md) | Accepted | translate/glossary | 고유명사 표기 3단: **단체 공식 표기 1순위**(허경영=Huh Kyung-young · 하늘궁=Heaven Palace · 불로유=Boolloyu · 백궁=White Heaven) → 없으면 음역(첫 등장 1회 괄호설명) → 의역 금지. 로마자 표기법 기계 적용은 오히려 틀림(Heo Gyeong-yeong은 미사용). 규칙 아닌 **목록**을 `GlossaryTerm.official`(JSON)에 담아 번역 프롬프트에 주입 | 공식 사이트 본문 확인 시 정정(백궁 White Heaven/White Heaven Palace 갈림), ja/zh 공식 표기 확보 시 |
| [ADR-0014](decisions/ADR-0014-modifier-split-alt-move-ctrl-text.md) | Accepted | editor/ux, tutorial | 조합키에 뜻 하나씩: **Alt = 이동**(←→ 영상 3초/10초 · ↑↓ 자막 · Z 작업 되돌리기), **Ctrl = 글자**(←→ 낱말 점프 복원 · Z 글자 되돌리기 · Enter 나누기). 탐색을 Ctrl→Alt로 옮겨 낱말 점프와의 충돌 해소 — 글상자 안에서도 탐색 가능. 나레이션이 모순된 두 규칙에서 "알트와 화살표는 모두 이동" 하나로 축소(고령 대상 실질 이유). 연습2 재렌더 필요 | 실기에서 Alt+←가 크롬 뒤로가기 유발 시 즉시(비화살표로 이전), 오른쪽 Alt(한자 키) 미동작 신고 반복 시 |
| [ADR-0015](decisions/ADR-0015-hanja-hint-from-spellcheck.md) | Accepted | correction/editor/learning | 한자 병기 힌트: **맞춤법 패스(1층 API)가 문맥으로 병기 후보를 기록**(special 단일자만, 텍스트는 안 바꿈)→ Segment.hanja_hints/LlmCache.hanja 저장 → **漢 채우기(2층 무-API)가 규칙 C로 소비**. 사전만으론 문맥 몰라 못 채우던 단독 1글자(貪·嗔·癡)를 API 추가 0으로 병기. ADR-0011 1층 역할 확장(보강). 오병기 최소=special만·낱말 존재로 무효화 | 1글자 과병기 시 규칙10 강화/tier 강등, 다자어 동형이의 필요 시 범위 확대 |
