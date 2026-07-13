# ACTIVE PLAN — 편집기 동시편집 안전화 + 반응성 개선 (2026-07-13)

Status: Done (2026-07-13) — 전 항목 구현·검증 완료
Started: 2026-07-13
Owner: User + Agent

(이전 플랜 = 경로 B 클라우드 이전, 완료·배포됨 → git 이력·CHANGELOG v0.2.0 참조.)

## 배경

검수자 다수(≤50명) 동시 사용 전제. 사용자 보고:
- 되돌리기(Alt+Z)가 여러 개를 한 번에 되돌리거나 아예 안 먹힘
- 편집이 "뚝딱거림" (끊기는 느낌)
- 담당자 기준으로 내 영상을 빨리 찾고 싶음

## 진단 (코드 확인 완료)

1. **Undo = 전체 트랙 스냅샷 복원** (`restore_segments`: 해당 lang 세그먼트 전부 DELETE 후 재삽입).
   - 텍스트 편집(`save`)은 `pushUndo`를 안 찍음 → 스택 비면 "안 먹힘".
   - 체크포인트 사이 모든 변경이 한 스냅샷에 묻힘 → "여러 개 한 번에 되돌아감".
   - 트랙 전체 delete-reinsert → 동시 편집자 B의 작업까지 파괴 (최대 위험).
2. **뚝딱거림**: (a) 변이마다 전체 refetch(2×RTT 싱가포르), (b) Row 비-memo + currentTime 전 행 전파로 재생 중 상시 전체 재렌더, (c) 낙관적 업데이트 없음(Enter/저장이 RTT 대기).
3. `_next_segment`/`_previous_segment`가 `idx == ±1` (dense idx 필수) → 부분 복원 시 idx 재정규화 필요.

## 계획

### A. 백엔드 (src/jamak/web/app.py, db.py)
- [x] PG 엔진 풀 확장: `pool_size=10, max_overflow=20` (50명 대비)
- [x] 변이 엔드포인트가 영향받은 행 반환 (전체 refetch 제거):
  - boundary-prev/next, edge-drag, redistribute-next → `{segments: [...]}`
  - split → `{segments: [left, right]}` / merge-next → `{segments: [survivor], deleted_id}` / delete → `{deleted_id}`
- [x] 신규 `POST /api/jobs/{video_id}/segments/restore-rows?lang=`:
  body `{upsert: [행 스냅샷], delete_ids: [...]}` — 해당 행만 upsert/삭제 + 트랙 idx를 (start,end,id) 순 재정규화, 전체 트랙 반환.
- [x] 구 `restore` 전체-트랙 엔드포인트 제거 (유일 호출자 대체, 동시편집 위험 제거)

### B. 프런트 Editor.tsx — Undo v2 + 낙관적 UI + memo
- [x] UndoEntry v2: `{label, kind, segId?, upsert: Segment[], deleteIds: number[]}` — 작업 단위.
  - 텍스트 저장도 push (같은 세그먼트 연속 타이핑은 coalesce — 셀 편집 세션 단위).
  - split은 응답의 새 행 id를 deleteIds로 기록.
- [x] undoLast → restore-rows (영향 행만 복원; 다른 검수자 작업 불가침).
- [x] 낙관적 저장: save() 로컬 즉시 반영 + Enter 즉시 다음 이동, PUT은 세그먼트별 직렬 큐, 실패 시 롤백+에러.
- [x] 시간 조정(◀▶/발화맞춤): 로컬 즉시 반영 + 백그라운드 PUT.
- [x] boundary/edge/구조: 응답 행으로 로컬 패치 (refetch 제거).
- [x] `React.memo(Row)` + 안정 콜백 + currentTime은 active/focused 행에만 전달.
- [x] keydown effect `[currentTime]` 의존 제거 (ref).

### C. 프런트 App.tsx — 담당자 검색
- [x] 검색창이 제목+담당자 매칭, "👤 내 담당만" 토글 칩 (me.name, localStorage 유지).

### D. 검증
- [x] 격리 임시 DB로 로컬 serve + 브라우저: 텍스트 undo / 구조 undo / Enter 즉시 이동 / nudge 무-refetch / 담당자 검색
- [x] 실 DB(클라우드 PG·로컬 jamak.db) 쓰기 금지

### E. 마무리
- [x] CURRENT_STATE / CHANGELOG_AGENT 갱신, 커밋·푸시, 배포 SHA 보고
