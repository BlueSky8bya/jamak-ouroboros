# Active ExecPlan

Plan ID: PLAN-20260710-010
Status: In Progress
Task Risk: L2
Created: 2026-07-10
Updated: 2026-07-10

## Objective

검수 피로 최소화(프로젝트 철학) 6개 요청 반영.

## Milestones

### M-A — 즉시 UI 수정 (요청 1,2,5)
- 영상 재생 단축키 복구: ⏯ 버튼(마우스) + Space(입력칸 밖) + Tab 유지. iframe 포커스 탈취 대비 다중 입력.
- 토스트(statusMsg/absorbMsg/error) 자동 사라짐 (4~8s).
- 파일명 `{lang}_{safe_title}_자막.srt`.
Validation: preview 스냅샷 + 파일명 헤더 확인.

### M-B — STT 프롬프트 환각 대응 (요청 6)
- noise.py `filter_prompt_hallucinations(segments, prompt_text)` + 연속 중복 붕괴.
- cli run()에 배선; 예방: stt.py `hallucination_silence_threshold`, whisper_prompt 단어목록화.
- 캐시된 테스트 영상(stt.json에 이미 누출)로 재실행 검증(리뷰 초기화 감수).
Validation: 재실행 후 "신인, 축지법..." 반복 세그먼트 제거 확인.

### M-C — 유튜브 밑 타임라인 마우스 미세조정 (요청 4)
- TimingStrip를 드래그 가능하게: 경계 드래그 → boundary-prev/next 호출.
Validation: preview에서 드래그 후 DB 시간 변경 확인.

### M-D — 번역 검수 워크플로 + 로컬 옵션 답변 (요청 3)
- KO 검수 완료 전 언어 선택 잠금.
- 번역 생성 후 세그먼트별 번역 검수(수정 저장) 화면.
- 로컬 모델 가능성 답변/옵션 (NLLB/m2m100 via CTranslate2 or Ollama; 품질 트레이드오프). Claude Haiku 저가 경로.
Validation: preview E2E (번역 생성→수정→저장→export 반영).

## Rollback
각 milestone 별도 커밋.
