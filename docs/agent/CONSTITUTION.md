# Constitution — jamak-ouroboros

## 1. Project Mission

허경영 강연 유튜브 영상의 한국어 자막 제작 비용을 "전체 타이핑"에서 "기계 초안 검수"로 낮추고, 검수할수록 기계 초안이 정확해지는 시스템을 만든다. 최종 산출물은 편집자에게 전달 가능한 `.srt` 파일이다 (채널이 제3자 소유이므로 API 업로드 불가 — ADR-0003).

## 2. Product Philosophy

- **우로보로스가 제품이다.** 1회성 STT 도구가 아니라, 사람 검수 diff가 용어사전·few-shot 교정쌍으로 축적되어 회차마다 CER이 내려가는 루프가 핵심 가치.
- 사람의 시간은 "불일치/불확실 구간"에 우선 배치한다 (교차검증 플래그, LLM uncertain 마킹).
- 자막 품질 기준: 발화 충실 (창작·요약 금지), 구어체 유지, 줄당 ~18자 최대 2줄.

## 3. Architecture Philosophy

- 파이프라인 단계는 1단계 = 1파일 (`src/jamak/pipeline/`), 각 단계는 캐시/DB 기반 재실행 가능(resumable).
- **DB(`data/jamak.db`)가 학습 데이터의 유일한 원본.** 프롬프트는 실행 시점에 DB에서 조립한다. 어휘 목록을 코드·프롬프트 파일에 하드코딩하지 않는다.
- 로컬 우선: STT는 로컬 GPU(faster-whisper), 교정만 Claude API. 비용 = API 교정비뿐.

## 4. Critical Invariants

- `data/jamak.db` 와 `data/seeds/` 는 명시적 승인 없이 삭제·스키마 파괴 변경 금지.
- Segment는 모든 단계의 텍스트(whisper/youtube/llm/final)를 나란히 보존한다 — diff 학습의 전제.
- 미승인(`approved=False`) 용어는 프롬프트에 주입되지 않는다. 승인은 사람이 한다.
- LLM 교정은 발화를 창작하지 않는다 (correct.py 프롬프트 규칙 2).
- Windows 콘솔 출력은 cp949 안전 문자만 (em-dash 등 금지 — CHG 이력 참고).

## 4.1 UX Invariant — 즉시 피드백 원칙 (2026-07-15, 사용자 확정)

**사용자 동작이 네트워크나 긴 작업을 기다리게 되면, 누른 그 순간부터 결과가
나올 때까지 화면에 눈에 보이는 신호가 있어야 한다.** "진행 중인지 거부됐는지
알 수 없는" 침묵 구간은 결함으로 취급한다.

- 시작: 즉시 표시 (버튼 라벨 "…중" + 비활성, 또는 전역 busy pill `.busy-pill`).
- 진행: 오래 걸리면 진행률 (번역 배치 진행바 `.tprogress` 패턴 — 정적 숫자 금지).
- 끝: 성공/실패를 그 자리에 명시 (도구 결과 배너 `.tool-msg`, 모달 안 `.srt-result`
  — 모달 뒤에 가려지는 상단 배너에만 쓰는 것 금지). "변화 없음"도 결과다
  ("이미 잘 정리되어 있어요")— 무변화를 침묵으로 표현하지 않는다.
- 서버: 같은 작업 이중 실행은 잠금으로 409 (`_exclusive`), 실패는 저장 여부를
  함께 알린다 ("저장된 것 없음, 재시도 안전").

## 5. Ambiguity & Change Policy

- WHITEHAVEN 프로토콜의 Ambiguity Gate, Minimum Necessary Change, Task Risk Level(L0~L3) 적용.
- L2 이상: `plans/ACTIVE_PLAN.md` 작성 후 구현. 파이프라인 정확도에 영향 주는 변경은 L2 취급.
- 정확도 관련 변경 후에는 CER 측정으로 검증한다 (`/jamak-eval`). 숫자가 나빠지면 되돌린다.

## 6. Verification Philosophy

- "코드 작성" ≠ "완료". 실제 영상 1개로 파이프라인 실행이 기본 검증.
- 실행하지 않은 검증은 `NOT VERIFIED`로 보고.
- ML_EVALUATION 규칙: CER 비교는 동일 정규화(jiwer transforms) 하에서만 유효. 평가 기준 변경은 ADR 대상.

## 7. Repository Memory

- 현재 상태: `CURRENT_STATE.md`. 결정: `decisions/` ADR. 변경 이력: `CHANGELOG_AGENT.md` + git. 인수인계: `handoffs/`.
- Claude API 코드 수정 시 `claude-api` 스킬 먼저 로드 (모델/파라미터 드리프트 방지).
