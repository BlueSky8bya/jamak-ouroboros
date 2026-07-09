# jamak-ouroboros

유튜브 강연 영상(주 대상: 허경영 강연)의 한국어 자막을 자동 생성 → LLM 교정 → 사람 검수 → 배포하는 end-to-end 파이프라인. 핵심 설계 원칙은 **우로보로스 루프**: 사람이 검수한 결과가 다음 실행의 입력(용어사전, few-shot 교정쌍)으로 되먹임되어 회차가 거듭될수록 정확해진다.

## 아키텍처

```
yt-dlp ingest → faster-whisper STT → 자동자막 교차검증 → Claude 교정 → srt 조립
                     ↑ initial_prompt         ↑ 검수 우선순위      ↑ 용어사전+few-shot
                     └──────────── 우로보로스 DB (SQLite) ←── 사람 검수 diff ──┘
```

- `src/jamak/pipeline/` — ingest, stt, crosscheck, correct, assemble (단계별 1파일)
- `src/jamak/db.py` — Job/Segment/Correction/GlossaryTerm. **DB가 학습 데이터의 원본.** 마크다운 스냅샷은 뷰일 뿐.
- `src/jamak/glossary.py` — DB → whisper prompt / Claude 프롬프트 블록 변환 (루프의 읽기 쪽)
- `src/jamak/seed.py` — 기존 검수 .srt 임포트 (루프의 부트스트랩)
- `data/jobs/<video_id>/` — 영상별 작업 파일 (오디오, stt 캐시, srt). git 제외.
- 각 파이프라인 단계는 캐시/DB 기반으로 재실행 가능(resumable) — 중간 실패 시 같은 명령 재실행.

## 명령

```
uv run jamak doctor              # 환경 점검 (GPU/ffmpeg/API키/DB)
uv run jamak run <youtube-url>   # 전체 파이프라인 → draft .srt
uv run jamak seed-import <dir>   # 검수 완료 .srt 일괄 임포트
uv run jamak export <video_id>   # 최신 단계 기준 .srt 내보내기
```

- LLM 교정에는 `ANTHROPIC_API_KEY` 필요. 없으면 해당 단계 자동 스킵.
- STT는 CUDA 필요 (RTX 4060 Ti 8GB 기준 int8_float16). CPU 폴백은 매우 느림.

## 우로보로스 규칙 (세션 하네스)

1. **검수가 끝나면 반드시 피드백을 흡수한다** — 검수된 자막이 생기면 diff → corrections/glossary 갱신이 실행되어야 다음 회차가 좋아진다. 이 단계를 건너뛴 세션은 미완성이다.
2. **용어사전 후보는 자동 추출되지만 승인은 사람이 한다** — `approved=False` 후보를 `/glossary-review`로 정리. 미승인 용어는 프롬프트에 주입되지 않는다.
3. **정확도는 측정한다** — 파이프라인을 고치면 `/jamak-eval`로 CER 추이를 확인. 숫자가 나빠지면 되돌린다.
4. **학습 데이터를 코드에 하드코딩하지 않는다** — 용어, 교정쌍은 전부 DB. 프롬프트 파일에 어휘 목록을 박아넣지 말 것.

## 컨벤션

- Python 3.12, uv. 의존성 추가는 pyproject.toml → `uv sync`.
- Claude API 코드 수정 시 `claude-api` 스킬 먼저 로드 (모델/파라미터 드리프트 방지).
- 자막 규칙: 줄당 ~18자, 최대 2줄 (config.py 상수).
- 커밋 메시지는 Conventional Commits.
