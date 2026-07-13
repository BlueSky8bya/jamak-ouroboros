# ACTIVE PLAN — 검수 모드 분리 + 자동 타이밍 (2026-07-13, ADR-0009)

Status: Done (2026-07-13) — 전 항목 구현·검증 완료 (흘려듣기 실재생·YT 연동은 DELEGATED)
Started: 2026-07-13
Owner: User(방향) + Agent(구현)

(이전 플랜 = 동시편집 안전화·반응성, 완료 → plans/completed/ 또는 git 이력.)

## 배경

텍스트 검수 중 타이밍 UI가 "지금 고쳐야 하나?" 불안 유발. 검수자에 고령자 많음
→ 화면 최소·큰 버튼·항상 되돌리기. 설계 결정은 ADR-0009.

## 단계

### A. 백엔드 (db.py, app.py, pipeline/retime.py 신규)
- [x] `Segment.review_flag: str = ""` + `_ensure_columns` additive ("hold" 단일값)
- [x] `SegmentUpdate`/`SegmentSnapshot`/`restore_rows`에 review_flag 반영
      (undo가 플래그를 지우지 않게)
- [x] update_segment: reviewed=True 저장 시 review_flag 자동 해제
- [x] `pipeline/retime.py`: 순수 함수 — 단어 스트림 + 세그먼트 → (스냅된 시간,
      분할 계획). 발화 스냅(tighten 로직) + >17cps 또는 >7s 자막을 내부 최대
      침묵 지점에서 분할(공백 스냅 char-split, 재귀). reviewed/review_flag 보존.
- [x] `POST /api/jobs/{video_id}/auto-timing`: absorb 먼저 → retime 적용(기존
      split 시맨틱: machine 텍스트 왼쪽, Translation은 원 행 유지+stale) →
      idx 재정규화 → `{changed, created_ids, before, tightened, split_count}`
      반환 (클라 undo용 before-rows 포함)

### B. 프론트 Editor.tsx (+types.ts, api.ts, styles)
- [x] mode: "text" | "timing" — 기본값 파생(ko_complete/timing_done), 큰 탭 2개
- [x] 내용 모드: Row 간소 렌더(시간 필드·nudge·타이밍 도구·구조 버튼·⏩빠름
      숨김), TimingStrip·무음다듬기·타이밍완료 체크 숨김
- [x] 🙉 잘 안 들림 버튼(행 + 단축키 Alt+H): review_flag 토글 + 다음 미검수·
      미보류로 이동. 행 배지. 확인 시 해제. 히어로에 "보류 N개" + 보류만 순회
      버튼(0.75×+구간반복 프리셋)
- [x] 흘려듣기: 내용 모드 토글(기본 ON, localStorage) — active 행 중앙 스크롤,
      입력칸 밖 Enter=현재 자막 확인(재생 유지)
- [x] 타이밍 모드: 문제 자막(⏩빠름·0.35s 미만·7s 초과) 카운트 + "다음 문제 →"
      순회
- [x] ✨ 타이밍 자동 정리 버튼(타이밍 모드) + 확인 모달 + 응답 before로
      pushOpUndo → Alt+Z 되돌리기
- [x] nextWorkTarget: 보류 행은 뒤로 미룸(미검수·미보류 우선)

### C. 검증 (실 DB 금지 — scratch SQLite: DATABASE_URL=sqlite:///<scratch>)
- [x] `npm run build` + `uv run python -c "import jamak.web.app"`
- [x] 마이그레이션 스모크: 기존 스키마 DB 복사본 부트 → review_flag 추가·행 보존
- [x] auto-timing API 스모크: 합성 job(세그먼트+SttBlob) → 분할 수/reviewed
      보존/translation 행 보존/idx dense 확인 + restore-rows로 원복
- [x] 브라우저: 모드 탭, 내용 모드 간소화, 잘 안 들림 플로우, 자동 정리+undo

### D. 마무리
- [x] WH-CHANGE 주석, CHANGELOG_AGENT(CHG-20260713-006~), CURRENT_STATE 갱신
- [x] 커밋·푸시, 배포 SHA 보고
