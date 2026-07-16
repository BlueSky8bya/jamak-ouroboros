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
    // v2 대본(17줄): 7 흐름 확인, 12 오타 고치기, 14 🙉, 15 Alt+Z, 16 글씨 크게
    7: [{ kind: "keys", rows: [["Enter"]] }],
    12: [{ kind: "tap-row" }, { kind: "keys", rows: [["Enter"]] }],
    14: [{ kind: "button", label: "🙉 잘 안 들림" }],
    15: [{ kind: "keys", rows: [["Alt", "Z"]] }],
    16: [{ kind: "button", label: "글씨 크게", zone: "top-left" }],
  },
  2: {
    2: [{ kind: "keys", rows: [["Tab"]] }],
    5: [{ kind: "keys", rows: [["Alt", "←"], ["Shift", "Tab"]] }],
    6: [{ kind: "speed", zone: "video-below" }],
    7: [{ kind: "keys", rows: [["Alt", "→"]] }],
    9: [{ kind: "keys", rows: [["Alt", "Shift", "→"]] }],
    10: [{ kind: "keys", rows: [["Ctrl", "\\"]] }],
    11: [{ kind: "check", label: "🔁 구간반복", on: true, zone: "video-below" }],
    12: [{ kind: "keys", rows: [["Alt", "↑"], ["Alt", "↓"]] }],
  },
  // [WH-CHANGE v0.9.88 | FIX | 2026-07-17 | CHG-20260717-128]
  // Reason: 사용자 지적 — 연습3 영상이 **삭제된 `✅ 안심 확인` 버튼을 안내**하고
  //   있었다("영상에는 왜 안내하고 있어"). 원인: v0.9.67에서 대본 3·5·6을 다시
  //   쓰면서 **이 파일을 안 고쳤다.** 이 맵은 대사 **번호**로 그림을 붙이는데,
  //   대본이 바뀌면 번호의 의미가 통째로 달라진다 — 죽은 버튼이 남았을 뿐 아니라
  //   3·5는 그림이 한두 칸씩 밀려 엉뚱한 대사 위에 떴고, 6은 옛 대본(6줄짜리)용
  //   맵이 23줄 대본에 그대로 남아 있었다. 세 코스 전부 현행 대본과 1:1 재작성.
  //   연습1·2·4는 대본이 그대로여서 대조 결과 이상 없음(확인함).
  // Related: CHANGELOG CHG-20260717-128.
  3: {
    // 16줄: 2 Enter 촤르륵 · 12 찾기바꾸기 · 13 멈춤끄기 · 14 따라가기 · 15 미확인이동
    2: [{ kind: "keys", rows: [["Enter"]] }],
    12: [{ kind: "button", label: "🔎 찾기·바꾸기", zone: "list-top" }],
    13: [{ kind: "check", label: "편집 시작 시 멈춤", on: false, zone: "video-below" }],
    14: [{ kind: "check", label: "🎧 자동 따라가기", on: false, zone: "video-below" }],
    15: [
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
    // 14줄: 3 ②타이밍 탭 · 5 다음문제 · 7 Alt+[ · 8 Alt+] · 9 Alt+\ · 11 손잡이
    //       · 12 무음다듬기 · 13 타이밍 검수 완료
    // (✨ 타이밍 자동 정리는 ADR-0012로 폐지 — 새 대본에도 없다)
    3: [{ kind: "tabs" }],
    5: [{ kind: "button", label: "다음 문제 →" }],
    7: [{ kind: "keys", rows: [["Alt", "["]] }],
    8: [{ kind: "keys", rows: [["Alt", "]"]] }],
    9: [{ kind: "keys", rows: [["Alt", "\\"]] }],
    11: [{ kind: "drag" }],
    12: [{ kind: "button", label: "✂ 무음 다듬기", zone: "left-bottom" }],
    13: [{ kind: "check", label: "⏱ 타이밍 검수 완료", on: true, zone: "left-bottom" }],
  },
  6: {
    // 23줄 캡스톤: 2 속도 정하기 · 3 Enter 촤르륵 · 10 군소리 지우기 · 13 합치기
    //   · 15 나누기 · 16 되짚기 · 19 漢 채우기 · 20 미리보기 · 21 학습 · 22 자막받기
    // (🛠 복구·채우기는 삭제된 버튼 — 새 대본에도 없다)
    2: [{ kind: "check", label: "편집 시작 시 멈춤", on: false, zone: "video-below" }],
    3: [{ kind: "keys", rows: [["Enter"]] }],
    10: [{ kind: "keys", rows: [["Alt", "Delete"]] }],
    13: [{ kind: "merge" }, { kind: "keys", rows: [["Ctrl", "Shift", "Enter"]] }],
    15: [{ kind: "split" }, { kind: "keys", rows: [["Ctrl", "Enter"]] }],
    16: [{ kind: "keys", rows: [["Alt", "↑"], ["Alt", "↓"], ["Shift", "Tab"]] }],
    19: [{ kind: "button", label: "漢 한자 채우기", zone: "left-bottom" }],
    20: [{ kind: "check", label: "💬 미리보기 모드", on: true, zone: "video-below" }],
    21: [{ kind: "button", label: "📚 학습", zone: "left-bottom" }],
    22: [{ kind: "button", label: "자막 받기 (.srt)", zone: "left-bottom" }],
  },
};
