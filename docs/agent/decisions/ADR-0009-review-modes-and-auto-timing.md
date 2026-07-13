# ADR-0009: 검수 모드 분리 (내용/타이밍) + 자동 타이밍 정리

Status: Accepted
Date: 2026-07-13
Decision Owners: User (방향·단순화 기준 확정) + Agent (세부 조합 위임받아 결정)

## Context

편집자 스트레스 최소화가 제품 철학. 1~2시간 강연 영상 검수에서 현재 에디터는
텍스트 확인과 타이밍 조정 UI가 한 화면에 섞여 있어 "타이밍도 지금 고쳐야 하나?"
불안을 만든다. 검수자에 나이 드신 분이 많아 화면 단순함·큰 버튼·되돌리기 보장이
특히 중요하다 (사용자 확정 기준).

데이터 모델은 이미 두 단계를 분리한다: `Segment.reviewed`(텍스트) vs
`Job.timing_done`/`Track.timing_done`(타이밍, ADR-0006). 부족한 것은 UI 모드뿐.

## Decision

1. **에디터에 두 작업 모드**: `내용 검수` / `타이밍 검수`. 큰 탭 2개로 전환.
   - 기본 모드는 상태에서 파생: 텍스트 검수 미완 → 내용, 완료 → 타이밍.
   - **강제 잠금 없음** — 전환은 언제나 가능 (하드 라우팅은 다른 스트레스를 만듦).
   - 모드 상태는 Editor 내부. App 라우팅으로 컴포넌트를 갈아끼우지 않는다
     (플레이어 재마운트 방지, TranslateReview 패널 교체와 같은 패턴).
   - 내용 모드: TimingStrip·WordMap·시간 필드·타이밍 도구·⏩빠름 배지·구조
     버튼 숨김. 재생/반복/참고(음성인식·유튜브)/Enter=확인+다음만 남김.
   - 포크된 번역 트랙에도 동일 적용 (Editor 내부 모드라 자동).
2. **잘 안 들림 = 단일 플래그**: `Segment.review_flag`("" | "hold") additive 컬럼.
   "잘 안 들림"과 "보류"를 하나로 통합 (두 개념 구분은 검수자 부담).
   - 확인(reviewed=True) 시 자동 해제. 보류는 완료(ko_complete)를 막는다 —
     대신 "남은 건 보류 N개뿐" UI로 심리 부담 제거. 보류 재방문 시
     0.75×+구간반복 프리셋.
3. **흘려듣기(자동 따라가기)**: 내용 모드 전용. 영상 연속 재생 + 재생 중인
   자막 중앙 스크롤 + (입력칸 밖) Enter로 현재 자막 확인. 수동 정지 없이
   들으며 확인만 하는 passive 플로우.
4. **자동 타이밍 정리** = 기존 프리미티브 조합, 전면 재세그먼트 아님:
   - `POST /api/jobs/{video_id}/auto-timing` (동기, GPU/API 불필요 — SttBlob
     단어 타임스탬프 기반이라 클라우드에서도 동작).
   - 순서: **absorb 먼저**(교정쌍 유실 방지) → 발화 구간 스냅(tighten과 동일
     로직) → 너무 빠른(>17cps)/너무 긴 자막을 단어 침묵 지점에서 자동 분할.
   - **분할돼도 reviewed 보존** (텍스트 내용은 동일, 잘리기만 함 — 미보존 시
     ko_complete 후퇴가 번역 게이트 재잠금으로 연쇄).
   - 응답에 before-rows/created-ids 포함 → 클라이언트 per-op undo 스택
     (restore-rows) 재사용, Alt+Z 되돌리기. 서버측 스냅샷 테이블은 만들지 않음.
   - 권한: 로그인 검수자 전원 (tighten과 일관) + 실행 전 확인 모달.
   - 트랙-와이드 작업 동시편집 정책은 기존과 동일 (드문 작업, 구두 조율).
5. **forced alignment(stable-ts/WhisperX)는 이번 스코프 밖** — 검수된
   text_final과 whisper 단어의 텍스트 불일치를 정밀하게 풀려면 필요하지만
   GPU 작업이라 worker(JobRequest에 `kind` additive 확장) 경유로 별도 ADR.

## Rationale

- 프리미티브 조합(분할 엔드포인트의 char-ratio 시간 보간 + split.py 경계 탐색)은
  stage 텍스트 보존·Translation FK·rowid 재사용 문제를 이미 검증된 경로로 통과.
  전면 재세그먼트는 이 방어를 전부 우회해 학습 데이터 파손 위험.
- absorb-먼저 규칙: 우로보로스 학습은 행 안의 machine↔final diff. 분할이 machine
  텍스트를 왼쪽 조각에만 남기므로, 대량 분할 후 absorb는 교정쌍을 잃는다.

## Consequences

- (+) 내용 검수 화면에서 타이밍 관련 시각 요소 소멸 — 판단 부담 제거.
- (+) 스키마 변경은 additive 1컬럼 — 기존 데이터·구버전 export 무손상.
- (-) 자동 분할의 시간 보간은 근사치 — 타이밍 모드에서 사람이 미세조정 (그래서
  타이밍 "검수" 모드가 뒤에 있음).
- (-) auto-timing의 Alt+Z는 클라이언트 세션 한정 (새로고침 후엔 수동 병합으로
  복구). tighten도 현재 undo가 없으므로 후퇴 아님.
- (-) 다른 검수자의 열린 undo 스택과 auto-timing이 겹치면 삭제 행 부활 가능 —
  기존 트랙-와이드 작업과 동일한 알려진 한계 (담당자 관례가 1차 방어).

## Revisit Conditions

- 자동 분할 결과의 수동 수정률이 높으면 forced alignment ADR 착수.
- 검수자 실사용에서 흘려듣기 vs 행 단위 플로우 선호 데이터.
- 보류 개수가 상시 누적되면 (해소 안 되면) 보류 전용 화면 검토.

## Phased Plan

`docs/agent/plans/ACTIVE_PLAN.md` (2026-07-13 검수 모드) 참조.
