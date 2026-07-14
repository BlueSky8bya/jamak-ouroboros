/** 자체 확인 모달 훅 — 브라우저 window.confirm 대체 (앱과 생김새가 달라
 *  "붕 뜬다"는 사용자 피드백, 2026-07-15). Promise 기반이라 기존
 *  `if (!confirm(...)) return;` 자리에 `if (!(await ask({...}))) return;`로
 *  갈아끼우면 된다. 스타일은 .srt-modal + .confirm-mini 재사용. */

import { useRef, useState } from "react";

export interface ConfirmOpts {
  title: string;
  body: React.ReactNode;
  ok: string; // 진행 버튼 라벨 (동사형: "정리할게요", "되돌릴게요" 등)
}

export function useConfirm(): [
  React.ReactNode,
  (o: ConfirmOpts) => Promise<boolean>,
] {
  const [opts, setOpts] = useState<ConfirmOpts | null>(null);
  const resolver = useRef<((v: boolean) => void) | null>(null);

  function ask(o: ConfirmOpts): Promise<boolean> {
    return new Promise((res) => {
      resolver.current = res;
      setOpts(o);
    });
  }
  function done(v: boolean) {
    setOpts(null);
    resolver.current?.(v);
    resolver.current = null;
  }

  const node = opts ? (
    <div
      className="srt-modal-back"
      onMouseDown={(e) => e.target === e.currentTarget && done(false)}
    >
      <div className="srt-modal confirm-mini" onClick={(e) => e.stopPropagation()}>
        <h3>{opts.title}</h3>
        <p className="srt-summary">{opts.body}</p>
        <div className="confirm-actions">
          <button className="tour-exit" onClick={() => done(false)}>
            취소
          </button>
          <button className="tour-finish" onClick={() => done(true)}>
            {opts.ok}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return [node, ask];
}
