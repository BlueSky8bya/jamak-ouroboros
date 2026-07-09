# jamak-ouroboros

유튜브 강연 영상의 한국어 자막을 자동 생성하고, 사람 검수 결과를 되먹임해 회차마다 정확해지는 자막 파이프라인.

```
유튜브 URL → yt-dlp → faster-whisper(GPU) → 자동자막 교차검증 → Claude 교정 → .srt
                                                                      ↑
                              사람 검수 diff → 용어사전/교정쌍 DB ────┘  (우로보로스 루프)
```

## 설치

```sh
uv sync --extra cuda   # NVIDIA GPU (권장)
uv run jamak doctor    # 환경 점검
```

요구사항: Python 3.12+, ffmpeg (PATH), NVIDIA GPU 8GB+ (STT), `ANTHROPIC_API_KEY` (LLM 교정).

## 사용

```sh
uv run jamak run "https://youtube.com/watch?v=..."   # 전체 파이프라인
uv run jamak seed-import data/seeds                  # 기존 검수 .srt 임포트
uv run jamak export <video_id>                       # .srt 내보내기
```

자세한 구조와 규칙은 [CLAUDE.md](CLAUDE.md).
