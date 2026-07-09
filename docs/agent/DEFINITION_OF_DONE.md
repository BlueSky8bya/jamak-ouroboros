# Definition of Done — jamak-ouroboros

작업 유형별 완료 기준. "코드 작성"이 아니라 아래 증거가 있어야 완료.

## 모든 작업 공통

- [ ] `uv run jamak doctor` PASS
- [ ] 실행한 검증 명령과 결과를 보고 (미실행은 `NOT VERIFIED` 명시)
- [ ] 콘솔 출력에 cp949 비호환 특수문자 없음 (ISSUE-003)
- [ ] `CURRENT_STATE.md` 갱신 (상태가 바뀌었으면)

## 파이프라인 변경 (L1~L2)

- [ ] 테스트 영상(lFuxxOlgl5Y, 9분)으로 해당 단계 재실행 성공
- [ ] 캐시/재실행(resumable) 동작 유지 — 같은 명령 재실행이 안전한가
- [ ] 출력 .srt 육안 스팟체크 (타임스탬프 싱크, 줄 규칙)

## 정확도 관련 변경 (프롬프트, 교차검증, few-shot 선별, 자막 규칙) — L2

- [ ] 변경 전/후 비교 근거 (검수본 있으면 CER, 없으면 알려진 오인식 케이스 스팟체크)
- [ ] 평가 기준 자체를 바꿨으면 ADR 작성
- [ ] 학습 데이터를 코드에 하드코딩하지 않았는가 (Constitution invariant)

## DB 스키마 변경 — L2/L3

- [ ] 기존 `data/jamak.db` 데이터 보존 경로 확인 (마이그레이션 또는 명시적 사용자 승인)
- [ ] 롤백 방법 기록

## Claude API 코드 변경

- [ ] `claude-api` 스킬 로드 후 작성 (모델 ID/파라미터 최신 확인)
- [ ] API 키 없는 환경에서 우아한 스킵 동작 유지

## 검수 웹앱 (M3부터)

- [ ] preview 도구로 구동, 핵심 플로우 E2E (세그먼트 클릭 시크 / 편집 / 저장 / srt 내보내기)
- [ ] 저장 시 diff가 DB에 기록되는지 확인 (우로보로스 전제)

## Done Report 형식

작업 종료 시: Task / Risk Level / Changed / Files / Validation Executed / Not Verified / Documentation Updated / Rollback.
