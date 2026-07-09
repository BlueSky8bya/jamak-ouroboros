# Project Map

| Path | Role | Main Entry | Input → Output | Risk |
|---|---|---|---|---|
| `src/jamak/cli.py` | CLI 진입점 (doctor/run/seed-import/export) | `app` (typer) | 명령 → 파이프라인 실행 | GENERAL |
| `src/jamak/config.py` | 경로·상수 (자막 규칙, 모델 설정) | - | env → 설정 | GENERAL |
| `src/jamak/db.py` | 우로보로스 저장소 스키마 (Job/Segment/Correction/GlossaryTerm) | `get_session` | - | **학습 데이터 원본 — 파괴 금지** |
| `src/jamak/glossary.py` | DB → whisper prompt / Claude 프롬프트 블록 | - | DB → 프롬프트 텍스트 | ML_EVALUATION |
| `src/jamak/seed.py` | 검수 완료 .srt/.txt 임포트 (루프 부트스트랩) | `import_seeds` | 파일 → glossary 후보 | GENERAL |
| `src/jamak/pipeline/ingest.py` | [1] yt-dlp 다운로드 (오디오+자동자막+메타) | `ingest` | URL → wav/json3 | GENERAL |
| `src/jamak/pipeline/stt.py` | [2] faster-whisper STT + CUDA DLL 로딩 | `transcribe` | wav → 세그먼트(단어 타임스탬프) | GENERAL |
| `src/jamak/pipeline/crosscheck.py` | [3] whisper vs 자동자막 비교 → flagged | `crosscheck` | 두 텍스트 → 불일치 플래그 | ML_EVALUATION |
| `src/jamak/pipeline/correct.py` | [4] Claude 교정 (용어사전+few-shot 주입) | `correct_job` | 세그먼트 → 교정 텍스트 | ML_EVALUATION |
| `src/jamak/pipeline/assemble.py` | [5] 자막 규칙 적용 → .srt/.vtt | `to_srt` | 세그먼트 → srt | GENERAL |
| `src/jamak/web/` | [M3 예정] 검수 웹앱 (FastAPI+React) | - | - | GENERAL |
| `data/jobs/<video_id>/` | 영상별 작업 캐시 (git 제외) | - | 삭제 시 해당 영상 재계산 | GENERAL |
| `data/seeds/` | 검수 완료 코퍼스 | - | seed-import 입력 | **원본 — 삭제 금지** |
| `data/jamak.db` | SQLite 저장소 | - | - | **원본 — 삭제 금지** |
| `.claude/skills/` | Claude Code 스킬 4개 (jamak-run/seed-import/glossary-review/jamak-eval) | - | - | GENERAL |
| `docs/agent/` | Agent Harness 문서 | - | - | GENERAL |

## Verification commands

- 환경: `uv run jamak doctor`
- E2E: `uv run jamak run <url>` (테스트 영상: lFuxxOlgl5Y, 9분)
- 정확도: `/jamak-eval` 스킬 (검수본 존재 시)
