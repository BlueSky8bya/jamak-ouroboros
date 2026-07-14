/** 연습 영상 ↔ 투어 체크포인트 동기화 테이블 (ACTIVE_PLAN 2026-07-15, 옵션 B;
 *  v2 대본 2026-07-15 — 흐름 확인·오타 지목·코스 프리셋).
 *
 *  코스별로 COURSES[i].steps와 같은 길이의 배열: steps[k]의 말풍선이 등장(하고
 *  영상이 자동 일시정지)하는 나레이션 시각(초). 값의 출처는 튜토리얼 영상 빌드
 *  산출물 `tools/tutorial-video/out/practice-N/timing.json`의 해당 지시 대사
 *  end + 0.15s — 영상을 다시 렌더하면 이 표도 함께 갱신해야 한다.
 *
 *  규칙:
 *  - 0 = 시작부터 표시 (영상을 틀기 전이라 영상이 지시할 수 없는 첫 단계).
 *  - 같은 값이 연달아 있으면 연쇄 단계: 첫 단계 완료 후 영상은 정지 유지,
 *    다음 말풍선이 바로 뜬다.
 *  - final 단계 값은 마무리 대사 시각 — 말풍선만 띄우고 일시정지는 하지 않는다.
 */
export const TUTORIAL_CHECKPOINTS: Record<string, number[]> = {
  // practice-1 v2(17줄): 재생(즉시) → 흐름 확인(L7, untilTime) → 오타 글 열기(L12)
  // → 고치고 확인(L12 연쇄) → 🙉(L14) → 되돌리기(L15) → 글씨 크게(L16) → 끝(L17)
  basic: [0, 68.1, 111.4, 111.4, 132.6, 145.8, 157.3, 158.3],
  // practice-2: Tab(L2) → 3초 뒤(L5) → 배속(L6) → 3초 앞(L7) → 10초(L9) →
  // 구간처음(L10) → 구간반복(L11) → 자막이동(L12) → 끝(L13)
  playback: [25.2, 57.2, 72.0, 81.9, 104.6, 116.2, 128.7, 142.4, 143.6],
  // practice-3: 안심 확인(L8) → 찾기바꾸기(L13) → 멈춤 끄기(L14) → 따라가기(L15)
  // → 미확인 이동(L16) → 끝(L17)
  fast: [50.3, 90.1, 108.8, 121.7, 137.0, 138.2],
  // practice-4: 글 열기+나누기(L3, 연쇄) → 합치기(L8) → 되돌리기×2(L9, 연쇄) → 끝(L11)
  structure: [45.6, 45.6, 68.8, 79.7, 79.7, 92.0],
  // practice-5: ② 탭+자동 정리(L3, 연쇄) → 다음 문제(L5) → Alt+[(L6) → Alt+](L7)
  // → Alt+\(L8) → 무음 다듬기(L9) → 타임라인 끌기(L10) → 끝(L12)
  timing: [50.6, 50.6, 64.3, 74.9, 80.5, 91.9, 106.1, 117.6, 125.9],
  // practice-6: 미리보기(L2) → 복구·채우기(L4) → 학습(L5) → 자막 받기(L7) → 끝(L9)
  finish: [27.9, 50.5, 67.2, 87.3, 95.4],
};

/** 코스 시작 시 강제 적용하는 재생 설정 — 이전 저장값·디폴트가 연습 목표를
 *  방해하지 않게 (사용자 결정 2026-07-15: "각 연습 목표에 맞게 설정이 유도되고,
 *  그 설정 자체도 영상이 설명한다"). 나레이션과 짝: 연습1·2는 "영상이 흐르는
 *  채로", 연습3은 멈춤 켠 상태에서 시작해 끄는 법을 가르침, 연습4는 "누르면
 *  멈추도록 맞춰 두었습니다". */
export const COURSE_PRESETS: Record<string, { pauseOnType: boolean; follow: boolean }> = {
  basic: { pauseOnType: false, follow: true },
  playback: { pauseOnType: false, follow: true },
  fast: { pauseOnType: true, follow: true },
  structure: { pauseOnType: true, follow: true },
  timing: { pauseOnType: true, follow: true },
  finish: { pauseOnType: true, follow: true },
};

/** 결함 주입 단어(practice.py COURSE_TEXT_DEFECTS와 동일 표면형) — 투어가
 *  "여기 글자가 달라요" 셀을 찾을 때 쓴다. 학습 데이터가 아니라 UI 앵커라
 *  하드코딩 허용(원본은 서버 주입 로직). */
export const TUTORIAL_DEFECT_WORDS = ["깨입", "밥나무", "축제법", "공중부용", "몽치"];
