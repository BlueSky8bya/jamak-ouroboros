---
name: jamak-run
description: 유튜브 URL을 받아 자막 파이프라인 전체를 실행하고 결과를 보고한다. 사용자가 유튜브 링크를 주며 "자막 만들어줘", "돌려줘", "/jamak-run <url>" 할 때 사용.
---

# jamak-run

유튜브 URL 하나를 자막 draft까지 처리하는 실행 스킬.

## 절차

1. 인자에서 유튜브 URL 확인. 없으면 사용자에게 요청.
2. `uv run jamak doctor` — 실패 항목 있으면 먼저 해결 (특히 CUDA, ANTHROPIC_API_KEY).
3. `uv run jamak run <url>` 실행. 1~2시간 강연 기준 STT 10~25분 소요 — 백그라운드 실행 + 진행 상황 주기 확인.
4. 완료 후 보고:
   - 세그먼트 수, 불일치(flagged) 수, LLM 교정 변경 수
   - draft .srt 경로 (`data/jobs/<video_id>/<video_id>.draft.srt`)
5. 검수 웹앱이 구현되어 있으면 (`src/jamak/web/`) 서버를 띄우고 검수 안내. 없으면 draft 파일 위치만 안내.

## 주의

- 같은 URL 재실행은 안전 (단계별 캐시). 오디오/STT 재계산 강제하려면 `data/jobs/<video_id>/` 삭제.
- LLM 교정 스킵됐다면 (API 키 없음) 사용자에게 알리고 키 설정 후 재실행 제안.
- 검수 완료된 자막이 생기면 반드시 우로보로스 피드백 단계 실행 (AGENTS.md 규칙 1).
