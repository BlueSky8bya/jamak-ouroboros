/** Per-line visual cues (PLAN P2 확장): 내레이션이 시키는 조작을 화면에
 *  애니메이션으로 보여준다 — 키캡 눌림, 버튼 탭, 체크 토글, 화면 위치 미니맵,
 *  나누기/합치기/드래그 모션. 대사 줄 번호(timing.json의 i, 1-base)로 매핑.
 *  발화 문장 자체는 여전히 표시하지 않는다 (듣기 검수 원칙).
 */

export type Zone =
  | "top-left" // 글씨 크게 등 좌상단
  | "video-below" // 영상 바로 아래 (배속·체크 칸 줄)
  | "left-bottom" // 왼쪽 아래 도구 줄·자막 받기
  | "list-top" // 자막 목록 맨 위 (탭·찾기바꾸기)
  | "list" // 자막 목록(행)
  | "bottom"; // 타임라인

export type Visual =
  | { kind: "keys"; rows: string[][] } // 대안이 여러 개면 rows 여러 줄 ("또는")
  | { kind: "button"; label: string; zone?: Zone }
  | { kind: "check"; label: string; on: boolean; zone?: Zone } // on = 목표 상태
  | { kind: "tap-row" } // 자막 글을 눌러 고치기
  | { kind: "split" }
  | { kind: "merge" }
  | { kind: "drag" }
  | { kind: "tabs" } // ② 타이밍 탭 누르기
  | { kind: "speed" ; zone?: Zone }; // 0.75× 배속

export const VISUALS: Record<number, Record<number, Visual[]>> = {
  1: {
    6: [{ kind: "keys", rows: [["Enter"]] }],
    10: [{ kind: "tap-row" }, { kind: "keys", rows: [["Enter"]] }],
    12: [{ kind: "button", label: "🙉 잘 안 들림" }],
    13: [{ kind: "keys", rows: [["Alt", "Z"]] }],
    14: [{ kind: "button", label: "글씨 크게", zone: "top-left" }],
  },
  2: {
    2: [{ kind: "keys", rows: [["Tab"]] }],
    5: [{ kind: "keys", rows: [["Ctrl", "←"], ["Shift", "Tab"]] }],
    6: [{ kind: "speed", zone: "video-below" }],
    7: [{ kind: "keys", rows: [["Ctrl", "→"]] }],
    9: [{ kind: "keys", rows: [["Ctrl", "Shift", "→"]] }],
    10: [{ kind: "keys", rows: [["Ctrl", "\\"]] }],
    11: [{ kind: "check", label: "🔁 구간반복", on: true, zone: "video-below" }],
    12: [{ kind: "keys", rows: [["Alt", "↑"], ["Alt", "↓"]] }],
  },
  3: {
    8: [{ kind: "button", label: "✅ 안심 확인", zone: "left-bottom" }],
    13: [{ kind: "button", label: "🔎 찾기·바꾸기", zone: "list-top" }],
    14: [{ kind: "check", label: "편집 시작 시 멈춤", on: false, zone: "video-below" }],
    15: [{ kind: "check", label: "🎧 자동 따라가기", on: false, zone: "video-below" }],
    16: [
      { kind: "keys", rows: [["Alt", "Shift", "↓"]] },
      { kind: "button", label: "이어서 작업하기", zone: "left-bottom" },
    ],
  },
  4: {
    3: [{ kind: "split" }, { kind: "keys", rows: [["Ctrl", "Enter"]] }],
    7: [{ kind: "merge" }],
    8: [{ kind: "merge" }, { kind: "keys", rows: [["Ctrl", "Shift", "Enter"]] }],
    9: [{ kind: "keys", rows: [["Alt", "Z"]] }],
    10: [{ kind: "keys", rows: [["Alt", "Delete"]] }],
  },
  5: {
    3: [{ kind: "tabs" }, { kind: "button", label: "✨ 타이밍 자동 정리", zone: "left-bottom" }],
    5: [{ kind: "button", label: "다음 문제 →" }],
    6: [{ kind: "keys", rows: [["Alt", "["]] }],
    7: [{ kind: "keys", rows: [["Alt", "]"]] }],
    8: [{ kind: "keys", rows: [["Alt", "\\"]] }],
    9: [{ kind: "button", label: "✂ 무음 다듬기", zone: "left-bottom" }],
    10: [{ kind: "drag" }],
    11: [{ kind: "check", label: "⏱ 타이밍 검수 완료", on: true, zone: "left-bottom" }],
  },
  6: {
    2: [{ kind: "check", label: "💬 미리보기 모드", on: true, zone: "video-below" }],
    3: [{ kind: "drag" }],
    4: [{ kind: "button", label: "🛠 복구·채우기", zone: "left-bottom" }],
    5: [{ kind: "button", label: "📚 학습", zone: "left-bottom" }],
    6: [{ kind: "button", label: "자막 받기 (.srt)", zone: "left-bottom" }],
  },
};
