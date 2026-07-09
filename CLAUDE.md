# Claude Code Entry Point — jamak-ouroboros

@AGENTS.md

이 저장소는 WHITEHAVEN Agent Harness를 사용한다 (`agent-harness.yaml` 참고).

## 라우팅

- 현재 상태·다음 작업: `docs/agent/CURRENT_STATE.md` (세션 시작 시 필독)
- 경로 라우팅: `docs/agent/PROJECT_MAP.md`
- 철학·불변 규칙: `docs/agent/CONSTITUTION.md`
- 설계 결정: `docs/agent/DECISION_INDEX.md`
- 완료 기준: `docs/agent/DEFINITION_OF_DONE.md`
- L2/L3 작업: `docs/agent/plans/ACTIVE_PLAN.md` 먼저

## 명령

```
uv run jamak doctor              # 환경 점검
uv run jamak run <youtube-url>   # 전체 파이프라인 → draft .srt
uv run jamak seed-import <dir>   # 검수 완료 자막 임포트
uv run jamak export <video_id>   # .srt 내보내기
```

## Claude Code 전용 노트

- 프로젝트 스킬: `/jamak-run`, `/seed-import`, `/glossary-review`, `/jamak-eval`
- Claude API 코드 수정 전 `claude-api` 스킬 로드 (모델/파라미터 드리프트 방지)
- 콘솔 출력은 cp949 안전 문자만. 파이프라인 실행 시 `PYTHONIOENCODING=utf-8` 권장
- `ANTHROPIC_API_KEY`가 세션에 없고 User 레지스트리에 있으면:
  `$env:ANTHROPIC_API_KEY=(Get-ItemProperty HKCU:\Environment).ANTHROPIC_API_KEY; <명령>`
- 검수 완료 자막 발생 시 피드백 흡수(diff → DB) 없이 세션을 끝내지 않는다
