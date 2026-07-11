import { useEffect, useMemo, useRef, useState } from "react";
import {
  absorbFeedback,
  boundaryNext,
  boundaryPrev,
  edgeDrag,
  confirmSafe,
  deleteSegment,
  exportUrl,
  fetchLanguages,
  fetchSegments,
  fetchTranslations,
  fetchWords,
  forkTrack,
  unforkTrack,
  mergeNext,
  repairStt,
  replaceText,
  restoreSegments,
  setTimingDone,
  splitSegment,
  tightenTiming,
  updateSegment,
} from "./api";
import type { WordTime } from "./api";
import { ThemeToggle } from "./theme";
import { TranslateReview } from "./TranslateReview";
import type { Segment } from "./types";
import { usePlayer } from "./usePlayer";

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = (t % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

/** "1:23.4" | "83.4" | "1:23" -> seconds, or null if unparseable */
function parseTime(v: string): number | null {
  const t = v.trim();
  if (/^\d+(\.\d+)?$/.test(t)) return parseFloat(t);
  const m = /^(\d+):(\d{1,2}(?:\.\d+)?)$/.exec(t);
  if (m) return parseInt(m[1]) * 60 + parseFloat(m[2]);
  return null;
}

function displayText(seg: Segment): string {
  return seg.text_final || seg.text_llm || seg.text_whisper;
}

function segmentNo(segments: Segment[], id: number | undefined): string {
  if (id === undefined) return "-";
  const i = segments.findIndex((s) => s.id === id);
  return i >= 0 ? String(i + 1) : "-";
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(Math.max(v, min), max);
}

function TimingStrip({
  segments,
  currentTime,
  activeId,
  focusedId,
  playing,
  onSeek,
  onBoundaryDrag,
  onDragActive,
}: {
  segments: Segment[];
  currentTime: number;
  activeId: number | undefined;
  focusedId: number | null;
  playing: boolean;
  onSeek: (t: number) => void;
  onBoundaryDrag: (segId: number, time: number, which: "start" | "end") => void;
  onDragActive?: (active: boolean) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  // Dragging is done IMPERATIVELY (no React state per pointermove): we move the
  // grabbed handle's `left` and the time label directly on the DOM. Driving it
  // through setState re-rendered the whole strip every frame — that reconcile
  // churn is what made the handle jump/stutter instead of tracking the pointer.
  // winRef freezes the visible window for the whole drag so the mapping is stable.
  const winRef = useRef<{ start: number; span: number } | null>(null);
  const dragRef = useRef<{
    segId: number;
    which: "start" | "end";
    el: HTMLElement;
    startX: number;
  } | null>(null);
  const [dragging, setDragging] = useState(false); // only to freeze the window

  const focused = segments.find((s) => s.id === focusedId);
  // when the playhead sits in a gap or the tail past the last cue there is no
  // active cue — the nearest cue behind it is what stays adjustable
  const nearestBehind =
    activeId == null
      ? (() => {
          let b: Segment | null = null;
          for (const s of segments) if (s.start <= currentTime) b = s;
          return b;
        })()
      : null;
  const live = (() => {
    if (dragging && winRef.current) return winRef.current;
    // follow the playhead while it moves (playing, or seeked outside the view);
    // otherwise anchor on the cue you're editing so it stays put
    const focusCenter = focused ? (focused.start + focused.end) / 2 : currentTime;
    const outside = currentTime < focusCenter - 8 || currentTime > focusCenter + 8;
    let center = playing || outside ? currentTime : focusCenter;
    // don't scroll off into empty space past the last cue / across a long gap —
    // keep the nearest-behind cue on screen so its edges stay grabbable
    if (nearestBehind && (playing || outside)) center = Math.min(center, nearestBehind.end + 5);
    const start = Math.max(0, center - 8);
    const end = Math.max(start + 12, center + 8);
    return { start, span: end - start };
  })();
  const { start, span } = live;
  const end = start + span;
  const local = segments.filter((s) => s.end >= start && s.start <= end);
  const marker = clamp(((currentTime - start) / span) * 100, 0, 100);
  // which cue's edges are grabbable: the playing one, or (gap / tail) the
  // nearest cue behind the playhead, so the last cue stays adjustable even
  // after it has finished on screen
  const handleTargetId = activeId ?? nearestBehind?.id ?? null;

  function timeAtClientX(clientX: number): number {
    const w = winRef.current ?? { start, span };
    const rect = trackRef.current!.getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    return w.start + ratio * w.span;
  }
  // Move the grabbed handle with `transform` (a GPU-composited pixel offset from
  // the pointer), NOT `left`. React owns the handle's `left` (its stable seg
  // position) and re-renders it every 250ms when the player clock ticks — if we
  // also drove `left` those two would fight and the handle would jump 4×/sec.
  // React never touches `transform`, so the drag offset survives every re-render.
  function paint(clientX: number) {
    const d = dragRef.current;
    const w = winRef.current;
    if (!d || !w) return;
    const deltaPx = clientX - d.startX;
    d.el.style.transform = `translateX(${-8 + deltaPx}px)`;
    const t = timeAtClientX(clientX);
    const lbl = labelRef.current;
    if (lbl) {
      lbl.style.left = `${clamp(((t - w.start) / w.span) * 100, 0, 100)}%`;
      lbl.textContent = fmt(t);
    }
  }

  function startDrag(e: React.PointerEvent, seg: Segment, which: "start" | "end") {
    e.stopPropagation();
    e.preventDefault();
    winRef.current = { start, span }; // freeze window for the whole drag
    const el = e.currentTarget as HTMLElement;
    el.classList.add("dragging");
    dragRef.current = { segId: seg.id, which, el, startX: e.clientX };
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* capture unavailable (e.g. synthetic pointer) — drag still works */
    }
    onDragActive?.(true); // freeze the player poll so re-renders don't stutter us
    setDragging(true); // shows the label + freezes the window
    paint(e.clientX);
  }
  function moveDrag(e: React.PointerEvent) {
    if (dragRef.current) paint(e.clientX);
  }
  function endDrag(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const t = timeAtClientX(e.clientX);
    d.el.classList.remove("dragging");
    d.el.style.transform = ""; // revert to the CSS centering; React re-renders left
    dragRef.current = null;
    winRef.current = null;
    setDragging(false);
    onDragActive?.(false);
    onBoundaryDrag(d.segId, t, d.which);
  }

  return (
    <div className="timing-strip">
      <div className="strip-track" ref={trackRef} onPointerMove={moveDrag} onPointerUp={endDrag}>
        {local.map((s) => {
          const left = clamp(((s.start - start) / span) * 100, 0, 100);
          const right = clamp(((s.end - start) / span) * 100, 0, 100);
          const isFocused = s.id === focusedId;
          const isActive = s.id === activeId;
          // every visible cue is draggable on both edges — not just the active
          // one — so you can retime any nearby subtitle without selecting it.
          // The focused/active/nearest cue's handles are emphasised, the rest dim.
          const emphasised = isFocused || isActive || s.id === handleTargetId;
          const dim = emphasised ? "" : " faint";
          return (
            <div key={s.id}>
              <button
                className={
                  "strip-seg" + (isActive ? " active" : "") + (isFocused ? " focused" : "")
                }
                style={{ left: `${left}%`, width: `${Math.max(1.5, right - left)}%` }}
                title={`#${segmentNo(segments, s.id)} ${fmt(s.start)} - ${fmt(s.end)}`}
                aria-label={`자막 ${segmentNo(segments, s.id)}로 이동`}
                onClick={() => onSeek(s.start)}
              />
              <span
                className={"strip-handle start" + dim}
                style={{ left: `${left}%` }}
                title="드래그해서 이 자막의 시작을 조절"
                onPointerDown={(e) => startDrag(e, s, "start")}
              />
              <span
                className={"strip-handle" + dim}
                style={{ left: `${right}%` }}
                title="드래그해서 이 자막의 끝을 조절 (넘기면 옆 자막이 밀림)"
                onPointerDown={(e) => startDrag(e, s, "end")}
              />
            </div>
          );
        })}
        <span className="strip-marker" style={{ left: `${marker}%` }} />
        {/* left + text are set imperatively during drag; React only owns display
            (via `dragging`) so it can't reset our imperative position each tick */}
        <span ref={labelRef} className="strip-drag-time" style={{ display: dragging ? "block" : "none" }} />
      </div>
      <div className="strip-meta">
        <span>{fmt(start)}</span>
        <span className="strip-hint">경계를 드래그해 미세조정</span>
        <span>{fmt(end)}</span>
      </div>
    </div>
  );
}

/* Speech map: word blocks on a mini timeline for the focused segment. Stands
   in for a waveform (the YouTube iframe gives no audio) — the reviewer SEES
   where speech vs silence is and drags the subtitle's start/end handles, which
   snap magnetically onto real word edges. Click empty space to seek there. */
function WordMap({
  seg,
  words,
  currentTime,
  onSeek,
  onCommit,
  onDragActive,
}: {
  seg: Segment;
  words: WordTime[];
  currentTime: number;
  onSeek: (t: number) => void;
  onCommit: (start: number, end: number) => void;
  onDragActive?: (active: boolean) => void;
}) {
  const PAD = 1.0;
  const SNAP = 0.12; // magnetic snap radius to a word edge (seconds)
  const trackRef = useRef<HTMLDivElement>(null);
  // imperative drag via `transform` (see TimingStrip): React owns the handle's
  // `left` and re-renders it on every 250ms clock tick, so we offset with a
  // GPU transform it never touches. Snap to a word edge only on RELEASE, so the
  // handle glides with the pointer instead of teleporting between words.
  const dragRef = useRef<{ which: "start" | "end"; el: HTMLElement; startX: number } | null>(
    null,
  );
  const [dragging, setDragging] = useState(false);

  const winStart = Math.max(0, seg.start - PAD);
  const winEnd = seg.end + PAD;
  const span = Math.max(0.5, winEnd - winStart);
  const local = words.filter((w) => w.end > winStart && w.start < winEnd);
  const pct = (t: number) => clamp(((t - winStart) / span) * 100, 0, 100);
  const start = seg.start;
  const end = seg.end;

  function timeAt(clientX: number): number {
    const r = trackRef.current!.getBoundingClientRect();
    return winStart + clamp((clientX - r.left) / r.width, 0, 1) * span;
  }
  function snap(t: number): number {
    let best: number | null = null;
    let bd = SNAP;
    for (const w of local) {
      for (const edge of [w.start, w.end]) {
        const dd = Math.abs(edge - t);
        if (dd < bd) {
          bd = dd;
          best = edge;
        }
      }
    }
    return best ?? t;
  }
  // move the grabbed handle with a GPU transform (no snap, no setState) so the
  // pointer is tracked smoothly; snapping happens on release in up()
  function paint(clientX: number) {
    const d = dragRef.current;
    if (!d) return;
    d.el.style.transform = `translateX(${-7 + (clientX - d.startX)}px)`;
  }
  function down(e: React.PointerEvent, which: "start" | "end") {
    e.stopPropagation();
    e.preventDefault();
    const el = e.currentTarget as HTMLElement;
    dragRef.current = { which, el, startX: e.clientX };
    try {
      el.setPointerCapture(e.pointerId);
    } catch {
      /* no capture — drag still works */
    }
    onDragActive?.(true); // freeze player poll so re-renders don't stutter us
    setDragging(true);
    paint(e.clientX);
  }
  function move(e: React.PointerEvent) {
    if (dragRef.current) paint(e.clientX);
  }
  function up(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const t = snap(timeAt(e.clientX)); // magnetic snap on release only
    const ns = d.which === "start" ? Math.min(t, seg.end - 0.1) : seg.start;
    const ne = d.which === "end" ? Math.max(t, seg.start + 0.1) : seg.end;
    d.el.style.transform = ""; // revert to CSS centering; React re-renders left
    dragRef.current = null;
    setDragging(false);
    onDragActive?.(false);
    onCommit(Math.round(ns * 1000) / 1000, Math.round(ne * 1000) / 1000);
  }

  const marker = currentTime >= winStart && currentTime <= winEnd ? pct(currentTime) : null;

  return (
    <div className="wordmap">
      <div
        className="wm-track"
        ref={trackRef}
        onPointerMove={move}
        onPointerUp={up}
        onClick={(e) => {
          if (!dragRef.current) onSeek(timeAt(e.clientX));
        }}
      >
        {/* selected span (current subtitle bounds) */}
        <span
          className="wm-band"
          style={{ left: `${pct(start)}%`, width: `${Math.max(0, pct(end) - pct(start))}%` }}
        />
        {/* recognized words = speech; empty = silence */}
        {local.map((w, i) => (
          <span
            key={i}
            className="wm-word"
            style={{ left: `${pct(w.start)}%`, width: `${Math.max(0.6, pct(w.end) - pct(w.start))}%` }}
            title={w.word.trim()}
          />
        ))}
        {marker !== null && <span className="wm-marker" style={{ left: `${marker}%` }} />}
        <span className="wm-handle s" style={{ left: `${pct(start)}%` }} onPointerDown={(e) => down(e, "start")} />
        <span className="wm-handle e" style={{ left: `${pct(end)}%` }} onPointerDown={(e) => down(e, "end")} />
      </div>
      <div className="wm-legend">
        <span>{fmt(start)}</span>
        <span className="wm-hint">
          {dragging ? "놓으면 가까운 단어 끝에 딱 붙어요" : "초록=말소리 · 손잡이를 끌어 시작/끝 맞추기"}
        </span>
        <span>{fmt(end)}</span>
      </div>
    </div>
  );
}

/* one editable time field (click, type, Enter/blur to apply) */
function TimeField({
  value,
  onCommit,
  title,
}: {
  value: number;
  onCommit: (v: number) => void;
  title: string;
}) {
  const [text, setText] = useState(fmt(value));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(fmt(value));
  }, [value, editing]);

  function commit() {
    const v = parseTime(text);
    if (v !== null && v !== value) onCommit(v);
    setEditing(false);
  }

  return (
    <input
      className="time-field"
      title={title + " — 클릭해서 직접 수정 (분:초.초)"}
      value={text}
      onFocus={() => setEditing(true)}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
          (e.target as HTMLInputElement).blur();
        }
        e.stopPropagation();
      }}
    />
  );
}

interface RowHandle {
  flush: () => Promise<void>;
  focus: () => void;
  segId: number;
}

interface UndoEntry {
  label: string;
  focusedId: number | null;
  segments: Segment[];
}

function snapshotSegments(segments: Segment[]): Segment[] {
  return segments.map((s) => ({ ...s }));
}

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "TEXTAREA" || el.tagName === "INPUT" || el.isContentEditable;
}

function isCellDeleteShortcut(e: KeyboardEvent): boolean {
  // deliberate 2-key combo only — never a bare Delete (that was a footgun that
  // could wipe a cue on a stray keypress outside the text box)
  return e.altKey && e.key === "Delete" && !e.ctrlKey && !e.metaKey && !e.shiftKey;
}

function isCellUndoShortcut(e: KeyboardEvent): boolean {
  return e.altKey && e.key.toLowerCase() === "z" && !e.ctrlKey && !e.metaKey && !e.shiftKey;
}

function Row({
  seg,
  active,
  focused,
  preview,
  currentTime,
  hasNext,
  koRef,
  words,
  register,
  onSeek,
  onSave,
  onTime,
  onSetTimes,
  onTiming,
  onStructure,
  onTyping,
  onFocusRow,
  onOpenRow,
  onDragActive,
}: {
  seg: Segment;
  active: boolean;
  focused: boolean;
  preview: boolean;
  currentTime: number;
  hasNext: boolean;
  koRef?: string;
  words: WordTime[];
  onDragActive?: (active: boolean) => void;
  register: (h: RowHandle | null) => void;
  onSeek: (t: number) => void;
  onSave: (id: number, text: string, reviewed: boolean | null, next: boolean) => Promise<void>;
  onTime: (seg: Segment, field: "start" | "end", value: number) => void;
  onSetTimes: (seg: Segment, start: number, end: number) => void;
  onTiming: (action: "start-here" | "next-here", seg: Segment) => void;
  onStructure: (action: "split" | "merge" | "delete", seg: Segment, position?: number) => void;
  onTyping: () => void;
  onFocusRow: (id: number) => void;
  onOpenRow: (seg: Segment) => void;
}) {
  const [text, setText] = useState(displayText(seg));
  const dirtyRef = useRef(false);
  const textRef = useRef(text);
  textRef.current = text;
  const ref = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const saveTimer = useRef<number | null>(null);

  useEffect(() => {
    setText(displayText(seg));
    dirtyRef.current = false;
  }, [seg.id, seg.text_final, seg.text_llm, seg.text_whisper]);

  // autosave + unmount flush: edits can never be lost by navigation
  async function flush() {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    if (dirtyRef.current) {
      dirtyRef.current = false;
      await onSave(seg.id, textRef.current, null, false);
    }
  }

  // one-click: replace the editable text with a machine source (no retyping
  // when whisper mangled a whole region but YouTube heard it right)
  function fillFrom(src: string) {
    setText(src);
    dirtyRef.current = false;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    void onSave(seg.id, src, null, false);
    taRef.current?.focus();
  }

  useEffect(() => {
    const handle: RowHandle = {
      flush,
      focus: () => taRef.current?.focus(),
      segId: seg.id,
    };
    register(handle);
    return () => {
      void flush();
      register(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg.id]);

  useEffect(() => {
    // in preview (theater) mode keep the playing cue centered so you can watch
    // the video and read ahead; while editing, only nudge it into view
    if (active) {
      ref.current?.scrollIntoView({
        block: preview ? "center" : "nearest",
        behavior: "smooth",
      });
    }
  }, [active, preview]);

  // show the reference panel whenever a machine source actually differs from
  // the working text — not only when the crosscheck flag fired. The flag uses a
  // lenient token-similarity threshold, so segments that disagree on key words
  // (e.g. whisper "보고삼" vs YouTube "부부삼") can slip through unflagged; the
  // reviewer still wants the reference there.
  const _norm = (s: string) => s.replace(/[^\w가-힣]/g, "");
  const _work = seg.text_final || seg.text_llm || seg.text_whisper;
  const _refDiffers =
    (seg.text_youtube.trim() !== "" && _norm(seg.text_youtube) !== _norm(_work)) ||
    (seg.text_whisper.trim() !== "" && _norm(seg.text_whisper) !== _norm(_work));
  const showSources = seg.flagged || seg.llm_uncertain || _refDiffers;
  // reading speed of the *current* (live-edited) text — flag if too fast to read
  const cps = text.replace(/\s+/g, "").length / Math.max(0.1, seg.end - seg.start);
  const tooFast = cps > 17;
  const playPct =
    currentTime >= seg.start && currentTime <= seg.end
      ? clamp(((currentTime - seg.start) / Math.max(0.001, seg.end - seg.start)) * 100, 0, 100)
      : null;
  // finished rows fold into a single quiet line — the list literally shrinks as
  // you work (momentum + far less scrolling). Click to reopen for a re-check.
  // In preview mode the currently-playing cue always expands so you can read it
  // in full as the video rolls over it.
  const collapsed = seg.reviewed && !focused && !(preview && active);

  return (
    <div
      ref={ref}
      className={
        "row" +
        (active ? " active" : "") +
        (focused ? " focused" : "") +
        (seg.reviewed ? " reviewed" : "") +
        (collapsed ? " collapsed" : "") +
        (seg.flagged || seg.llm_uncertain ? " needs-attention" : "") +
        (seg.safe && !seg.reviewed ? " safe" : "")
      }
    >
      <button
        type="button"
        className="collapsed-preview"
        title="펼쳐서 다시 보기"
        onClick={() => onOpenRow(seg)}
      >
        <span className="cp-check">✓</span>
        <span className="cp-text">{text}</span>
        <span className="cp-time">{fmt(seg.start)}</span>
      </button>
      <div className="row-head">
        <button className="time" onClick={() => onSeek(seg.start)} title="이 구간 재생">
          ▶
        </button>
        <span className="time-edit">
          {focused && (
            <button
              className="nudge-btn"
              title="시작 0.1초 앞으로"
              onClick={() => onTime(seg, "start", Math.max(0, seg.start - 0.1))}
            >
              ◀
            </button>
          )}
          <TimeField value={seg.start} title="시작 시간" onCommit={(v) => onTime(seg, "start", v)} />
          {focused && (
            <button
              className="nudge-btn"
              title="시작 0.1초 뒤로"
              onClick={() => onTime(seg, "start", Math.min(seg.end - 0.1, seg.start + 0.1))}
            >
              ▶
            </button>
          )}
        </span>
        <span className="time-sep">→</span>
        <span className="time-edit">
          {focused && (
            <button
              className="nudge-btn"
              title="끝 0.1초 앞으로"
              onClick={() => onTime(seg, "end", Math.max(seg.start + 0.1, seg.end - 0.1))}
            >
              ◀
            </button>
          )}
          <TimeField value={seg.end} title="끝 시간" onCommit={(v) => onTime(seg, "end", v)} />
          {focused && (
            <button
              className="nudge-btn"
              title="끝 0.1초 뒤로"
              onClick={() => onTime(seg, "end", seg.end + 0.1)}
            >
              ▶
            </button>
          )}
        </span>
        <span className="badges">
          {seg.flagged && (
            <span className="badge flag" title="음성인식과 유튜브 자막이 서로 다르게 들은 구간">
              서로 다름
            </span>
          )}
          {seg.llm_uncertain && (
            <span className="badge unc" title="AI가 확신하지 못한 구간">
              확인 필요
            </span>
          )}
          {tooFast && !seg.reviewed && (
            <span
              className="badge fast"
              title={`읽기 속도 ${cps.toFixed(0)}자/초 — 너무 빠릅니다. '나누기'로 쪼개거나 끝시간을 늘려 17자/초 이하로 (시청자가 못 읽음)`}
            >
              ⏩ 빠름 {cps.toFixed(0)}
            </span>
          )}
          {seg.safe && !seg.reviewed && (
            <span className="badge safe" title="두 음성인식이 일치하고 어려운 용어도 없고 읽기 속도도 편안한 안심 구간">
              안심
            </span>
          )}
          {seg.reviewed && <span className="badge ok">확인 완료</span>}
        </span>
      </div>
      {playPct !== null && (
        <div className="cue-rail" title={`영상 위치 ${fmt(currentTime)}`}>
          <span className="cue-fill" style={{ width: `${playPct}%` }} />
          <span className="cue-dot" style={{ left: `${playPct}%` }} />
        </div>
      )}
      {koRef && (
        <div className="ko-ref" title="번역 원문 (한국어) — 참고용, 수정 불가">
          <span className="ko-ref-label">원문</span>
          <span className="ko-ref-text">{koRef}</span>
        </div>
      )}
      <textarea
        ref={taRef}
        value={text}
        rows={Math.max(2, Math.ceil(text.length / 40))}
        onFocus={() => {
          onFocusRow(seg.id);
          // pause once when you START editing this segment — not on every
          // keystroke. Lets you replay/loop and keep listening while you type.
          onTyping();
        }}
        onChange={(e) => {
          setText(e.target.value);
          dirtyRef.current = true;
          if (saveTimer.current) window.clearTimeout(saveTimer.current);
          saveTimer.current = window.setTimeout(() => void flush(), 900);
        }}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return; // 한글 조합 중 무시
          if (e.key === "Enter" && e.ctrlKey && e.shiftKey) {
            // Amara 관례: Ctrl+Shift+Enter = 병합
            e.preventDefault();
            void flush().then(() => onStructure("merge", seg));
          } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            // Amara 관례: Ctrl+Enter = 커서 위치에서 분할
            e.preventDefault();
            void flush().then(() => onStructure("split", seg, taRef.current?.selectionStart ?? 0));
          } else if (e.key === "Enter") {
            // Enter = 확정하고 다음 자막으로 (줄바꿈은 내보낼 때 자동)
            e.preventDefault();
            dirtyRef.current = false;
            if (saveTimer.current) window.clearTimeout(saveTimer.current);
            void onSave(seg.id, text, true, true);
          }
        }}
        onBlur={() => void flush()}
      />
      {focused && words.length > 0 && (
        <WordMap
          seg={seg}
          words={words}
          currentTime={currentTime}
          onSeek={onSeek}
          onCommit={(s, e) => onSetTimes(seg, s, e)}
          onDragActive={onDragActive}
        />
      )}
      {seg.suspect && !seg.reviewed && focused && (
        <div
          className="lowconf"
          title="음성인식과 유튜브 자막이 다르게 들은 단어 — 여기부터 확인하세요"
        >
          ⚠️ 의심 단어: {seg.suspect}
        </div>
      )}
      {focused && showSources && (
        <div className="sources">
          <div className="sources-title">
            참고용 — 기계가 각자 들은 내용. 맞는 걸 <b>가져오기</b>로 바로 채울 수 있어요
          </div>
          {seg.text_whisper.trim() ? (
            <div className="src-line">
              <span className="src-label w">음성인식</span>
              <span className="src-text">{seg.text_whisper}</span>
              <button className="src-fill" title="이 내용을 편집칸에 채우기" onClick={() => fillFrom(seg.text_whisper.trim())}>
                가져오기
              </button>
            </div>
          ) : (
            <div className="src-line">
              <span className="src-label w">음성인식</span>
              <span className="src-text src-empty">
                이 구간은 음성인식이 놓쳐서 유튜브 자막으로 채웠습니다
              </span>
            </div>
          )}
          {seg.text_youtube && (
            <div className="src-line">
              <span className="src-label y">유튜브 자막</span>
              <span className="src-text">{seg.text_youtube}</span>
              <button className="src-fill" title="이 내용을 편집칸에 채우기" onClick={() => fillFrom(seg.text_youtube.trim())}>
                가져오기
              </button>
            </div>
          )}
        </div>
      )}
      <div className="row-foot">
        <label className="reviewed-check">
          <input
            type="checkbox"
            checked={seg.reviewed}
            onChange={(e) => onSave(seg.id, text, e.target.checked, false)}
          />
          확인 완료
        </label>
        {focused && (
        <>
        <span className="timing-tools">
          <button
            title="현재 영상 시간을 이 자막의 시작으로 맞추고, 이전 자막 끝도 같이 맞춤 (Alt+[)"
            onClick={() => void flush().then(() => onTiming("start-here", seg))}
          >
            여기서 시작
          </button>
          <button
            title="현재 영상 시간에서 이 자막을 끝내고 다음 자막으로 넘김 (Alt+])"
            onClick={() => void flush().then(() => onTiming("next-here", seg))}
          >
            {hasNext ? "여기서 넘김" : "여기서 끝"}
          </button>
          {words.length > 0 && (
            <button
              title="이 자막을 실제 발화 시작~끝에 자동으로 딱 맞춤 (앞뒤 침묵 제거) (Alt+\\)"
              onClick={() => {
                const inside = words.filter((w) => {
                  const m = (w.start + w.end) / 2;
                  return seg.start <= m && m < seg.end;
                });
                if (inside.length) {
                  const ns = Math.min(...inside.map((w) => w.start));
                  const ne = Math.max(...inside.map((w) => w.end));
                  onSetTimes(seg, Math.round(ns * 1000) / 1000, Math.round(ne * 1000) / 1000);
                }
              }}
            >
              ⤢ 발화 맞춤
            </button>
          )}
        </span>
        <span className="structure">
          <button
            title="텍스트 커서 위치에서 자막을 둘로 나누기 (Ctrl+Enter)"
            onClick={() => {
              void flush().then(() => onStructure("split", seg, taRef.current?.selectionStart ?? 0));
            }}
          >
            ✂ 나누기
          </button>
          <button
            title="아래 자막과 합치기 (Ctrl+Shift+Enter)"
            onClick={() => {
              void flush().then(() => onStructure("merge", seg));
            }}
          >
            ⇣ 합치기
          </button>
          <button
            className="danger"
            title="이 자막을 바로 지움 (Ctrl+Z로 복구)"
            onClick={() => {
              void flush().then(() => onStructure("delete", seg));
            }}
          >
            ✕ 지우기
          </button>
        </span>
        </>
        )}
      </div>
    </div>
  );
}

interface ShortcutItem {
  keys: string[];
  label: string;
  detail?: string;
}

interface ShortcutGroup {
  title: string;
  items: ShortcutItem[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "재생·이동  (화살표는 언제나 이동만 — 안전)",
    items: [
      { keys: ["Tab"], label: "재생 / 일시정지", detail: "스페이스바는 글자 입력용" },
      { keys: ["Ctrl+←", "Ctrl+→"], label: "3초 뒤로 / 앞으로", detail: "Shift+Tab도 3초 뒤로" },
      { keys: ["Ctrl+Shift+←", "Ctrl+Shift+→"], label: "10초 뒤로 / 앞으로" },
      { keys: ["Ctrl+\\"], label: "이 자막 처음부터 다시 재생", detail: "편집 중에도 됩니다" },
      { keys: ["Alt+↑", "Alt+↓"], label: "이전 / 다음 자막" },
      {
        keys: ["Alt+Shift+↑", "Alt+Shift+↓"],
        label: "이전 / 다음 미검수 자막",
        detail: "확인한 건 건너뜁니다",
      },
    ],
  },
  {
    title: "자막 확정·구조  (Enter 계열 · 모두 되돌리기 가능)",
    items: [
      { keys: ["Enter"], label: "확인 완료하고 다음 자막으로" },
      { keys: ["Ctrl+Enter"], label: "커서 위치에서 자막 나누기" },
      { keys: ["Ctrl+Shift+Enter"], label: "아래 자막과 합치기" },
      { keys: ["Alt+Delete"], label: "이 자막 삭제", detail: "편집 중에도, Alt+Z로 복구" },
      {
        keys: ["Alt+Z"],
        label: "방금 조작 되돌리기",
        detail: "나누기·합치기·삭제·시간까지, 편집 중에도",
      },
    ],
  },
  {
    title: "시간 맞추기  (Alt + 대괄호)",
    items: [
      { keys: ["Alt+["], label: "여기서 시작", detail: "재생 위치를 이 자막 시작점으로" },
      { keys: ["Alt+]"], label: "여기서 넘김", detail: "재생 위치에서 끝내고 다음으로" },
      { keys: ["Alt+\\"], label: "발화 맞춤", detail: "말소리 시작~끝에 자동으로" },
      { keys: ["드래그", "◀▶"], label: "미세 조정", detail: "타임라인 손잡이 드래그 · 시간 옆 ◀▶ 버튼" },
    ],
  },
  {
    title: "입력칸 안에서 (글자)",
    items: [
      {
        keys: ["Delete", "Ctrl+Z"],
        label: "글자 삭제 / 되돌리기",
        detail: "편집칸 안에서는 평범한 텍스트 편집으로 동작",
      },
    ],
  },
  {
    title: "모드·도구",
    items: [
      { keys: ["Alt+P"], label: "미리보기 모드", detail: "영상 크게 + 자막 따라 스크롤" },
      { keys: ["Alt+R"], label: "구간 반복 켜기 / 끄기" },
      { keys: ["Alt+S"], label: "편집 시작 시 멈춤 켜기 / 끄기" },
      { keys: ["Alt+B"], label: "찾기·바꾸기 열기" },
      { keys: ["Alt+M"], label: "무음 다듬기" },
      { keys: ["Alt+G"], label: "복구·채우기" },
      { keys: ["Alt+K"], label: "학습(피드백 흡수)" },
    ],
  },
];

export function Editor({
  videoId,
  onBack,
  koComplete,
  timingDone: initialTimingDone,
  initialLang = "ko",
  languages = [],
}: {
  videoId: string;
  onBack: () => void;
  koComplete: boolean;
  timingDone: boolean;
  initialLang?: string;
  languages?: { code: string; forked: boolean; timing_done: boolean }[];
}) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [timingDone, setTimingDoneState] = useState(initialTimingDone);
  // per-forked-track timing-done (ko uses `timingDone`); synced from the job's
  // languages when the active forked track changes
  const [langTimingDone, setLangTimingDone] = useState(false);
  const forkedLangs = new Set(languages.filter((l) => l.forked).map((l) => l.code));
  const [koDoneSeen, setKoDoneSeen] = useState(koComplete);
  const [error, setError] = useState("");
  const [absorbMsg, setAbsorbMsg] = useState("");
  const [langs, setLangs] = useState<{ code: string; label: string }[]>([]);
  const [lang, setLang] = useState(initialLang);
  const [exporting, setExporting] = useState(false);
  const [pauseOnType, setPauseOnType] = useState(true);
  const [loopSeg, setLoopSeg] = useState(false);
  // preview (theater) mode: big video + on-video caption + follow-along scroll.
  // off by default — editing is the primary task; turn on for the final watch.
  const [showPreview, setShowPreview] = useState(false);
  const [showKeys, setShowKeys] = useState(true);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const [findOpen, setFindOpen] = useState(false);
  const [findText, setFindText] = useState("");
  const [replText, setReplText] = useState("");
  const [findMatches, setFindMatches] = useState<number | null>(null);
  const [eta, setEta] = useState("");
  const [celebrate, setCelebrate] = useState(false);
  const [words, setWords] = useState<WordTime[]>([]);
  // for the on-video preview overlay when reviewing a translation: segment_id → text
  const [transMap, setTransMap] = useState<Record<number, string>>({});
  // Korean source segments, shown as a read-only reference while editing a
  // forked translation track (matched by time overlap since idx diverges)
  const [koRefSegs, setKoRefSegs] = useState<Segment[]>([]);
  // bumped when TranslateReview generates/saves translations, so the transMap
  // effect refetches and the fork button / overlay appear without a track switch
  const [transRefresh, setTransRefresh] = useState(0);
  // set true while a timeline handle is being dragged → freezes the player's
  // 250ms clock poll so the editor stops re-rendering and the main thread stays
  // free, letting the dragged handle track the pointer without stutter
  const dragFreezeRef = useRef(false);
  const { currentTime, playing, seekTo, seekBy, play, pause, playPause } = usePlayer(
    videoId,
    dragFreezeRef,
  );

  const rowsRef = useRef(new Map<number, RowHandle>());
  const focusedIdRef = useRef<number | null>(null);
  const segmentsRef = useRef<Segment[]>([]);
  const undoStackRef = useRef<UndoEntry[]>([]);
  const paceRef = useRef<number[]>([]); // timestamps of recent confirms → pace
  const prevReviewedRef = useRef(0);
  const prevPctRef = useRef(0);
  segmentsRef.current = segments;
  undoStackRef.current = undoStack;

  useEffect(() => {
    fetchLanguages().then(setLangs).catch(() => {});
    fetchWords(videoId).then(setWords).catch(() => setWords([]));
  }, [videoId]);

  // segments for the CURRENT track (ko source, or a forked language). Empty for
  // a non-forked translation language → the translation-review view is shown.
  useEffect(() => {
    // undo is per-track: restore_segments is scoped to one lang and reinserts
    // by original id. A snapshot from another track carries foreign ids that
    // collide on restore (500). Clear undo/focus whenever the track changes.
    setUndoStack([]);
    undoStackRef.current = [];
    setFocusedId(null);
    fetchSegments(videoId, lang)
      .then((nextSegments) => {
        segmentsRef.current = nextSegments;
        setSegments(nextSegments);
      })
      .catch((e) => setError(String(e)));
  }, [videoId, lang]);

  // on-video preview overlay for a translation: keep a fresh segment→text map
  // (refetched when preview is toggled, so edits in the list show up)
  useEffect(() => {
    if (lang === "ko") {
      setTransMap({});
      return;
    }
    fetchTranslations(videoId, lang)
      .then((rows) => {
        const m: Record<number, string> = {};
        for (const r of rows) if (r.text) m[r.segment_id] = r.text;
        setTransMap(m);
      })
      .catch(() => setTransMap({}));
  }, [videoId, lang, showPreview, transRefresh]);

  // Korean source, kept alongside a forked translation track so each row can
  // show the original as read-only reference (idx diverges after split/merge,
  // so rows are matched by time overlap, not index)
  useEffect(() => {
    if (lang === "ko") {
      setKoRefSegs([]);
      return;
    }
    fetchSegments(videoId, "ko")
      .then(setKoRefSegs)
      .catch(() => setKoRefSegs([]));
  }, [videoId, lang]);

  // sync the forked track's timing-done state when the active track changes
  useEffect(() => {
    if (lang === "ko") return;
    setLangTimingDone(languages.find((l) => l.code === lang)?.timing_done ?? false);
  }, [lang, languages]);

  // live match-count preview for find & replace (debounced)
  useEffect(() => {
    if (!findOpen || !findText.trim()) {
      setFindMatches(null);
      return;
    }
    const t = window.setTimeout(() => {
      replaceText(videoId, findText, "", false, lang)
        .then((r) => setFindMatches(r.matches))
        .catch(() => setFindMatches(null));
    }, 350);
    return () => window.clearTimeout(t);
    // lang: re-query the count when the active track changes, else the "N곳"
    // preview keeps the previous track's number while replace uses the new lang
  }, [findText, findOpen, videoId, lang]);

  // 어떤 경로로 떠나도 수정 내용은 저장된다 (구조적 보장)
  async function flushAll() {
    await Promise.all(Array.from(rowsRef.current.values()).map((h) => h.flush()));
  }
  useEffect(() => {
    const onUnload = () => void flushAll();
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      void flushAll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 안내 메시지는 잠깐 보여주고 스스로 사라진다 (화면에 계속 남지 않게)
  useEffect(() => {
    if (!statusMsg) return;
    const t = window.setTimeout(() => setStatusMsg(""), 4000);
    return () => window.clearTimeout(t);
  }, [statusMsg]);
  useEffect(() => {
    if (!absorbMsg) return;
    const t = window.setTimeout(() => setAbsorbMsg(""), 8000);
    return () => window.clearTimeout(t);
  }, [absorbMsg]);
  useEffect(() => {
    if (!error) return;
    const t = window.setTimeout(() => setError(""), 6000);
    return () => window.clearTimeout(t);
  }, [error]);

  const activeId = useMemo(() => {
    const s = segments.find((x) => currentTime >= x.start && currentTime < x.end);
    return s?.id;
  }, [segments, currentTime]);
  const activeSeg = useMemo(() => segments.find((s) => s.id === activeId), [segments, activeId]);
  const focusedSeg = useMemo(() => segments.find((s) => s.id === focusedId), [segments, focusedId]);

  // loop the current segment's audio while editing (hands-free re-listen)
  useEffect(() => {
    if (!loopSeg || !playing || !focusedSeg) return;
    if (currentTime >= focusedSeg.end - 0.04) seekTo(focusedSeg.start);
  }, [currentTime, loopSeg, playing, focusedSeg, seekTo]);

  const nReviewed = segments.filter((s) => s.reviewed).length;
  const nRemaining = Math.max(0, segments.length - nReviewed);
  const nSafe = segments.filter((s) => s.safe && !s.reviewed).length;
  const reviewedPct = segments.length ? Math.round((nReviewed / segments.length) * 100) : 0;
  const langLabel = langs.find((l) => l.code === lang)?.label ?? lang;
  const isKo = lang === "ko";
  // a forked translation track has its own segments; a non-forked one shows the
  // lighter translation-review view (inherits Korean structure/timing)
  const forked = !isKo && segments.length > 0;
  // the koComplete prop is a frozen snapshot from the landing list; unlock the
  // translation languages the moment the Korean track hits 100% in-editor, so
  // the reviewer doesn't have to exit and re-open at the hand-off.
  const koTrackDone = isKo && segments.length > 0 && nReviewed === segments.length;
  useEffect(() => {
    if (koTrackDone) setKoDoneSeen(true);
  }, [koTrackDone]);
  const koDone = koComplete || koDoneSeen;

  // never let a locked language stay selected — EXCEPT a forked track, which is
  // fully independent of Korean completeness (it has its own segments). Only a
  // non-forked (inherited) translation is gated on Korean being done. Explain
  // the snap-back so the reviewer isn't silently bounced to Korean.
  useEffect(() => {
    if (lang !== "ko" && !koDone && segments.length === 0) {
      setLang("ko");
      setStatusMsg("한국어 검수가 미완이라 번역 트랙(상속)을 열 수 없습니다 — 한국어를 먼저 끝내세요");
    }
  }, [lang, koDone, segments]);

  // review pace → soft ETA ("이 속도면 약 N분 남음"), and gentle milestone
  // pulses at 25/50/75/100% — both cut the "endless list" fatigue without
  // adding any new chrome (ETA rides the hero, milestone rides the statusbar).
  useEffect(() => {
    if (nReviewed > prevReviewedRef.current) {
      const arr = paceRef.current;
      arr.push(performance.now());
      if (arr.length > 12) arr.shift();
    }
    prevReviewedRef.current = nReviewed;
    const p = paceRef.current;
    if (p.length >= 3 && nRemaining > 0) {
      const per = (p[p.length - 1] - p[0]) / (p.length - 1);
      const min = Math.round((per * nRemaining) / 60000);
      setEta(`이 속도면 약 ${Math.max(1, min)}분 남음`);
    } else {
      setEta("");
    }
  }, [nReviewed, nRemaining]);

  useEffect(() => {
    const mark = [25, 50, 75, 100].find((m) => prevPctRef.current < m && reviewedPct >= m);
    prevPctRef.current = reviewedPct;
    if (mark) {
      setStatusMsg(mark === 100 ? "모두 확인 완료 🎉 수고하셨어요" : `${mark}% 통과 — 좋아요 👏`);
      setCelebrate(true);
      const t = window.setTimeout(() => setCelebrate(false), 900);
      return () => window.clearTimeout(t);
    }
  }, [reviewedPct]);

  function markFocused(id: number) {
    focusedIdRef.current = id;
    setFocusedId(id);
  }

  function nextWorkTarget(list: Segment[], fromId: number | null | undefined): Segment | undefined {
    if (!list.length) return undefined;
    const fromIndex = fromId != null ? list.findIndex((s) => s.id === fromId) : -1;
    const startIndex = fromIndex >= 0 ? fromIndex + 1 : 0;
    return (
      list.slice(startIndex).find((s) => !s.reviewed) ??
      list.find((s) => !s.reviewed) ??
      (fromIndex >= 0 ? list[fromIndex + 1] : undefined) ??
      list[0]
    );
  }

  function nextTimelineTarget(list: Segment[], previous: Segment): Segment | undefined {
    return list.find((s) => s.start >= previous.start) ?? list[list.length - 1];
  }

  function focusSegment(seg: Segment | undefined) {
    if (!seg) {
      focusedIdRef.current = null;
      setFocusedId(null);
      return;
    }
    focusedIdRef.current = seg.id;
    setFocusedId(seg.id);
    seekTo(seg.start);
    window.setTimeout(() => rowsRef.current.get(seg.id)?.focus(), 0);
  }


  // replay the subtitle you're on, from its start (works while typing)
  function replayCurrent() {
    const segs = segmentsRef.current;
    const cur =
      segs.find((s) => s.id === focusedIdRef.current) ??
      segs.find((s) => currentTime >= s.start && currentTime < s.end) ??
      segs.find((s) => s.id === activeId);
    if (cur) {
      seekTo(cur.start);
      play();
    }
  }

  async function continueWork() {
    await flushAll();
    const target = nextWorkTarget(segmentsRef.current, focusedIdRef.current ?? activeId ?? null);
    focusSegment(target);
    setStatusMsg(target ? "이어서 작업할 자막으로 이동했습니다" : "이동할 자막이 없습니다");
  }

  function pushUndo(label: string) {
    const entry: UndoEntry = {
      label,
      focusedId: focusedIdRef.current,
      segments: snapshotSegments(segmentsRef.current),
    };
    setUndoStack((prev) => [...prev.slice(-19), entry]);
  }

  async function undoLast() {
    const entry = undoStackRef.current[undoStackRef.current.length - 1];
    if (!entry) return;
    try {
      await flushAll();
      const restored = await restoreSegments(videoId, entry.segments, lang);
      segmentsRef.current = restored;
      setSegments(restored);
      setUndoStack((prev) => prev.slice(0, -1));
      focusedIdRef.current = entry.focusedId;
      setFocusedId(entry.focusedId);
      setStatusMsg(`${entry.label} 되돌림`);
      if (entry.focusedId) {
        window.setTimeout(() => rowsRef.current.get(entry.focusedId ?? -1)?.focus(), 0);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  // ---- global keyboard workflow (Amara/YouTube Studio conventions)
  useEffect(() => {
    function currentRow(): Segment | undefined {
      const segs = segmentsRef.current;
      return (
        segs.find((s) => s.id === focusedIdRef.current) ??
        segs.find((s) => currentTime >= s.start && currentTime < s.end)
      );
    }
    function deleteRow(row: Segment | undefined) {
      if (!row) return;
      const handle = rowsRef.current.get(row.id);
      void (handle ? handle.flush() : Promise.resolve()).then(() => structure("delete", row));
    }
    function onKey(e: KeyboardEvent) {
      if ((e as any).isComposing) return;
      if (isCellUndoShortcut(e)) {
        e.preventDefault();
        void undoLast();
        return;
      }
      if (isCellDeleteShortcut(e)) {
        e.preventDefault();
        deleteRow(currentRow());
        return;
      }
      // ---- replay current cue from its start (Ctrl+\), safe while typing ----
      if ((e.ctrlKey || e.metaKey) && (e.code === "Backslash" || e.key === "\\")) {
        e.preventDefault();
        replayCurrent();
        return;
      }

      // ===== PLAYBACK & NAVIGATION — arrows and Tab NEVER edit data, so a
      // mis-press or a slipped Shift can only move the playhead/selection =====
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (e.shiftKey) seekBy(-3);
        else playPause();
        return;
      }
      if (e.code === "Space" && !e.ctrlKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault();
        playPause();
        return;
      }
      // seek: Ctrl+←/→ = ∓3s, Ctrl+Shift+←/→ = ∓10s. On Ctrl (not Alt) so it can
      // never trigger Chrome's Alt+←/→ back/forward navigation. Skipped inside a
      // text field so Ctrl+←/→ keeps its native word-jump while editing.
      if (
        (e.ctrlKey || e.metaKey) &&
        !e.altKey &&
        (e.key === "ArrowLeft" || e.key === "ArrowRight") &&
        !isTypingTarget(e.target)
      ) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 3;
        seekBy(e.key === "ArrowLeft" ? -step : step);
        return;
      }
      // swallow Alt+←/→ entirely so a stray press can't send Chrome back/forward
      if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        e.preventDefault();
        return;
      }
      // Alt+↑/↓ = prev/next cue, Alt+Shift+↑/↓ = prev/next UNREVIEWED cue
      if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        e.preventDefault();
        const segs = segmentsRef.current;
        if (!segs.length) return;
        const dir = e.key === "ArrowDown" ? 1 : -1;
        const cur = currentRow();
        if (e.shiftKey) {
          const from = cur ? segs.findIndex((s) => s.id === cur.id) : dir === 1 ? -1 : segs.length;
          for (let i = from + dir; i >= 0 && i < segs.length; i += dir) {
            if (!segs[i].reviewed) {
              focusSegment(segs[i]);
              return;
            }
          }
          return;
        }
        if (!cur) return;
        const next = segs[segs.findIndex((s) => s.id === cur.id) + dir];
        if (next) focusSegment(next);
        return;
      }
      // cue timing on the focused subtitle (Alt + [ ] \) — in/out-point keys,
      // kept OFF the , . seek keys so a missed Shift can never mangle a boundary
      if (e.altKey && !e.ctrlKey && !e.shiftKey && (e.key === "[" || e.key === "]" || e.key === "\\")) {
        e.preventDefault();
        const row = currentRow();
        if (!row) return;
        const h = rowsRef.current.get(row.id);
        const flushThen = (fn: () => void) =>
          void (h ? h.flush() : Promise.resolve()).then(fn);
        if (e.key === "[") flushThen(() => timing("start-here", row));
        else if (e.key === "]") flushThen(() => timing("next-here", row));
        else {
          const inside = words.filter((w) => {
            const m = (w.start + w.end) / 2;
            return row.start <= m && m < row.end;
          });
          if (inside.length) {
            const ns = Math.min(...inside.map((w) => w.start));
            const ne = Math.max(...inside.map((w) => w.end));
            setTimes(row, Math.round(ns * 1000) / 1000, Math.round(ne * 1000) / 1000);
          }
        }
        return;
      }
      // mode toggles + left-panel tools (Alt + letter) — safe while typing
      if (e.altKey && !e.ctrlKey && !e.shiftKey && /^[a-z]$/i.test(e.key)) {
        const actions: Record<string, () => void> = {
          r: () => setLoopSeg((v) => !v),
          s: () => setPauseOnType((v) => !v),
          p: () => setShowPreview((v) => !v),
          b: () => setFindOpen((v) => !v),
          g: () => void runRepair(),
          m: () => void runTighten(),
          k: () => void runAbsorb(),
        };
        const act = actions[e.key.toLowerCase()];
        if (act) {
          e.preventDefault();
          act();
          return;
        }
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTime]);

  async function save(id: number, text: string, reviewed: boolean | null, next: boolean) {
    try {
      const body: Parameters<typeof updateSegment>[1] = { text_final: text };
      if (reviewed !== null) body.reviewed = reviewed;
      const updated = await updateSegment(id, body);
      const nextSegments = segmentsRef.current.map((s) => (s.id === id ? updated : s));
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      if (next) {
        focusSegment(nextWorkTarget(nextSegments, id));
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function timeChange(seg: Segment, field: "start" | "end", value: number) {
    try {
      pushUndo("시간 조정");
      await updateSegment(seg.id, { [field]: Math.max(0, Math.round(value * 1000) / 1000) });
      const nextSegments = await fetchSegments(videoId, lang);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      setStatusMsg("시간 조정됨 - Ctrl+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  // timeline-strip edge drag: hybrid neighbour push (see edge_drag endpoint)
  async function edgeDragCommit(seg: Segment, which: "start" | "end", time: number) {
    try {
      pushUndo("시간 조정");
      await edgeDrag(seg.id, which, Math.max(0, Math.round(time * 1000) / 1000));
      const nextSegments = await fetchSegments(videoId, lang);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      setStatusMsg("시간 조정됨 - Ctrl+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  // set both bounds at once (speech-map drag / 발화 맞춤) — one undo step
  async function setTimes(seg: Segment, start: number, end: number) {
    try {
      pushUndo("시간 맞춤");
      await updateSegment(seg.id, {
        start: Math.max(0, start),
        end: Math.max(start + 0.1, end),
      });
      const nextSegments = await fetchSegments(videoId, lang);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      setStatusMsg("발화 구간에 맞췄습니다 - Ctrl+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  async function timing(action: "start-here" | "next-here", seg: Segment, atTime?: number) {
    try {
      const t = atTime ?? currentTime;
      pushUndo(action === "start-here" ? "시작 맞춤" : "넘김 맞춤");
      if (action === "start-here") {
        await boundaryPrev(seg.id, t);
      } else {
        await boundaryNext(seg.id, t);
      }
      const nextSegments = await fetchSegments(videoId, lang);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      setStatusMsg("경계가 맞춰졌습니다 - Ctrl+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  async function structure(action: "split" | "merge" | "delete", seg: Segment, position?: number) {
    try {
      const label = action === "split" ? "나누기" : action === "merge" ? "합치기" : "삭제";
      pushUndo(label);
      if (action === "split") await splitSegment(seg.id, position ?? 0);
      else if (action === "merge") await mergeNext(seg.id);
      else await deleteSegment(seg.id);
      const nextSegments = await fetchSegments(videoId, lang);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      if (action === "delete") focusSegment(nextTimelineTarget(nextSegments, seg));
      setStatusMsg(
        action === "delete"
          ? "자막을 지웠습니다 - Ctrl+Z로 바로 복구할 수 있습니다"
          : `${label} 완료 - Ctrl+Z로 되돌릴 수 있습니다`,
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function refreshSegments() {
    const next = await fetchSegments(videoId, lang);
    segmentsRef.current = next;
    setSegments(next);
  }

  async function applyReplace() {
    if (!findText.trim()) return;
    try {
      const r = await replaceText(videoId, findText, replText, true, lang);
      await refreshSegments();
      setFindMatches(null);
      setStatusMsg(
        r.matches
          ? `"${findText}" → "${replText || "(삭제)"}" · 자막 ${r.segments}개에서 ${r.matches}곳 바꿨습니다`
          : "바꿀 내용을 찾지 못했습니다",
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runFork() {
    try {
      // flush any in-flight translation edit first: TranslateReview autosaves on
      // blur (fire-and-forget), and fork_track copies from the Translation rows
      // then deletes them — a mid-edit fork could copy the pre-edit value and
      // lose the just-typed text. Blur the active field and let its save land.
      (document.activeElement as HTMLElement | null)?.blur();
      await new Promise((r) => setTimeout(r, 250));
      await forkTrack(videoId, lang);
      const next = await fetchSegments(videoId, lang);
      segmentsRef.current = next;
      setSegments(next);
      setFocusedId(null);
      focusedIdRef.current = null;
      setStatusMsg(`${langLabel} 트랙을 독립 편집으로 전환했습니다 — 이제 언어별로 분할·타이밍 가능`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function runUnfork() {
    if (
      !window.confirm(
        `${langLabel} 독립 편집을 해제하고 한국어 구조를 따르는 번역 검수로 되돌립니다.\n` +
          `편집한 번역 텍스트는 한국어 자막에 맞춰 복원됩니다 (재분할한 경우 근사 복원). 계속할까요?`,
      )
    )
      return;
    try {
      await unforkTrack(videoId, lang);
      setUndoStack([]);
      undoStackRef.current = [];
      const next = await fetchSegments(videoId, lang);
      segmentsRef.current = next;
      setSegments(next);
      setFocusedId(null);
      focusedIdRef.current = null;
      setTransRefresh((n) => n + 1);
      setStatusMsg(`${langLabel} 독립 편집을 해제했습니다 — 번역 검수 화면으로 복귀`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function toggleTimingDone() {
    try {
      const current = isKo ? timingDone : langTimingDone;
      const r = await setTimingDone(videoId, !current, lang);
      if (isKo) setTimingDoneState(r.timing_done);
      else setLangTimingDone(r.timing_done);
      setStatusMsg(
        r.timing_done
          ? `${langLabel} 타이밍 검수 완료로 표시했습니다`
          : `${langLabel} 타이밍 검수 미완으로 되돌렸습니다`,
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runRepair() {
    await flushAll();
    try {
      const r = await repairStt(videoId);
      await refreshSegments();
      const parts: string[] = [];
      if (r.repaired) parts.push(`오류 ${r.repaired}곳 복구`);
      if (r.filled) parts.push(`빈 구간 ${r.filled}곳 유튜브 자막으로 채움`);
      setStatusMsg(
        parts.length
          ? `${parts.join(", ")} (유튜브 자막 기반, 검수 필요)` +
              (r.no_caption ? ` · 자막 없는 ${r.no_caption}곳은 직접 수정` : "")
          : "복구·보충할 구간을 찾지 못했습니다",
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runTighten() {
    await flushAll();
    try {
      const r = await tightenTiming(videoId);
      await refreshSegments();
      setStatusMsg(
        r.tightened
          ? `${r.tightened}개 자막을 실제 발화 구간에 맞춰 다듬었습니다 — 침묵 구간엔 자막이 사라집니다`
          : "이미 발화 구간에 맞게 다듬어져 있습니다",
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runConfirmSafe() {
    await flushAll();
    try {
      const r = await confirmSafe(videoId);
      await refreshSegments();
      setStatusMsg(
        `안심 구간 ${r.confirmed}개를 한번에 확인했습니다 — 이제 표시된 구간만 검수하세요`,
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runAbsorb() {
    await flushAll();
    try {
      const r = await absorbFeedback(videoId);
      await refreshSegments();
      setAbsorbMsg(
        `학습 완료 — 확인한 자막 ${r.reviewed_segments}개에서 고침 ${r.new_pairs}가지를 새로 배웠습니다` +
          (r.bumped ? ` (${r.bumped}가지는 더 확실해짐)` : "") +
          (r.propagated_segments
            ? `, 뒤쪽 자막 ${r.propagated_segments}개에 ${r.propagated_replacements}곳 반영`
            : ""),
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function runExport() {
    await flushAll();
    setExporting(true);
    try {
      const r = await fetch(exportUrl(videoId, "best", lang));
      if (!r.ok) throw new Error(`export: ${r.status}`);
      const blob = await r.blob();
      const cd = r.headers.get("content-disposition") ?? "";
      const m = /filename\*=utf-8''([^;]+)/i.exec(cd);
      const name = m ? decodeURIComponent(m[1]) : `${lang}_${videoId}_자막.srt`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setError(String(e));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className={"editor" + (showPreview ? " preview" : "")}>
      <div className="left">
        <div className="left-top">
          <button
            className="back"
            onClick={async () => {
              await flushAll();
              onBack();
            }}
          >
            ← 목록
          </button>
          <ThemeToggle />
        </div>
        <div className="player-wrap">
          <div id="yt-player" />
          {showPreview &&
            (() => {
              // show the language being reviewed on the video, not Korean.
              let cc = "";
              if (isKo || forked) {
                // current track has its own segments/timing
                if (activeSeg) cc = displayText(activeSeg);
              } else {
                // non-forked translation: no lang segments exist, so drive the
                // overlay off the inherited Korean timing (koRefSegs) and show
                // this language's translation for the active Korean cue. Without
                // this the on-video preview was dead until the track was forked.
                const koSeg = koRefSegs.find(
                  (k) => currentTime >= k.start && currentTime < k.end,
                );
                if (koSeg) cc = transMap[koSeg.id] ?? "";
              }
              return cc ? (
                <div className="cc-overlay">
                  <span>{cc}</span>
                </div>
              ) : null;
            })()}
        </div>
        <div className="play-controls">
          <button
            className="pc-btn"
            title="지금 편집 중인 자막을 처음부터 다시 재생 (Ctrl+\)"
            onClick={replayCurrent}
          >
            ⏮ 구간처음
          </button>
          <button className="pc-btn" title="3초 뒤로 (Ctrl+← 또는 Shift+Tab)" onClick={() => seekBy(-3)}>
            ⟲ 3초
          </button>
          <button
            className="pc-btn play"
            title="재생 / 일시정지 (Tab, 또는 편집칸 밖에서 Space)"
            onClick={() => playPause()}
          >
            {playing ? "⏸ 멈춤" : "▶ 재생"}
          </button>
          <button className="pc-btn" title="3초 앞으로 (Ctrl+→)" onClick={() => seekBy(3)}>
            3초 ⟳
          </button>
          <div className="pc-settings">
            <label className="pc-toggle" title="편집 중인 구간의 소리를 반복 재생 (되감기 없이 다시 듣기) (Alt+R)">
              <input
                type="checkbox"
                checked={loopSeg}
                onChange={(e) => setLoopSeg(e.target.checked)}
              />
              🔁 구간반복
            </label>
            <label
              className="pc-toggle"
              title="구간을 클릭해 편집을 시작할 때 영상을 한 번 멈춤 (타이핑·백스페이스로는 안 멈춰서 재생·구간반복 들으며 편집 가능) (Alt+S)"
            >
              <input
                type="checkbox"
                checked={pauseOnType}
                onChange={(e) => setPauseOnType(e.target.checked)}
              />
              편집 시작 시 멈춤
            </label>
            <label
              className="pc-toggle"
              title="미리보기(극장) 모드 — 영상을 크게, 자막을 영상 위에 얹고, 재생 중인 자막을 화면 가운데로 따라 스크롤. 최종 확인용 (편집은 끄고) (Alt+P)"
            >
              <input
                type="checkbox"
                checked={showPreview}
                onChange={(e) => setShowPreview(e.target.checked)}
              />
              💬 미리보기 모드
            </label>
          </div>
        </div>
        <div className="orientation">
          <div className="orientation-line">
            <span>재생</span>
            <strong>{fmt(currentTime)}</strong>
            <em>
              #{segmentNo(segments, activeId)} {activeSeg ? `${fmt(activeSeg.start)} → ${fmt(activeSeg.end)}` : ""}
            </em>
          </div>
          <div className="orientation-line edit">
            <span>편집</span>
            <strong>#{focusedSeg ? segmentNo(segments, focusedSeg.id) : "-"}</strong>
            <em>{focusedSeg ? `${fmt(focusedSeg.start)} → ${fmt(focusedSeg.end)}` : ""}</em>
          </div>
        </div>
        <TimingStrip
          segments={segments}
          currentTime={currentTime}
          activeId={activeId}
          focusedId={focusedId}
          playing={playing}
          onSeek={seekTo}
          onBoundaryDrag={(segId, time, which) => {
            const seg = segmentsRef.current.find((s) => s.id === segId);
            // hybrid: free in a gap, pushes the neighbour once it crosses the
            // shared wall (pull a start earlier than the prev cue's end → that
            // end follows; drag an end past the next start → that start follows)
            if (seg) void edgeDragCommit(seg, which, time);
          }}
          onDragActive={(a) => {
            dragFreezeRef.current = a;
          }}
        />
        {/* subtle, non-interruptive status (autosave-style) */}
        <div className="statusbar" aria-live="polite">
          <span className={"save-dot" + (statusMsg ? " busy" : "")} />
          <span className="work-status">
            {statusMsg ||
              (undoStack.length
                ? `${undoStack[undoStack.length - 1].label} — 되돌릴 수 있음`
                : "자동 저장됨")}
          </span>
          <button
            className="undo-mini"
            disabled={!undoStack.length}
            title="되돌리기 (Ctrl+Z)"
            onClick={() => void undoLast()}
          >
            ↶
          </button>
        </div>

        {/* momentum hero — only when this track has segments to work on. A
            not-yet-forked translation has none here (its progress lives in the
            right-hand translation-review panel), so don't falsely say "done". */}
        {(isKo || forked) && (
          <div className={"flow-hero" + (celebrate ? " celebrate" : "")}>
            <div className="flow-progress">
              <div className="flow-nums">
                <strong>{nReviewed}</strong>
                <span>/ {segments.length}</span>
                <em>{reviewedPct}%</em>
              </div>
              <div className="flow-bar">
                <span style={{ width: `${reviewedPct}%` }} />
              </div>
              <div className="flow-remain">
                <span>{nRemaining ? `${nRemaining}개 남음` : "모두 확인 🎉"}</span>
                {eta && <em className="flow-eta">{eta}</em>}
              </div>
            </div>
            <button
              className="continue-btn"
              disabled={!nRemaining}
              onClick={() => void continueWork()}
            >
              <span>이어서 작업하기</span>
              <strong>{nRemaining ? "다음 →" : "완료"}</strong>
            </button>
          </div>
        )}

        {/* secondary tools — Korean-source only (whisper/YouTube based) */}
        {isKo && (
        <div className="tools">
          {nSafe > 0 && (
            <button
              className="tool accent"
              title="두 음성인식이 일치하고 어려운 용어도 없는 '안심' 구간을 한번에 확인. 나머지에만 집중하세요."
              onClick={() => void runConfirmSafe()}
            >
              ✅ 안심 {nSafe}개 확인
            </button>
          )}
          <button
            className="tool"
            title="자막을 실제 발화 시작~끝 구간에 딱 맞춰 다듬어 침묵 구간엔 자막이 안 보이게 함 (텍스트·검수 상태는 그대로, API 사용 안 함) (Alt+M)"
            onClick={() => void runTighten()}
          >
            ✂ 무음 다듬기
          </button>
          <button
            className="tool"
            title="음성인식이 놓치거나 잘못 뱉은 구간을 유튜브 자막으로 복구·보충 (API 사용 안 함) (Alt+G)"
            onClick={() => void runRepair()}
          >
            🛠 복구·채우기
          </button>
          <button
            className="tool"
            title="이번에 고친 내용을 뒤쪽 미검수 자막에 반영하고 다음 실행에도 기억 (Alt+K)"
            onClick={() => void runAbsorb()}
          >
            📚 학습
          </button>
        </div>
        )}

        {/* export footer */}
        <div className="export-footer">
          {(isKo || forked) && (
            <label
              className={"timing-done" + ((isKo ? timingDone : langTimingDone) ? " on" : "")}
              title="자막 시간(타이밍)까지 조정을 끝냈으면 체크 — 텍스트 검수와 별개로, 트랙(언어)별로 목록에 표시됩니다"
            >
              <input
                type="checkbox"
                checked={isKo ? timingDone : langTimingDone}
                onChange={() => void toggleTimingDone()}
              />
              ⏱ {isKo ? "" : langLabel + " "}타이밍 검수 완료
            </label>
          )}
          <div className="export-row">
            <span className="track-label" title="지금 편집하고 내보낼 언어 트랙">
              편집·내보낼 언어
            </span>
            <select
              value={lang}
              onChange={(e) => setLang(e.target.value)}
              title={koDone ? "편집·내보낼 언어 트랙 선택" : "한국어 검수를 마치면 번역 언어를 선택할 수 있어요"}
            >
              {langs.map((l) => {
                // a forked track is independent of Korean completeness — never
                // lock/mislabel it. Only inherited (non-forked) translations are
                // gated on ko being done.
                const locked = l.code !== "ko" && !koDone && !forkedLangs.has(l.code);
                return (
                  <option key={l.code} value={l.code} disabled={locked}>
                    {l.label}
                    {locked ? " (한국어 검수 후)" : ""}
                  </option>
                );
              })}
            </select>
            <button className="export" disabled={exporting} onClick={() => void runExport()}>
              {exporting
                ? lang === "ko"
                  ? "저장하는 중..."
                  : "번역하는 중... (처음엔 1~2분)"
                : "자막 받기 (.srt)"}
            </button>
          </div>
          <div className="hint">받으면 고친 내용이 뒤쪽 자막과 다음 실행에 자동 반영됩니다</div>
        </div>
        {absorbMsg && <div className="absorb-msg">{absorbMsg}</div>}
        {error && <div className="error">{error}</div>}

        <div className="keys">
          <button className="keys-toggle" onClick={() => setShowKeys(!showKeys)}>
            <span>단축키</span>
            <strong>{showKeys ? "접기" : "열기"}</strong>
          </button>
          {showKeys && (
            <div className="shortcut-groups">
              {SHORTCUT_GROUPS.map((group) => (
                <section className="shortcut-group" key={group.title}>
                  <h3>{group.title}</h3>
                  <div className="shortcut-list">
                    {group.items.map((item) => (
                      <div className="shortcut-item" key={`${group.title}-${item.keys.join("-")}-${item.label}`}>
                        <div className="shortcut-keys">
                          {item.keys.map((key) => (
                            <kbd key={key}>{key}</kbd>
                          ))}
                        </div>
                        <div className="shortcut-copy">
                          <strong>{item.label}</strong>
                          {item.detail && <span>{item.detail}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="right">
        {(isKo || forked) && (
          <div className={"findbar" + (findOpen ? " open" : "")}>
            {findOpen ? (
              <>
                <input
                  className="find-in"
                  placeholder="찾을 내용"
                  value={findText}
                  autoFocus
                  onChange={(e) => setFindText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && findMatches) void applyReplace();
                    if (e.key === "Escape") setFindOpen(false);
                  }}
                />
                <span className="find-arrow">→</span>
                <input
                  className="find-in"
                  placeholder="바꿀 내용 (비우면 삭제)"
                  value={replText}
                  onChange={(e) => setReplText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && findMatches) void applyReplace();
                    if (e.key === "Escape") setFindOpen(false);
                  }}
                />
                <span className="find-count">
                  {findText.trim() ? (findMatches === null ? "…" : `${findMatches}곳`) : ""}
                </span>
                <button
                  className="find-apply"
                  disabled={!findMatches}
                  onClick={() => void applyReplace()}
                >
                  모두 바꾸기
                </button>
                <button
                  className="find-close"
                  title="닫기 (Esc)"
                  onClick={() => {
                    setFindOpen(false);
                    setFindMatches(null);
                  }}
                >
                  ✕
                </button>
              </>
            ) : (
              <button
                className="find-toggle"
                title="반복되는 오인식을 전체 자막에서 한 번에 교정 (Alt+B)"
                onClick={() => setFindOpen(true)}
              >
                🔎 찾기·바꾸기
              </button>
            )}
          </div>
        )}
        {!isKo && !forked ? (
          <div className="track-review">
            {Object.keys(transMap).length > 0 && (
              <div className="track-fork">
                <button className="mini fork-btn" onClick={() => void runFork()}>
                  ✂ 이 언어를 따로 분할·타이밍 편집하기
                </button>
                <span className="fork-hint">
                  언어에 맞게 자막을 다르게 쪼개거나 타이밍을 바꿔야 할 때. 한국어 구조를 복사해
                  독립 트랙으로 만듭니다. 나중에 <b>독립 편집 해제</b>로 되돌릴 수 있어요.
                </span>
              </div>
            )}
            <TranslateReview
              videoId={videoId}
              lang={lang}
              langLabel={langLabel}
              currentTime={currentTime}
              onSeek={seekTo}
              onGenerated={() => setTransRefresh((n) => n + 1)}
            />
          </div>
        ) : (
          <>
            {!isKo && forked && (
              <div className="track-fork forked-actions">
                <button
                  className="mini"
                  onClick={() => void runUnfork()}
                  title="한국어 구조를 따르는 번역 검수로 되돌립니다 (편집한 번역은 복원)"
                >
                  ↩ 독립 편집 해제
                </button>
                <span className="fork-hint">
                  {langLabel}을(를) 독립 트랙으로 편집 중 — 분할·타이밍을 한국어와 다르게 조정할 수 있어요.
                </span>
              </div>
            )}
            {segments.map((seg) => (
            <Row
              key={seg.id}
              seg={seg}
              active={seg.id === activeId}
              focused={seg.id === focusedId}
              preview={showPreview}
              currentTime={currentTime}
              hasNext={segments.some((s) => s.job_id === seg.job_id && s.idx === seg.idx + 1)}
              koRef={
                isKo
                  ? undefined
                  : koRefSegs
                      .filter((k) => k.start < seg.end && k.end > seg.start)
                      .map((k) => displayText(k))
                      .join(" ")
                      .trim() || undefined
              }
              words={isKo || forked ? words : []}
              register={(h) => {
                if (h) rowsRef.current.set(seg.id, h);
                else rowsRef.current.delete(seg.id);
              }}
              onSeek={seekTo}
              onSave={save}
              onTime={timeChange}
              onSetTimes={setTimes}
              onTiming={timing}
              onStructure={structure}
              onTyping={() => {
                if (pauseOnType && playing) pause();
              }}
              onFocusRow={markFocused}
              onOpenRow={focusSegment}
              onDragActive={(a) => {
                dragFreezeRef.current = a;
              }}
            />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
