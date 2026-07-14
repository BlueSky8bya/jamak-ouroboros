/** 따라하기 투어 (interactive walkthrough) — 어르신 검수자용.
 *
 *  The static 📖 사용법 screen is the reference book; this is the practice run:
 *  it dims the real editor, spotlights ONE control at a time, and each step
 *  advances only when the reviewer actually performs the action (press ▶,
 *  press Enter, click a subtitle, press 🙉, press Alt+Z). Learning by doing —
 *  one action per step, big text, exit any time.
 *
 *  Purely presentational: the Editor owns the step state and calls
 *  `advance()` from the real action sites; this component just draws the
 *  spotlight + bubble for the current step. No dependencies — the spotlight is
 *  four dim panels around the target's rect (clicks outside the hole are
 *  blocked, the hole itself stays fully interactive).
 */

import { useEffect, useRef, useState } from "react";

export interface TourStep {
  /** CSS selector for the element to spotlight; null = centered card */
  target: string | null;
  title: string;
  body: React.ReactNode;
  /** shown when the target element isn't on screen yet */
  missingHint?: string;
  /** final step shows a big finish button instead of waiting for an action */
  final?: boolean;
  /** action event (tourEvent name) that completes this step */
  on?: string;
  /** 흐름 확인 단계: 체크포인트 시각까지 나온 자막이 전부 확인/보류되면 자동
   *  진행 (Editor가 세그먼트 상태로 판정). on:"confirm"과 함께 쓴다. */
  untilTime?: boolean;
  /** 심은 오타가 든 자막 행을 동적으로 지목 (Editor가 selector로 풀어줌) */
  targetDefect?: boolean;
  /** 이 단계 동안 대상 행을 구간반복으로 들려준다 (정지 대신) — 자막과 말을
   *  비교해야 하는 행 단계용. 완료 시 체크포인트 위치로 되감아 이어간다. */
  loopRow?: boolean;
  /** loopRow 대상 행을 시간으로 지정: 이 나레이션 구간과 겹치는 행 (초). */
  subject?: [number, number];
}

const PAD = 8; // spotlight breathing room around the target

export function Tour({
  steps,
  step,
  onExit,
  onSkipStep,
  onFinish,
  targetOverride,
  note,
}: {
  steps: TourStep[];
  step: number;
  onExit: () => void;
  onSkipStep: () => void;
  onFinish: () => void;
  /** Editor가 동적으로 푼 대상 selector (오타 행 지목 등) — target보다 우선 */
  targetOverride?: string | null;
  /** 진행 상황 한 줄 (예: "남은 자막 3개") — 흐름 확인 단계에서 갱신됨 */
  note?: string;
}) {
  const cur = steps[step];
  const [rect, setRect] = useState<DOMRect | null>(null);
  const scrolledEl = useRef<Element | null>(null);
  const target = targetOverride !== undefined ? targetOverride : cur?.target;

  // follow the target: elements move (scroll, playback, layout), so poll its
  // rect while the tour is up. Cheap — one querySelector per 250ms.
  useEffect(() => {
    function measure() {
      if (!target) {
        setRect(null);
        return;
      }
      const el = document.querySelector(target);
      if (!el) {
        setRect(null);
        return;
      }
      // 대상 "요소"가 바뀔 때마다 다시 화면 중앙으로 — 흐름 확인 단계에서
      // 말풍선이 다음 미확인 자막을 따라 내려가야 한다 (단계당 1회였던 것 개선)
      if (scrolledEl.current !== el) {
        scrolledEl.current = el;
        el.scrollIntoView({ block: "center", behavior: "smooth" });
      }
      const r = el.getBoundingClientRect();
      setRect((prev) =>
        prev &&
        Math.abs(prev.top - r.top) < 1 &&
        Math.abs(prev.left - r.left) < 1 &&
        Math.abs(prev.width - r.width) < 1 &&
        Math.abs(prev.height - r.height) < 1
          ? prev
          : r,
      );
    }
    measure();
    const t = window.setInterval(measure, 250);
    window.addEventListener("resize", measure);
    return () => {
      window.clearInterval(t);
      window.removeEventListener("resize", measure);
    };
  }, [target, step]);

  if (!cur) return null;

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const hole = rect
    ? {
        top: Math.max(0, rect.top - PAD),
        left: Math.max(0, rect.left - PAD),
        right: Math.min(vw, rect.right + PAD),
        bottom: Math.min(vh, rect.bottom + PAD),
      }
    : null;

  // bubble goes below the hole when there's room, else above, else centered
  const bubbleBelow = hole ? vh - hole.bottom > 230 : false;
  const bubbleStyle: React.CSSProperties = hole
    ? {
        left: Math.min(Math.max(12, (hole.left + hole.right) / 2 - 190), vw - 392),
        ...(bubbleBelow
          ? { top: hole.bottom + 14 }
          : { bottom: vh - hole.top + 14 }),
      }
    : { left: "50%", top: "50%", transform: "translate(-50%, -50%)" };

  return (
    <div className="tour" aria-live="polite">
      {/* four dim panels leaving the target clickable */}
      {hole ? (
        <>
          <div className="tour-dim" style={{ top: 0, left: 0, width: "100vw", height: hole.top }} />
          <div className="tour-dim" style={{ top: hole.bottom, left: 0, width: "100vw", height: Math.max(0, vh - hole.bottom) }} />
          <div className="tour-dim" style={{ top: hole.top, left: 0, width: hole.left, height: hole.bottom - hole.top }} />
          <div className="tour-dim" style={{ top: hole.top, left: hole.right, width: Math.max(0, vw - hole.right), height: hole.bottom - hole.top }} />
          <div
            className="tour-ring"
            style={{ top: hole.top, left: hole.left, width: hole.right - hole.left, height: hole.bottom - hole.top }}
          />
        </>
      ) : (
        <div className="tour-dim" style={{ inset: 0 }} />
      )}

      <div className={"tour-bubble" + (cur.final ? " final" : "")} style={bubbleStyle} role="dialog">
        <div className="tour-progress">
          {steps.map((_, i) => (
            <span key={i} className={"tour-dot" + (i === step ? " on" : i < step ? " done" : "")} />
          ))}
          <em>
            {step + 1} / {steps.length}
          </em>
        </div>
        <h3>{cur.title}</h3>
        <div className="tour-body">{cur.body}</div>
        {note && <div className="tour-note">{note}</div>}
        {target && !rect && cur.missingHint && (
          <div className="tour-missing">{cur.missingHint}</div>
        )}
        <div className="tour-actions">
          <button className="tour-exit" onClick={onExit}>
            그만 볼래요
          </button>
          {cur.final ? (
            <button className="tour-finish" onClick={onFinish}>
              좋아요, 시작할게요!
            </button>
          ) : (
            <button className="tour-skip" onClick={onSkipStep}>
              이 단계 건너뛰기 →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
