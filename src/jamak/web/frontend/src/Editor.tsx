import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  absorbFeedback,
  autoTiming,
  boundaryNext,
  boundaryPrev,
  edgeDrag,
  confirmSafe,
  deleteSegment,
  exportUrl,
  fetchLanguages,
  fetchQc,
  fetchSegments,
  fetchTranslations,
  fetchWords,
  forkTrack,
  unforkTrack,
  mergeNext,
  practiceKey,
  practiceSession,
  repairStt,
  replaceText,
  restoreRows,
  runSpellcheck,
  setTimingDone,
  splitSegment,
  tightenTiming,
  updateSegment,
} from "./api";
import type { QcReport, SpellSuggestion, WordTime } from "./api";
import { Dropdown } from "./Dropdown";
import { ThemeToggle } from "./theme";
import { useConfirm } from "./confirm";
import { Tour, type TourStep } from "./Tour";
import {
  COURSE_PRESETS,
  TUTORIAL_CHECKPOINTS,
  TUTORIAL_DEFECT_WORDS,
  TUTORIAL_LINES,
} from "./tutorialSync";
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
  const markerRef = useRef<HTMLSpanElement>(null);
  const scrubRef = useRef(false); // dragging the playhead to seek (scrub)
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
    if (scrubRef.current) return seekPaint(e.clientX);
    if (dragRef.current) paint(e.clientX);
  }
  function endDrag(e: React.PointerEvent) {
    if (scrubRef.current) {
      seekPaint(e.clientX);
      scrubRef.current = false;
      winRef.current = null;
      setDragging(false);
      onDragActive?.(false);
      if (labelRef.current) labelRef.current.textContent = "";
      return;
    }
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

  // scrub the playhead to seek — drag the white marker (or click/drag the empty
  // track). The marker + time label move imperatively (poll frozen), and we seek
  // the video to that time, so the strip doubles as a video scrubber.
  function seekPaint(clientX: number) {
    const w = winRef.current;
    if (!w) return;
    const t = timeAtClientX(clientX);
    const pct = clamp(((t - w.start) / w.span) * 100, 0, 100);
    if (markerRef.current) markerRef.current.style.left = `${pct}%`;
    const lbl = labelRef.current;
    if (lbl) {
      lbl.style.left = `${pct}%`;
      lbl.textContent = fmt(t);
    }
    onSeek(t);
  }
  function startScrub(e: React.PointerEvent) {
    e.preventDefault();
    winRef.current = { start, span }; // freeze window so the marker doesn't recenter
    scrubRef.current = true;
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      /* capture unavailable — scrub still works */
    }
    onDragActive?.(true); // freeze poll (our imperative marker owns the position)
    setDragging(true);
    seekPaint(e.clientX);
  }

  return (
    <div className="timing-strip">
      {/* `smooth`: while the video plays the window scrolls to follow the
          playhead, but currentTime only ticks 4×/sec — a CSS transition
          interpolates each 250ms jump into continuous motion. OFF while dragging
          (the handle must track the pointer, not glide) or paused. */}
      <div
        className={"strip-track" + (playing && !dragging ? " smooth" : "")}
        ref={trackRef}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerDown={(e) => {
          // click/drag the empty track background to seek (scrub). Segments and
          // handles are children with their own handlers, so this only fires on
          // the bare track area.
          if (e.target === trackRef.current) startScrub(e);
        }}
      >
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
        <span
          ref={markerRef}
          className="strip-marker"
          style={{ left: `${marker}%` }}
          title="드래그해서 재생 위치 이동 (스크럽)"
          onPointerDown={startScrub}
        />
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
            className={"wm-word" + (currentTime >= w.start && currentTime < w.end ? " on" : "")}
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

/* [WH-CHANGE v0.3.1 | FEAT | 2026-07-13 | CHG-20260713-008]
   Reason: 벤치마킹(Descript/Otter/Auphonic) — 소리와 글자를 눈으로 잇는 카라오케
           하이라이트 + 단어 단위 재청취 + 의심 단어 인라인이 고령 검수자의
           눈 이동·판단 부담을 가장 크게 줄임.
   Related: ADR-0009 / CHANGELOG CHG-20260713-008.

   Read view for 내용 모드 (Descript/Otter pattern): unfocused rows show their
   text as word spans instead of a textarea. While the video plays over this
   cue the current word lights up (karaoke follow — proportional mapping from
   the whisper word timestamps onto the possibly-edited text), suspect words
   carry a wavy red underline inline (no separate warning line to cross-
   reference), and clicking any word replays from that word. Clicking empty
   space switches the row into the normal textarea for editing. */
function ReadText({
  seg,
  text,
  words,
  currentTime,
  onWordPlay,
  onEdit,
}: {
  seg: Segment;
  text: string;
  words: WordTime[];
  currentTime: number;
  onWordPlay: (t: number) => void;
  onEdit: () => void;
}) {
  const inside = useMemo(
    () =>
      words.filter((w) => {
        const m = (w.start + w.end) / 2;
        return seg.start <= m && m < seg.end;
      }),
    [words, seg.start, seg.end],
  );
  const tokens = useMemo(() => text.split(/(\s+)/), [text]);
  const suspectSet = useMemo(() => {
    const norm = (s: string) => s.replace(/[^\w가-힣]/g, "");
    return new Set(
      (seg.suspect ?? "")
        .split(",")
        .map((t) => norm(t.trim()))
        .filter((t) => t.length >= 2),
    );
  }, [seg.suspect]);

  const wordTokens = tokens.filter((t) => t.trim() !== "").length;
  const M = inside.length;
  // which text token the speaker is on right now (edited text no longer maps
  // 1:1 onto whisper words, so map proportionally — close enough to follow)
  let activeOrd = -1;
  if (M > 0 && wordTokens > 0 && currentTime >= seg.start && currentTime < seg.end) {
    let k = inside.findIndex((w) => currentTime < w.end);
    if (k < 0) k = M - 1;
    activeOrd =
      wordTokens > 1 ? Math.round((k / Math.max(1, M - 1)) * (wordTokens - 1)) : 0;
  }
  const timeFor = (ord: number) => {
    if (M > 0) {
      const k = Math.min(
        M - 1,
        Math.round((ord / Math.max(1, wordTokens - 1)) * (M - 1)),
      );
      return inside[k].start;
    }
    // no recognized speech here (e.g. a gap-fill row) — char-ratio fallback
    const span = Math.max(0, seg.end - seg.start - 0.2);
    return seg.start + (wordTokens > 1 ? (ord / (wordTokens - 1)) * span : 0);
  };

  let ord = -1;
  return (
    <div
      className="read-text"
      title="단어를 누르면 그 부분부터 다시 들려요 · 빈 곳을 누르면 고치기"
      onClick={onEdit}
    >
      {tokens.map((tok, i) => {
        if (tok.trim() === "") return tok;
        ord += 1;
        const o = ord;
        const norm = tok.replace(/[^\w가-힣]/g, "");
        const sus = norm.length >= 2 && suspectSet.has(norm);
        return (
          <span
            key={i}
            className={"rt-w" + (o === activeOrd ? " on" : "") + (sus ? " sus" : "")}
            title={sus ? "기계들이 서로 다르게 들은 단어 — 확인해 보세요" : undefined}
            onClick={(e) => {
              e.stopPropagation();
              onWordPlay(timeFor(o));
            }}
          >
            {tok}
          </span>
        );
      })}
      {text.trim() === "" && <span className="rt-empty">(빈 자막 — 눌러서 입력)</span>}
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

// ONE editor operation's undo step: put `upsert` rows back exactly as they
// were and delete the rows the operation created. Only those rows are touched
// on the server, so undoing never clobbers a concurrent reviewer's edits
// elsewhere in the track (the old whole-track snapshot restore did).
interface UndoEntry {
  label: string;
  kind: "text" | "op";
  segId: number | null; // text entries coalesce per editing session of one cell
  focusedId: number | null;
  upsert: Segment[];
  deleteIds: number[];
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
  textMode,
  currentTime,
  hasNext,
  koRef,
  words,
  onRegister,
  onSeek,
  onPlayFrom,
  onSave,
  onTime,
  onSetTimes,
  onTiming,
  onStructure,
  onTyping,
  onFocusRow,
  onOpenRow,
  onHold,
  onDragActive,
}: {
  seg: Segment;
  active: boolean;
  focused: boolean;
  preview: boolean;
  // 내용 검수 모드: hide every timing affordance so the reviewer only ever
  // decides "is this what was said?" (ADR-0009)
  textMode: boolean;
  currentTime: number;
  hasNext: boolean;
  koRef?: string;
  words: WordTime[];
  onDragActive?: (active: boolean) => void;
  onRegister: (id: number, h: RowHandle | null) => void;
  onSeek: (t: number) => void;
  onPlayFrom: (t: number) => void;
  onSave: (id: number, text: string, reviewed: boolean | null, next: boolean) => Promise<void>;
  onTime: (seg: Segment, field: "start" | "end", value: number) => void;
  onSetTimes: (seg: Segment, start: number, end: number) => void;
  onTiming: (action: "start-here" | "next-here", seg: Segment) => void;
  onStructure: (action: "split" | "merge" | "delete", seg: Segment, position?: number) => void;
  onTyping: () => void;
  onFocusRow: (id: number) => void;
  onOpenRow: (seg: Segment) => void;
  onHold: (seg: Segment) => void;
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
    onRegister(seg.id, handle);
    return () => {
      void flush();
      onRegister(seg.id, null);
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

  // 내용 모드: the textarea only exists while this row is focused (ReadText
  // otherwise), so grab the caret as soon as the swap renders — the parent's
  // setTimeout(0) focus can fire before the textarea is in the DOM
  useEffect(() => {
    if (focused && textMode) taRef.current?.focus({ preventScroll: true });
  }, [focused, textMode]);

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
      data-segid={seg.id}
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
        {/* seek AND play — with seek-only this button looked dead whenever the
            video was paused (it only moved the playhead) */}
        <button className="time" onClick={() => onPlayFrom(seg.start)} title="이 구간 재생">
          ▶
        </button>
        {textMode ? (
          // 내용 모드: the time is orientation only — nothing here is editable,
          // so there is nothing timing-related to worry about
          <span className="time-plain" title="자막 시간 (타이밍 검수에서 조정)">
            {fmt(seg.start)}
          </span>
        ) : (
          <>
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
          </>
        )}
        <span className="badges">
          {!textMode && text.trim() !== "" && (
            // 읽기 속도 신호등 (Ooona/EZTitles 관례): 숫자 대신 색 —
            // 초록=편안, 주황=한계선, 빨강=너무 빠름(고치기)
            <span
              className={
                "cps-dot " + (cps > 17 ? "red" : cps > 14 ? "amber" : "green")
              }
              title={`읽기 속도 ${cps.toFixed(0)}자/초 — ${
                cps > 17
                  ? "너무 빨라요: 나누거나 시간을 늘리세요"
                  : cps > 14
                    ? "한계선이에요"
                    : "편안해요"
              }`}
            />
          )}
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
          {tooFast && !seg.reviewed && !textMode && (
            <span
              className="badge fast"
              title={`읽기 속도 ${cps.toFixed(0)}자/초 — 너무 빠릅니다. '나누기'로 쪼개거나 끝시간을 늘려 17자/초 이하로 (시청자가 못 읽음)`}
            >
              ⏩ 빠름 {cps.toFixed(0)}
            </span>
          )}
          {seg.review_flag === "hold" && !seg.reviewed && (
            <span className="badge hold" title="잘 안 들려서 나중에 다시 듣기로 표시한 자막">
              🙉 나중에 다시
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
      {textMode && !focused ? (
        <ReadText
          seg={seg}
          text={text}
          words={words}
          currentTime={currentTime}
          onWordPlay={onPlayFrom}
          onEdit={() => onOpenRow(seg)}
        />
      ) : (
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
      )}
      {focused && !textMode && words.length > 0 && (
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
        {textMode && (focused || seg.review_flag === "hold") && (
          <button
            className={"hold-btn" + (seg.review_flag === "hold" ? " on" : "")}
            title="잘 안 들리면 눌러두세요 — 건너뛰고 나중에 다시 들을 수 있어요 (Alt+H)"
            onClick={() => onHold(seg)}
          >
            {seg.review_flag === "hold" ? "🙉 보류 해제" : "🙉 잘 안 들림"}
          </button>
        )}
        {textMode && focused && (
          // 모바일 전용 (CSS로 데스크톱에선 숨김): 키보드 단축키의 터치 대체.
          // 데스크톱 내용 모드는 ADR-0009대로 구조 도구를 숨긴 채 유지.
          <span className="structure structure-mobile">
            <button
              title="텍스트 커서 위치에서 자막을 둘로 나누기"
              onClick={() => {
                void flush().then(() =>
                  onStructure("split", seg, taRef.current?.selectionStart ?? 0),
                );
              }}
            >
              ✂ 나누기
            </button>
            <button
              title="아래 자막과 합치기"
              onClick={() => {
                void flush().then(() => onStructure("merge", seg));
              }}
            >
              ⇣ 합치기
            </button>
            <button
              className="danger"
              title="이 자막을 지움 (되돌리기 가능)"
              onClick={() => {
                void flush().then(() => onStructure("delete", seg));
              }}
            >
              ✕
            </button>
          </span>
        )}
        {focused && !textMode && (
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
            title="이 자막을 바로 지움 (Alt+Z로 복구)"
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

// Memoized: with hundreds of rows, re-rendering the whole list per keystroke /
// player tick is what made editing feel choppy. Handlers passed in are stable
// (ref-trampolined) and `currentTime` is only fed to the active/focused row, so
// during playback exactly one row re-renders per tick.
const MemoRow = memo(Row);

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
        label: "방금 작업 하나 되돌리기",
        detail: "글 수정·나누기·합치기·삭제·시간 — 한 번에 하나씩, 편집 중에도",
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
      { keys: ["Enter"], label: "(내용 모드, 입력칸 밖) 지금 나온 자막 확인", detail: "재생 안 멈춤 — 흘려들으며 확인" },
      { keys: ["Alt+H"], label: "잘 안 들림 — 나중에 다시", detail: "건너뛰고 이어서, 나중에 느리게 다시 듣기" },
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

/* [WH-CHANGE v0.4.0 | FEAT | 2026-07-14 | CHG-20260714-002]
   Reason: 어르신 검수자 온보딩 — 기능 전부를 코스별로 하나씩 직접 해보며 익히는
           따라하기 레슨(6개 코스). 각 단계는 실제 그 동작이 일어나야 진행
           (동작 지점마다 tourEvent(이름) 훅). 연습용(🎓) 영상에서 마음껏 연습.
   Related: ADR-0009 / CHANGELOG CHG-20260714-002.

   TourStep.on = 이 단계를 통과시키는 실제 동작 이벤트 이름. */
interface TourCourse {
  id: string; // localStorage 완료 키
  icon: string;
  title: string;
  desc: string;
  steps: TourStep[];
}

const K = ({ c }: { c: string }) => <kbd className="g-key">{c}</kbd>;

const COURSES: TourCourse[] = [
  {
    id: "basic",
    icon: "1️⃣",
    title: "기본기 — 듣고, 확인하고, 고치기",
    desc: "재생 · Enter 확인 · 글 고치기 · 🙉 · 되돌리기",
    steps: [
      {
        target: ".pc-btn.play",
        title: "영상을 틀어볼게요",
        body: <>여기 밝게 보이는 <b>▶ 재생</b> 버튼을 <b>직접 눌러보세요</b>.</>,
        on: "play",
      },
      {
        // v2 흐름 확인: 영상이 멈춘 동안, 지금까지 나온 자막을 전부 확인해야
        // 다음으로 — 말풍선이 다음 미확인 자막을 따라 내려간다 (untilTime)
        target: ".row:not(.collapsed)",
        title: "위에서부터 차례로 Enter",
        body: (
          <>
            말과 자막이 맞으면 <K c="Enter" /> — 확인 ✓ 되고 다음 자막으로 내려가요.
            <b> 방금 나온 자막을 모두 확인하면</b> 영상이 이어져요.
          </>
        ),
        missingHint: "확인 안 된 자막이 남아 있어야 진행돼요.",
        on: "confirm",
        untilTime: true,
        loopRow: true,
      },
      {
        target: ".row:not(.collapsed) .read-text",
        targetDefect: true,
        title: "여기, 글자가 달라요",
        body: (
          <>
            이 자막에 <b>틀린 글자</b>가 심어져 있어요. 실제 들린 말과 비교해 보세요.
            <b> 자막 글을 한 번 누르면</b> 고칠 수 있는 칸이 열려요.
          </>
        ),
        missingHint: "확인 안 된 자막이 남아 있으면 여기 글이 보여요.",
        on: "open-row",
        loopRow: true,
      },
      {
        target: ".row.focused",
        targetDefect: true,
        title: "들린 대로 고치고 Enter",
        body: (
          <>
            소리를 반복해서 들려드리고 있어요. 틀린 낱말을 <b>실제 들린 말로 고친
            다음</b> <K c="Enter" /> — 확인되고 영상이 이어져요. (다른 자막에도
            틀린 글자가 몇 개 더 숨어 있어요)
          </>
        ),
        missingHint: "자막 글을 눌러 고치기 칸을 먼저 여세요.",
        on: "confirm",
        loopRow: true,
      },
      {
        target: ".hold-btn",
        subject: [113.2, 118.4],
        loopRow: true,
        title: "잘 안 들리면 🙉",
        body: (
          <>
            방금 웅얼거린 자막처럼 못 정하겠으면 <b>그 자막 글을 누르고 🙉 잘 안
            들림</b>을 눌러보세요. 건너뛰고 나중에 <b>느리게</b> 다시 들려드려요.
          </>
        ),
        missingHint: "자막 글을 누르면 그 자막 아래에 🙉 버튼이 나와요.",
        on: "hold",
      },
      {
        target: ".undo-mini",
        title: "실수해도 괜찮아요 — 되돌리기",
        body: (
          <>
            방금 🙉 표시를 되돌려 볼게요. <K c="Alt" />+<K c="Z" /> 를 누르거나 여기{" "}
            <b>↶</b> 버튼. 무엇을 하든 이걸로 되돌아가요.
          </>
        ),
        on: "undo",
      },
      {
        target: ".bigtype-btn",
        title: "글씨가 작으면 크게",
        body: (
          <>
            여기 <b>글씨 크게</b> 버튼을 눌러보세요. 자막과 버튼이 커져요. (한 번 더
            누르면 보통으로)
          </>
        ),
        on: "bigtype",
      },
      {
        target: null,
        final: true,
        title: "🎉 기본기 끝!",
        body: (
          <>
            <b>듣고 → 맞으면 Enter → 틀리면 눌러 고치고 Enter.</b> 이거면 끝까지 가요.
            목록의 <b>🎓 튜토리얼 연습</b> 탭에 다른 연습(재생 조작, 나누기, 타이밍…)도 있어요.
          </>
        ),
      },
    ],
  },
  {
    id: "playback",
    icon: "2️⃣",
    title: "재생 다루기 — 키보드로 자유롭게",
    desc: "Tab · 3초/10초 이동 · 구간 처음 · 느리게 · 반복",
    steps: [
      {
        target: ".pc-btn.play",
        title: "Tab = 재생/멈춤",
        body: (
          <>
            키보드 <K c="Tab" />을 눌러보세요. 재생↔멈춤이 번갈아요. (글자 쓰는 중에도
            돼요 — 스페이스는 글자 입력용이라 안 써요.)
          </>
        ),
        on: "play",
      },
      {
        target: ".play-controls",
        title: "방금 말을 놓쳤다? 3초 뒤로",
        body: (
          <>
            <K c="Shift" />+<K c="Tab" /> 또는 <K c="Ctrl" />+<K c="←" /> 를 눌러보세요.
            3초 뒤로 갑니다.
            <br />
            💡 자막 글 상자 안에 <b>깜빡이는 줄(커서)</b>이 있으면 화살표 키는
            글자 사이를 움직여요. 그럴 땐 <b>바깥 빈 곳을 한 번 누른 다음</b>{" "}
            <K c="Ctrl" />+<K c="←" />를 누르세요.
          </>
        ),
        on: "seek-back",
      },
      {
        // 나레이션 순서와 일치 (체크포인트 동기화): 배속은 "그래도 빠르면
        // 느리게" 대사 직후 — 3초 뒤로 다음, 건너뛰기 전
        target: ".pc-speed",
        title: "빠른 말은 천천히",
        body: <>여기서 <b>0.75×</b>를 눌러보세요. 말이 빠른 구간은 느리게 들어요.</>,
        on: "rate",
      },
      {
        target: ".play-controls",
        title: "3초 앞으로",
        body: (
          <>
            <K c="Ctrl" />+<K c="→" /> — 3초 앞으로. 조용한 구간은 이걸로 훌쩍.
          </>
        ),
        on: "seek-fwd",
      },
      {
        target: ".play-controls",
        title: "10초씩 크게 이동",
        body: (
          <>
            <K c="Ctrl" />+<K c="Shift" />+<K c="←" /> 또는 <K c="→" /> — 10초씩 성큼.
          </>
        ),
        on: "seek-10",
      },
      {
        target: ".pc-btn",
        title: "이 자막 처음부터 다시",
        body: (
          <>
            한 번 더 듣고 싶으면 <K c="Ctrl" />+<K c="\\" /> (또는 ⏮ 구간처음). 지금
            자막의 처음으로 돌아가 재생해요.
          </>
        ),
        on: "replay",
      },
      {
        target: ".pc-toggle-loop",
        title: "구간 반복",
        body: (
          <>
            <b>🔁 구간반복</b>을 켜보세요(<K c="Alt" />+<K c="R" />). 편집 중인 자막
            구간을 계속 반복해서 들려줘요 — 손 안 대고 여러 번 듣기.
          </>
        ),
        on: "loop",
      },
      {
        target: ".row:not(.collapsed)",
        title: "자막 사이 이동",
        body: (
          <>
            <K c="Alt" />+<K c="↑" /> / <K c="↓" /> — 이전/다음 자막으로 바로 가요.
            눌러보세요.
          </>
        ),
        on: "nav",
      },
      {
        target: null,
        final: true,
        title: "🎉 재생 조작 끝!",
        body: (
          <>
            정리: <K c="Tab" /> 재생/멈춤 · <K c="Ctrl" />+<K c="←→" /> 3초 ·{" "}
            <K c="Ctrl" />+<K c="\\" /> 구간 처음 · 0.75× 느리게 · 🔁 반복. 손이
            키보드에서 안 떠나면 두 배 빨라져요.
          </>
        ),
      },
    ],
  },
  {
    id: "fast",
    icon: "3️⃣",
    title: "빠르게 훑기 — 멈추지 않는 검수",
    desc: "멈춤 끄기 · 따라가기 조절 · 안심 일괄확인 · 찾기·바꾸기",
    // 나레이션 순서와 일치 (체크포인트 동기화): 안심 확인 → 찾기·바꾸기 →
    // 멈춤 끄기 → 따라가기 → 미확인 이동
    steps: [
      {
        target: ".tool-safe",
        title: "쉬운 자막은 한꺼번에 — 안심 확인",
        body: (
          <>
            기계 둘이 똑같이 들은 쉬운 자막은 <b>✅ 안심 확인</b>으로 한 번에 넘기고,
            어려운 것만 보세요. 눌러보세요.
          </>
        ),
        missingHint: "이 영상엔 지금 안심 구간이 없어요 — '건너뛰기'를 누르세요.",
        on: "confirm-safe",
      },
      {
        target: ".findbar",
        title: "같은 오타가 반복되면 — 찾기·바꾸기",
        body: (
          <>
            <b>🔎 찾기·바꾸기</b>를 열어보세요(<K c="Alt" />+<K c="B" />). 같은 잘못이
            100번 나와도 한 번에 다 바꿔요.
          </>
        ),
        on: "find",
      },
      {
        target: ".pc-toggle-pause",
        title: "'편집 시작 시 멈춤' 끄기",
        body: (
          <>
            이 체크를 <b>꺼보세요</b>(<K c="Alt" />+<K c="S" />). 끄면 자막 칸을 눌러도
            영상이 계속 흘러요 — <b>들으면서 바로바로</b> 고칠 때 좋아요. 차분히 볼 땐
            다시 켜세요.
          </>
        ),
        on: "pausetype",
      },
      {
        target: ".pc-toggle-follow",
        title: "'자동 따라가기'는 언제 끄나",
        body: (
          <>
            한 번 <b>껐다 켜보세요</b>. <b>켜기</b>: 쭉 들으며 확인할 때(화면이 알아서
            따라옴). <b>끄기</b>: 한 자막을 붙잡고 오래 고칠 때(화면이 안 움직여서 편함).
          </>
        ),
        on: "follow",
      },
      {
        target: ".flow-hero",
        title: "확인 안 한 자막만 골라 다니기",
        body: (
          <>
            <K c="Alt" />+<K c="Shift" />+<K c="↓" /> — 확인한 자막은 건너뛰고 다음{" "}
            <b>미확인 자막</b>으로 가요. <b>이어서 작업하기</b> 버튼도 같은 일을 해요.
            둘 중 하나를 해보세요.
          </>
        ),
        on: "nav-unreviewed",
      },
      {
        target: null,
        final: true,
        title: "🎉 훑기 요령 끝!",
        body: (
          <>
            요령: 완벽하게 하려고 멈추지 말고, 애매하면 🙉으로 넘기고 계속 가세요.
            쉬운 건 ✅ 안심으로 한꺼번에, 반복 오타는 🔎로 한 번에.
          </>
        ),
      },
    ],
  },
  {
    id: "structure",
    icon: "4️⃣",
    title: "나누기·합치기 — 자막 모양 다듬기",
    desc: "Ctrl+Enter 나누기 · Ctrl+Shift+Enter 합치기 · 복구",
    steps: [
      {
        target: ".row:not(.collapsed) .read-text",
        subject: [16.5, 32.8],
        loopRow: true,
        title: "먼저 자막 글을 누르세요",
        body: <>연습할 <b>긴 자막 글을 한 번 눌러</b> 고치기 칸을 여세요.</>,
        missingHint: "확인 안 된 자막이 남아 있으면 여기 글이 보여요.",
        on: "open-row",
      },
      {
        target: ".row.focused",
        subject: [16.5, 32.8],
        loopRow: true,
        title: "자막이 너무 길면 — 나누기",
        body: (
          <>
            나누고 싶은 곳에 <b>커서를 두고</b> <K c="Ctrl" />+<K c="Enter" />. 그
            자리에서 자막이 둘로 나뉘어요. 해보세요.
          </>
        ),
        missingHint: "자막 글을 눌러 고치기 칸이 열려 있어야 해요.",
        on: "split",
      },
      // 나레이션 순서와 일치 (체크포인트 동기화): 나누기 → 합치기 → 되돌리기 2번
      {
        target: ".row.focused",
        subject: [46.6, 59.1],
        loopRow: true,
        title: "너무 잘게 나뉘었으면 — 합치기",
        body: (
          <>
            토막 난 자막 글을 누른 뒤 <K c="Ctrl" />+<K c="Shift" />+<K c="Enter" /> —
            아래 자막과 합쳐져요. 해보세요.
          </>
        ),
        missingHint: "자막 글을 눌러 고치기 칸을 먼저 여세요.",
        on: "merge",
      },
      {
        target: ".undo-mini",
        title: "연습이니까 되돌려요",
        body: (
          <>
            <K c="Alt" />+<K c="Z" /> (또는 ↶) — 방금 합친 게 도로 나뉘어요.
          </>
        ),
        on: "undo",
      },
      {
        target: ".undo-mini",
        title: "한 번 더 — 나눈 것도 복구",
        body: (
          <>
            <K c="Alt" />+<K c="Z" /> 한 번 더 — 아까 나눈 것도 도로 붙어요. 무엇을
            하든 이걸로 되돌아가요.
          </>
        ),
        on: "undo",
      },
      {
        target: null,
        final: true,
        title: "🎉 모양 다듬기 끝!",
        body: (
          <>
            나누기 <K c="Ctrl" />+<K c="Enter" /> · 합치기 <K c="Ctrl" />+<K c="Shift" />+
            <K c="Enter" /> · 지우기 <K c="Alt" />+<K c="Delete" /> (전부 <K c="Alt" />+
            <K c="Z" />로 복구). 박수 소리만 있는 자막은 지워도 돼요.
          </>
        ),
      },
    ],
  },
  {
    id: "timing",
    icon: "5️⃣",
    title: "타이밍 — 자막이 뜨는 시간 맞추기",
    desc: "② 탭 · ✨ 자동 정리 · Alt+[ ] \\ · 타임라인 · 무음 다듬기",
    steps: [
      {
        target: ".mode-tabs",
        title: "② 타이밍 탭으로",
        body: (
          <>
            내용(글자) 검수가 끝나면 시간을 봐요. 위의 <b>② 타이밍</b> 탭을 눌러보세요.
          </>
        ),
        on: "mode-timing",
      },
      {
        target: ".tool-auto",
        title: "기계가 먼저 — ✨ 자동 정리",
        body: (
          <>
            <b>✨ 타이밍 자동 정리</b>를 눌러보세요. 말소리에 맞추고, 긴 자막은 나누고,
            빠른 자막은 시간을 늘려줘요. (<K c="Alt" />+<K c="Z" />로 전체 되돌리기 가능)
          </>
        ),
        on: "auto-timing",
      },
      {
        target: ".issue-bar",
        title: "남은 문제만 골라 보기",
        body: <><b>다음 문제 →</b>를 눌러보세요. 손볼 자막으로 바로 데려다줘요.</>,
        missingHint: "문제 자막이 없네요 — '건너뛰기'를 누르세요.",
        on: "next-issue",
      },
      {
        target: ".timing-tools",
        subject: [51.4, 57.6],
        loopRow: true,
        title: "여기서 시작 — Alt+[",
        body: (
          <>
            이 자막 소리를 반복해서 들려드려요. <b>말이 시작되는 순간</b>{" "}
            <K c="Alt" />+<K c="[" /> — 지금 재생 위치가 자막의 시작이 돼요.
          </>
        ),
        missingHint: "자막 글을 누르면 아래에 시간 도구가 나와요.",
        on: "start-here",
      },
      {
        target: ".timing-tools",
        subject: [51.4, 57.6],
        loopRow: true,
        title: "여기서 넘김 — Alt+]",
        body: (
          <>
            말이 끝나는 순간 <K c="Alt" />+<K c="]" /> — 여기서 자막을 끝내고 다음으로
            넘겨요.
          </>
        ),
        missingHint: "자막 글을 누르면 아래에 시간 도구가 나와요.",
        on: "next-here",
      },
      {
        target: ".timing-tools",
        subject: [51.4, 57.6],
        loopRow: true,
        title: "발화 맞춤 — Alt+\\",
        body: (
          <>
            <K c="Alt" />+<K c="\\" /> (또는 ⤢ 발화 맞춤) — 이 자막을 실제 말소리
            시작~끝에 자동으로 딱 맞춰요. 제일 편한 버튼이에요.
          </>
        ),
        missingHint: "자막 글을 누르면 아래에 시간 도구가 나와요.",
        on: "set-times",
      },
      // 나레이션 순서와 일치 (체크포인트 동기화): 무음 다듬기 → 타임라인 끌기
      {
        target: ".tool-tighten",
        title: "무음 다듬기",
        body: (
          <>
            <b>✂ 무음 다듬기</b>(<K c="Alt" />+<K c="M" />) — 조용한 구간에 자막이
            안 남게 전체를 한 번에 다듬어요. 눌러보세요.
          </>
        ),
        on: "tighten",
      },
      {
        target: ".timing-strip",
        title: "타임라인 손잡이 끌기",
        body: (
          <>
            여기 타임라인의 <b>밝은 손잡이를 좌우로 끌어보세요</b> — 자막의 시작/끝이
            따라 움직여요. 미세조정은 이걸로.
          </>
        ),
        on: "edge-drag",
      },
      {
        target: null,
        final: true,
        title: "🎉 타이밍 끝!",
        body: (
          <>
            순서: ✨ 자동 정리 → 문제만 순회 → <K c="Alt" />+<K c="[" />/<K c="]" />/
            <K c="\\" />로 손보기. 다 되면 아래 <b>⏱ 타이밍 검수 완료</b>에 체크하세요.
          </>
        ),
      },
    ],
  },
  {
    id: "finish",
    icon: "6️⃣",
    title: "마무리 도구 — 미리보기·복구·학습·내보내기",
    desc: "Alt+P 미리보기 · 복구·채우기 · 학습 · 자막 받기(점검표)",
    steps: [
      {
        target: ".pc-toggle-preview",
        title: "영화 보듯 최종 확인 — 미리보기",
        body: (
          <>
            <b>💬 미리보기 모드</b>를 켜보세요(<K c="Alt" />+<K c="P" />). 영상이
            커지고 자막이 영상 위에 얹혀요 — 시청자가 보게 될 모습 그대로. 확인 후
            다시 끄세요.
          </>
        ),
        on: "preview",
      },
      {
        target: ".tool-repair",
        title: "🛠 복구·채우기",
        body: (
          <>
            음성인식이 놓친 구간을 유튜브 자막으로 채워줘요. 눌러보세요. (관리자
            전용이라 안 되면 '건너뛰기')
          </>
        ),
        missingHint: "내용 모드에서 보여요 — ① 내용 확인 탭으로 가보세요.",
        on: "repair",
      },
      {
        target: ".tool-absorb",
        title: "📚 학습 — 기계가 배워요",
        body: (
          <>
            <b>📚 학습</b>(<K c="Alt" />+<K c="K" />)을 눌러보세요. 여러분이 고친 걸
            기계가 외워서, 다음 영상부터는 같은 실수를 덜 해요. 검수를 마칠 때마다
            눌러주면 좋아요. (연습용 영상에서는 "0개"라고 떠요 — 연습이라 진짜로
            배우지는 않는 게 정상이에요.)
          </>
        ),
        missingHint: "내용 모드에서 보여요 — ① 내용 확인 탭으로 가보세요.",
        on: "absorb",
      },
      {
        target: ".export-footer .export",
        title: "자막 받기 — 점검표가 먼저 떠요",
        body: (
          <>
            <b>자막 받기 (.srt)</b>를 눌러보세요. 빠진 곳·문제를 먼저 알려주는 점검표가
            떠요. 그냥 닫아도 돼요 — 진짜 받는 건 다 끝났을 때.
          </>
        ),
        on: "export-check",
      },
      {
        target: null,
        final: true,
        title: "🎉 전부 다 배우셨어요!",
        body: (
          <>
            점검표에서 <b>보기→</b>로 문제 자막에 바로 갈 수 있고, <b>✏️ 맞춤법
            검사</b>로 오타도 잡아줘요. 이제 진짜 영상에서 시작하세요 — 막히면 언제든{" "}
            <b>🎓 튜토리얼 연습</b> 탭에서 다시 연습할 수 있어요.
          </>
        ),
      },
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
  practice = false,
  tutorials = {},
  pendingCourse = null,
  onConsumePendingCourse,
  onOpenCourseVideo,
}: {
  videoId: string;
  onBack: () => void;
  koComplete: boolean;
  timingDone: boolean;
  initialLang?: string;
  languages?: { code: string; forked: boolean; timing_done: boolean }[];
  practice?: boolean;
  /** course id -> 전용 연습 영상(기준 Job)의 video_id */
  tutorials?: Record<string, string>;
  /** one-shot: 이 영상이 열리면 이 코스를 자동 시작 (App이 전환 시 세팅) */
  pendingCourse?: { course: string; nonce: number } | null;
  onConsumePendingCourse?: () => void;
  /** 코스 메뉴에서 전용 연습 영상으로 건너가기 (App이 클론 부트스트랩) */
  onOpenCourseVideo?: (courseId: string) => void;
}) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [timingDone, setTimingDoneState] = useState(initialTimingDone);
  // per-forked-track timing-done (ko uses `timingDone`); synced from the job's
  // languages when the active forked track changes
  const [langTimingDone, setLangTimingDone] = useState(false);
  const forkedLangs = new Set(languages.filter((l) => l.forked).map((l) => l.code));
  const [koDoneSeen, setKoDoneSeen] = useState(koComplete);
  const [error, setError] = useState("");
  // 도구 줄 피드백: 어떤 도구가 돌고 있는지(버튼 스피너·전체 비활성) +
  // 결과 배너(도구 줄 바로 아래, 눈에 띄게) — "눌렀는데 변화가 안 보임" 금지
  const [toolBusy, setToolBusy] = useState<string | null>(null);
  const [toolMsg, setToolMsg] = useState("");
  useEffect(() => {
    if (!toolMsg) return;
    const t = window.setTimeout(() => setToolMsg(""), 8000);
    return () => window.clearTimeout(t);
  }, [toolMsg]);
  const [langs, setLangs] = useState<{ code: string; label: string }[]>([]);
  const [lang, setLang] = useState(initialLang);
  const [exporting, setExporting] = useState(false);
  const [pauseOnType, setPauseOnType] = useState(true);
  const [loopSeg, setLoopSeg] = useState(false);
  // preview (theater) mode: big video + on-video caption + follow-along scroll.
  // off by default — editing is the primary task; turn on for the final watch.
  const [showPreview, setShowPreview] = useState(false);
  // [WH-CHANGE v0.3.0 | FEAT | 2026-07-13 | CHG-20260713-007]
  // Reason: 텍스트 검수 중 타이밍 UI가 "지금 고쳐야 하나?" 불안을 만듦 — 고령
  //         검수자 기준으로 화면을 단계별로 단순화 (내용/타이밍 모드 + 잘 안
  //         들림 보류 + 흘려듣기).
  // Related: ADR-0009 / CHANGELOG CHG-20260713-007.
  // work mode: 내용 검수 hides every timing affordance; 타이밍 검수 is
  // the full editor. Default derives from where the video is in the flow, but
  // the tabs never lock — a reviewer can always switch.
  const [mode, setMode] = useState<"text" | "timing">(koComplete ? "timing" : "text");
  // 흘려듣기: video keeps playing, the active cue follows centered, Enter (outside
  // a text box) confirms it — passive listening for long lectures
  const [follow, setFollow] = useState(() => localStorage.getItem("jamak.follow") !== "0");
  // 연습 코스 프리셋이 강제한 값이 실제 작업의 저장된 선호를 덮어쓰지 않게,
  // 연습 영상에서는 저장하지 않는다
  useEffect(() => {
    if (!practice) localStorage.setItem("jamak.follow", follow ? "1" : "0");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [follow]);
  // 큰 글씨 (고령 검수자): 자막 글자·주요 버튼 확대. 세션 간 유지.
  // 글씨 크기 3단계 (보통/크게/최대) — 구 bigtype("1")은 1단계로 승계
  const [fontScale, setFontScale] = useState(() => {
    const v = localStorage.getItem("jamak.fontscale");
    if (v !== null) return Math.min(2, Math.max(0, Number(v) || 0));
    return localStorage.getItem("jamak.bigtype") === "1" ? 1 : 0;
  });
  useEffect(() => localStorage.setItem("jamak.fontscale", String(fontScale)), [fontScale]);
  const bigType = fontScale >= 1; // 기존 .bigtype CSS 재사용
  // 따라하기 레슨: {course, step} = active lesson, null = off. 🎓 → 코스 메뉴.
  // Each step passes only when its real action fires (tourEvent at action sites).
  const [tour, setTour] = useState<{ course: number; step: number } | null>(null);
  const [tourMenu, setTourMenu] = useState(false);
  const tourRef = useRef<typeof tour>(null);
  tourRef.current = tour;
  // [WH-CHANGE v0.9.0 | FEAT | 2026-07-15 | CHG-20260715-031]
  // Reason: 연습 영상(나레이션)과 투어(말풍선)가 서로 모르는 두 타임라인이라
  //   지시가 엇갈리고, 영상이 계속 흘러 하이라이트가 대상을 지나치면 누를 곳이
  //   사라졌음 (사용자: 어르신용으로 최악). 체크포인트 동기화(옵션 B, 사용자
  //   확정): 나레이션이 "직접 해보세요"를 마치는 시각에 영상을 자동 일시정지
  //   하고 그때만 말풍선을 띄운다. 수행하면 자동 재개 — 선생은 영상 하나,
  //   앱은 멈추고 확인하는 조교.
  // Related: ACTIVE_PLAN 2026-07-15 / tutorialSync.ts / CHG-20260715-031.
  const tourMaxTimeRef = useRef(0); // 코스 시작 후 최대 재생 시각 (되감기 방어)
  const tourPausedRef = useRef(false); // 체크포인트 때문에 우리가 멈춘 상태인가
  const tourFiredRef = useRef(-1); // 일시정지를 이미 실행한 단계 index
  const [tourGate, setTourGate] = useState(true); // 현재 단계 말풍선 표시 여부

  /** 이 단계의 체크포인트 시각(초). null = 동기화 없음(항상 표시). */
  function stepCheckpoint(t: { course: number; step: number }): number | null {
    if (!practice) return null; // 실제 영상 투어는 기존 동작 그대로
    const at = TUTORIAL_CHECKPOINTS[COURSES[t.course].id]?.[t.step];
    return typeof at === "number" ? at : null;
  }
  function tourGateOpen(t: { course: number; step: number }): boolean {
    const at = stepCheckpoint(t);
    return at === null || tourMaxTimeRef.current >= at;
  }
  /** loopRow 단계의 대상 행: untilTime = 체크포인트 전 첫 미확인 행,
   *  targetDefect = 오타 행, subject = 그 나레이션 구간과 겹치는 행. */
  function stepLoopSeg(
    t: { course: number; step: number },
  ): Segment | undefined {
    const step = COURSES[t.course].steps[t.step];
    const segs = segmentsRef.current;
    if (step?.untilTime) {
      const at = stepCheckpoint(t) ?? Infinity;
      return segs.find(
        (s) => s.start < at && !s.reviewed && s.review_flag !== "hold",
      );
    }
    if (step?.targetDefect)
      return segs.find(
        (s) =>
          !s.reviewed &&
          TUTORIAL_DEFECT_WORDS.some((w) =>
            (s.text_final || s.text_llm || s.text_whisper || "").includes(w),
          ),
      );
    if (step?.subject) {
      const [a, b] = step.subject;
      return segs.find((s) => s.start < b && s.end > a && !s.reviewed) ??
        segs.find((s) => s.start < b && s.end > a);
    }
    return undefined;
  }
  /** 단계 활성화(체크포인트 도달 또는 연쇄 진입): loopRow 단계는 대상 행을
   *  구간반복으로 들려주고(자막↔말 비교가 과제이므로 정지 대신), 그 외는
   *  일시정지. (사용자 피드백 2026-07-15: "멈춰 있으면 맞는지 어떻게 확인해") */
  const tourLoopRef = useRef(false);
  function tourEnterStep(t: { course: number; step: number }) {
    const step = COURSES[t.course].steps[t.step];
    const at = stepCheckpoint(t);
    if (!step || step.final) return;
    if (step.loopRow) {
      // 한 번만 들려주고 행 끝에서 정지 (반복은 귀 피로 — 3차 파일럿).
      // 다시 듣기는 행 왼쪽 ▶ (말풍선이 안내). 행이 바뀌면 새 행을 또 한 번.
      const seg = stepLoopSeg(t);
      tourLoopRef.current = true;
      tourPausedRef.current = false;
      if (step.targetDefect) setPauseOnType(true); // 고치는 동안 영상 정지
      if (seg) {
        focusSegment(seg);
        seekTo(seg.start);
      }
      play();
    } else if (at !== null && at > 0) {
      // 재생 조작·버튼 단계: 글 상자에 커서가 남아 있으면 Ctrl+화살표 같은
      // 키가 글자 이동으로 먹혀버린다 — 편집 단계가 아니니 포커스를 풀어
      // 배우는 키가 바로 듣게 한다 (4차 파일럿)
      const ae = document.activeElement as HTMLElement | null;
      if (ae && (ae.tagName === "TEXTAREA" || ae.tagName === "INPUT")) ae.blur();
      tourPausedRef.current = true;
      pause();
    }
  }
  /** 단계 통과 직후: loop 정리 후, 다음 체크포인트가 앞이면 체크포인트 위치로
   *  되감아 나레이션을 이어가고(루프 중 재생 위치가 뒤로 흘렀으므로), 이미
   *  지났으면(연쇄 단계) 다음 단계를 바로 활성화한다. */
  function afterTourAdvance(next: { course: number; step: number } | null) {
    const wasLoop = tourLoopRef.current;
    if (wasLoop) tourLoopRef.current = false;
    if (next === null || next.step >= COURSES[next.course].steps.length) {
      tourPausedRef.current = false;
      return;
    }
    if (tourGateOpen(next)) {
      tourFiredRef.current = next.step;
      setTourGate(true);
      tourEnterStep(next); // 연쇄: 다음 단계의 loop/정지 상태로 전환
    } else {
      setTourGate(false);
      const doneAt = stepCheckpoint({ course: next.course, step: next.step - 1 });
      if (wasLoop && doneAt !== null) seekTo(doneAt); // 나레이션 이어가기
      tourPausedRef.current = false;
      play();
    }
  }
  /** an instrumented action happened — advance if it's what the step waits for */
  function tourEvent(name: string) {
    const t = tourRef.current;
    if (!t) return;
    const step = COURSES[t.course].steps[t.step];
    if (step?.on !== name) return;
    // 동기화 코스에선 영상이 시키기 전(말풍선 없음)의 행동은 세지 않는다 —
    // 단계가 소리 없이 넘어가면 나레이션과 다시 어긋난다
    if (!tourGateOpen(t)) return;
    // 흐름 확인 단계는 개별 confirm으로 넘어가지 않는다 — "체크포인트까지
    // 나온 자막 전부 확인" 판정 effect(tourRemain)가 진행을 소유
    if (step.untilTime) return;
    const next = { course: t.course, step: t.step + 1 };
    setTour(next);
    afterTourAdvance(next);
  }
  function courseDone(id: string): boolean {
    // legacy: jamak.tourDone was the old single-course flag → counts as basic
    return (
      localStorage.getItem(`jamak.tour.${id}`) === "1" ||
      (id === "basic" && localStorage.getItem("jamak.tourDone") === "1")
    );
  }
  // [WH-CHANGE v0.4.3 | FIX | 2026-07-14 | CHG-20260714-006]
  // Reason: "그만 볼래요" (mid-course exit) used to write the done flag too,
  //   so an aborted course showed ✓ in the menu and couldn't be told apart
  //   from a finished one. Exit now closes without marking done.
  // Related: docs/tutorial/PLAN.md Codex review (exit ≠ complete).
  function endTour(markDone: boolean) {
    const t = tourRef.current;
    if (markDone && t)
      localStorage.setItem(`jamak.tour.${COURSES[t.course].id}`, "1");
    tourPausedRef.current = false;
    if (tourLoopRef.current) {
      tourLoopRef.current = false;
      setLoopSeg(false);
    }
    setTour(null);
  }
  function startCourse(i: number) {
    setTourMenu(false);
    setMode("text"); // 모든 코스는 내용 모드에서 출발 (타이밍 코스는 탭 전환부터 가르침)
    // 코스 프리셋: 이전 저장값·디폴트가 연습 목표를 방해하지 않게 재생 설정을
    // 코스에 맞게 강제 (사용자 결정 2026-07-15 — 나레이션이 이 상태를 설명함)
    const preset = practice ? COURSE_PRESETS[COURSES[i].id] : undefined;
    if (preset) {
      setPauseOnType(preset.pauseOnType);
      setFollow(preset.follow);
      setLoopSeg(false);
      setShowPreview(false);
    }
    tourMaxTimeRef.current = 0;
    tourPausedRef.current = false;
    tourFiredRef.current = -1;
    setTour({ course: i, step: 0 });
    setTourGate(tourGateOpen({ course: i, step: 0 }));
  }
  // 흐름 확인 단계(untilTime): 체크포인트 시각보다 먼저 시작한 자막 중 아직
  // 확인도 보류도 안 된 것의 수 — 0이 되면 자동 진행, 말풍선에 남은 수 표시
  const tourRemain = useMemo(() => {
    if (!tour) return null;
    const step = COURSES[tour.course].steps[tour.step];
    if (!step?.untilTime) return null;
    const at = stepCheckpoint(tour) ?? Infinity;
    return segments.filter(
      (s) => s.start < at && !s.reviewed && s.review_flag !== "hold",
    ).length;
  }, [segments, tour]);
  useEffect(() => {
    const t = tourRef.current;
    if (t === null || tourRemain === null || tourRemain > 0) return;
    if (!tourGateOpen(t)) return;
    const next = { course: t.course, step: t.step + 1 };
    setTour(next);
    afterTourAdvance(next);
    // tourGate 포함: 체크포인트 전에 이미 다 확인해 둔 경우, 게이트가 열리는
    // 순간 진행돼야 한다 (remain은 이미 0이라 그것만으론 재발화 안 됨)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourRemain, tourGate]);
  /** 동적 대상 지목: 오타 행(targetDefect)·흐름 확인의 첫 미확인 행(untilTime) */
  function resolveTourTarget(): string | null | undefined {
    const t = tour;
    if (!t) return undefined;
    const step = COURSES[t.course].steps[t.step];
    // subject 단계도 대상 행에 앵커 — 아니면 selector가 화면 밖 "첫 행"에
    // 붙어 스포트라이트가 미아가 된다 (연습 4에서 실측)
    if (!step?.targetDefect && !step?.untilTime && !step?.subject)
      return undefined; // 기본 target
    const seg = stepLoopSeg(t);
    return seg ? `.row[data-segid="${seg.id}"]` : step.target;
  }
  /** 나레이션 원문에서 이 행이 담아야 할 문장(들)을 시간 보간으로 찾는다 —
   *  "지금 「…」 → 실제 말 「…」" 안내의 근거 (사용자 요구: 앱이 각 셀의 DB
   *  내용을 파악해 구체적으로 안내). */
  function expectedNarration(
    t: { course: number; step: number },
    seg: Segment,
  ): { text: string; boundary: boolean } | null {
    // 단어 단위 시간 보간: 셀이 실제로 담은 말만 정답으로 제시한다 — 문장
    // 전체를 정답이라 우기면 반 토막 셀에서 거짓 안내가 됨 (3차 파일럿).
    const lines = TUTORIAL_LINES[COURSES[t.course].id];
    if (!lines) return null;
    const words: { mid: number; w: string; sent: number }[] = [];
    let sent = 0;
    for (const ln of lines) {
      const dur = ln.end - ln.start;
      const total = ln.text.length;
      let off = 0;
      for (const w of ln.text.split(/\s+/)) {
        words.push({ mid: ln.start + ((off + w.length / 2) / total) * dur, w, sent });
        off += w.length + 1;
        if (/[.?!]$/.test(w)) sent++;
      }
      sent++;
    }
    // 1차: 단어 mid 시각이 든 행에 배정. 2차: 문장 다수결 스냅 — 문장 첫/끝
    // 단어가 경계 0.9초 이내로 옆 행에 걸린 경우(STT 꼬리 '이' 등) 그 문장의
    // 다수 단어가 있는 행으로 끌어온다. 셀 정답이 서로 모순되지 않게.
    const rows = segmentsRef.current
      .filter((r) => r.start < seg.start + 60) // 근처만 (성능)
      .sort((a, b) => a.start - b.start);
    const rowOf = (mid: number) => {
      let best: Segment | undefined;
      let bd = Infinity;
      for (const r of rows) {
        if (mid >= r.start && mid < r.end) return r.id;
        const d = mid < r.start ? r.start - mid : mid - r.end;
        if (d < bd) {
          bd = d;
          best = r;
        }
      }
      return best?.id ?? -1;
    };
    const assigned = words.map((x) => ({ ...x, row: rowOf(x.mid) }));
    const bySent = new Map<number, typeof assigned>();
    for (const x of assigned) {
      if (!bySent.has(x.sent)) bySent.set(x.sent, []);
      bySent.get(x.sent)!.push(x);
    }
    const nmw = (s: string) => s.replace(/[^\w가-힣]/g, "");
    for (const group of bySent.values()) {
      const count = new Map<number, number>();
      for (const x of group) count.set(x.row, (count.get(x.row) ?? 0) + 1);
      const major = [...count.entries()].sort((a, b) => b[1] - a[1])[0][0];
      const mr = rows.find((r) => r.id === major);
      if (!mr) continue;
      group.forEach((x, gi) => {
        if (x.row === major) return;
        const d = x.mid < mr.start ? mr.start - x.mid : x.mid - mr.end;
        if (d > 3) return;
        if (gi < group.length / 2) {
          // 문장 머리 낙오(꼬리 '이' 등) — 문장이 있는 셀로
          x.row = major;
          return;
        }
        // 문장 꼬리 낙오: STT가 실제로 그 셀에서 들었으면(텍스트에 존재) 진짜
        // 걸친 것(두었습니다) — 두고 정직 안내. 없으면 보간 오차 — 복귀.
        const r = rows.find((rr) => rr.id === x.row);
        const rt = r ? r.text_final || r.text_llm || r.text_whisper || "" : "";
        if (!nmw(rt).includes(nmw(x.w))) x.row = major;
      });
    }
    const inRow = assigned.filter((x) => x.row === seg.id);
    if (!inRow.length) return null;
    const mySents = new Set(inRow.map((x) => x.sent));
    const boundary = assigned.some(
      (x) => mySents.has(x.sent) && x.row !== seg.id,
    );
    return { text: inRow.map((x) => x.w).join(" "), boundary };
  }
  /** 흐름 확인 단계의 셀별 안내문: 맞으면 "Enter!", 다르면 지금↔실제 말 대조,
   *  문장이 옆 칸에 걸쳐 있으면 솔직하게 (나누기는 연습 4에서). */
  function tourNote(): React.ReactNode {
    const t = tour;
    if (!t || tourRemain === null || tourRemain <= 0) return undefined;
    const step = COURSES[t.course].steps[t.step];
    if (!step?.untilTime) return undefined;
    const seg = stepLoopSeg(t);
    if (!seg) return undefined;
    const cur = (seg.text_final || seg.text_llm || seg.text_whisper || "").trim();
    const exp = expectedNarration(t, seg);
    const nm = (x: string) => x.replace(/[^\w가-힣]/g, "");
    const meta = (
      <div className="tn-meta">
        남은 자막 {tourRemain}개 · 다시 들으려면 자막 왼쪽의 작은 ▶
      </div>
    );
    if (exp && nm(exp.text) !== nm(cur))
      return (
        <>
          <div className="tn-status fix">✏️ 글을 눌러 아래처럼 고친 뒤 Enter</div>
          <div className="tn-diff">
            <span className="tn-label">지금</span>
            <span className="tn-cur">{cur}</span>
          </div>
          <div className="tn-diff">
            <span className="tn-label">실제 말</span>
            <span className="tn-exp">{exp.text}</span>
          </div>
          {meta}
        </>
      );
    if (exp?.boundary)
      return (
        <>
          <div className="tn-status ok">✔ 말과 같아요 — Enter</div>
          <div className="tn-sub">
            문장이 옆 칸으로 이어지지만 <b>지금은 그대로</b> 두세요 · 칸 나누고
            붙이기는 <b>연습 4</b>에서
          </div>
          {meta}
        </>
      );
    return (
      <>
        <div className="tn-status ok">✔ 이 자막은 말과 같아요 — Enter</div>
        {meta}
      </>
    );
  }
  // 전용 연습 영상 딥링크: App이 영상 전환과 함께 넘긴 코스를, 세그먼트가
  // 로드된 뒤 자동 시작. nonce 기억으로 재실행 오발 방지 (일회성 소비).
  const consumedCourseRef = useRef(0);
  useEffect(() => {
    if (!pendingCourse || segments.length === 0) return;
    if (consumedCourseRef.current === pendingCourse.nonce) return;
    consumedCourseRef.current = pendingCourse.nonce;
    const i = COURSES.findIndex((c) => c.id === pendingCourse.course);
    if (i >= 0) startCourse(i);
    onConsumePendingCourse?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingCourse, segments.length]);
  // 모바일 재생 설정 시트: 데스크톱의 체크박스 2줄(구간반복 등)은 좁은 화면에서
  // 과밀 — 모바일 표준 문법(바텀 시트)으로 옮긴다. 상태는 동일한 것을 공유.
  const [mobileSettings, setMobileSettings] = useState(false);
  // 연습 초기화: 이 브라우저의 클론을 버리고 기준 상태로 재복제. 세그먼트
  // id 공간이 통째로 바뀌므로 늦게 도착하는 이전 저장 PUT은 자연히 무효
  // (지워진 id로 404) — baseline을 다시 오염시킬 수 없다.
  const [practiceResetting, setPracticeResetting] = useState(false);
  const [confirmNode, askConfirm] = useConfirm();
  async function practiceRestart() {
    if (
      !(await askConfirm({
        title: "↺ 처음부터 다시",
        body: "연습 내용을 지우고 처음 상태로 되돌릴까요?",
        ok: "처음부터 다시",
      }))
    )
      return;
    setPracticeResetting(true);
    try {
      await practiceSession(ytVideoId, practiceKey(), true);
      const next = await fetchSegments(videoId, langRef.current);
      segmentsRef.current = next;
      setSegments(next);
      setUndoStack([]);
      undoStackRef.current = [];
      setFocusedId(null);
      setStatusMsg("처음 상태로 되돌렸습니다 — 다시 연습해 보세요");
    } catch (e) {
      setError(String(e));
    } finally {
      setPracticeResetting(false);
    }
  }
  function skipTourStep() {
    const t = tourRef.current;
    if (!t) return;
    if (t.step >= COURSES[t.course].steps.length - 1) {
      localStorage.setItem(`jamak.tour.${COURSES[t.course].id}`, "1");
      tourPausedRef.current = false;
      setTour(null);
      return;
    }
    const next = { course: t.course, step: t.step + 1 };
    setTour(next);
    afterTourAdvance(next);
  }
  // 내보내기 전 점검 모달 (QC + 선택적 AI 맞춤법). null = closed.
  const [qcModal, setQcModal] = useState<null | {
    report: QcReport | null; // null while loading
    spell: SpellSuggestion[] | null; // null = not run yet
    spellBusy: boolean;
    accepted: Set<number>; // segment_ids the reviewer kept checked
  }>(null);
  const [showKeys, setShowKeys] = useState(true);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  // 오타 지목 단계(open-row)의 자동 통과: 직전 흐름 확인의 "확인+다음"이 이미
  // 그 행을 열어둔 경우가 흔하다 — 열려 있으면 누를 글이 없으니 막다른 골목.
  // 지목 행이 이미 포커스면 연 것으로 치고 다음(고치기) 단계로 넘어간다.
  useEffect(() => {
    const t = tourRef.current;
    if (t === null) return;
    const step = COURSES[t.course].steps[t.step];
    if (step?.on !== "open-row" || !(step.targetDefect || step.subject)) return;
    if (!tourGateOpen(t)) return;
    const m = resolveTourTarget()?.match(/data-segid="(\d+)"/);
    if (m && focusedId === Number(m[1])) {
      const next = { course: t.course, step: t.step + 1 };
      setTour(next);
      afterTourAdvance(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedId, tour, tourGate]);
  // 행 오디오 모드: 확인+다음으로 행이 바뀌면 새 행을 한 번 들려준다
  useEffect(() => {
    if (!tourLoopRef.current || focusedId === null) return;
    const seg = segmentsRef.current.find((s) => s.id === focusedId);
    if (seg) {
      seekTo(seg.start);
      play();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusedId]);
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
  // a practice-session clone's video_id is "<base>~<key>" — the YouTube player
  // must load the real video id (PLAN v4 §4.3)
  const ytVideoId = videoId.split("~")[0];
  const { currentTime, playing, rate, setRate, seekTo, seekBy, play, pause, playPause } =
    usePlayer(ytVideoId, dragFreezeRef);

  // 체크포인트 감시: 나레이션이 지시를 마친 시각에 영상을 멈추고 말풍선을 연다
  // (usePlayer 아래 위치 필수 — currentTime/pause 사용)
  useEffect(() => {
    if (!tour) return;
    if (currentTime > tourMaxTimeRef.current) tourMaxTimeRef.current = currentTime;
    const at = stepCheckpoint(tour);
    if (at === null) {
      setTourGate(true);
      return;
    }
    if (tourMaxTimeRef.current < at) {
      setTourGate(false);
      return;
    }
    setTourGate(true);
    if (tourFiredRef.current !== tour.step) {
      tourFiredRef.current = tour.step;
      tourEnterStep(tour); // loopRow = 대상 행 1회 재생, 그 외 = 일시정지
    }
    // 안내 단계가 떠 있는 동안 화면 구성을 통째로 바꾸는 미리보기 모드가
    // 켜지면 스포트라이트·말풍선이 대상을 잃는다 — 즉시 되돌리고 안내
    // (미리보기를 가르치는 단계는 예외). 사용자 피드백 2026-07-15.
    {
      const st = COURSES[tour.course].steps[tour.step];
      if (practice && showPreview && st && !st.final && st.on !== "preview") {
        setShowPreview(false);
        setStatusMsg("연습 단계 중에는 미리보기 모드를 잠시 꺼 둘게요 — 이 단계가 끝나면 다시 켤 수 있어요");
      }
    }
    // 행 오디오 모드: 행 끝에 닿으면 정지 (1회 듣기 — 반복은 ▶로 사용자가)
    if (tourLoopRef.current && playing) {
      const fs = segmentsRef.current.find((s) => s.id === focusedIdRef.current);
      if (fs && currentTime >= fs.end - 0.05) pause();
    }
    // showPreview 포함: 체크포인트에서 멈춘 동안(currentTime 정지) 토글돼도 잡게
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTime, tour, practice, showPreview]);

  const rowsRef = useRef(new Map<number, RowHandle>());
  const focusedIdRef = useRef<number | null>(null);
  const segmentsRef = useRef<Segment[]>([]);
  const undoStackRef = useRef<UndoEntry[]>([]);
  const paceRef = useRef<number[]>([]); // timestamps of recent confirms → pace
  const prevReviewedRef = useRef(0);
  const prevPctRef = useRef(0);
  // latest player time for stable (non-re-registered) keyboard/undo closures
  const currentTimeRef = useRef(0);
  currentTimeRef.current = currentTime;
  // per-segment save chains: optimistic edits apply to the UI instantly, the
  // PUTs run in the background but strictly in order per segment
  const saveQueuesRef = useRef(new Map<number, Promise<void>>());
  const langRef = useRef(lang);
  langRef.current = lang;
  segmentsRef.current = segments;
  undoStackRef.current = undoStack;

  // Latest closures for the once-registered keyboard listener and the stable
  // callback props MemoRow depends on (a re-created prop would defeat memo).
  // All function declarations below are hoisted, so this assignment sees them.
  const H = useRef({
    save,
    timeChange,
    setTimes,
    timing,
    structure,
    focusSegment,
    markFocused,
    undoLast,
    replayCurrent,
    runRepair,
    runTighten,
    runAbsorb,
    hold,
    confirmActive,
    tourEvent,
    seekTo,
    seekBy,
    play,
    pause,
    playPause,
    pauseOnType,
    playing,
    words,
    mode,
  });
  H.current = {
    save,
    timeChange,
    setTimes,
    timing,
    structure,
    focusSegment,
    markFocused,
    undoLast,
    replayCurrent,
    runRepair,
    runTighten,
    runAbsorb,
    hold,
    confirmActive,
    tourEvent,
    seekTo,
    seekBy,
    play,
    pause,
    playPause,
    pauseOnType,
    playing,
    words,
    mode,
  };

  // stable Row props (identity never changes → MemoRow can actually skip)
  const onSaveCb = useCallback(
    (id: number, text: string, reviewed: boolean | null, next: boolean) =>
      H.current.save(id, text, reviewed, next),
    [],
  );
  const onTimeCb = useCallback(
    (seg: Segment, field: "start" | "end", v: number) => H.current.timeChange(seg, field, v),
    [],
  );
  const onSetTimesCb = useCallback(
    (seg: Segment, s: number, e: number) => H.current.setTimes(seg, s, e),
    [],
  );
  const onTimingCb = useCallback(
    (action: "start-here" | "next-here", seg: Segment) => H.current.timing(action, seg),
    [],
  );
  const onStructureCb = useCallback(
    (action: "split" | "merge" | "delete", seg: Segment, position?: number) =>
      H.current.structure(action, seg, position),
    [],
  );
  const onSeekCb = useCallback((t: number) => H.current.seekTo(t), []);
  const onPlayFromCb = useCallback((t: number) => {
    H.current.seekTo(t);
    H.current.play();
  }, []);
  const onTypingCb = useCallback(() => {
    // pause once when editing starts — reads live values via H
    if (H.current.pauseOnType && H.current.playing) H.current.pause();
  }, []);
  const onFocusRowCb = useCallback((id: number) => H.current.markFocused(id), []);
  const onOpenRowCb = useCallback((seg: Segment) => {
    H.current.focusSegment(seg);
    tourEvent("open-row"); // 사용자가 자막 글을 직접 눌렀을 때만 (프로그램 포커스 제외)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const onHoldCb = useCallback((seg: Segment) => H.current.hold(seg), []);
  const onDragActiveCb = useCallback((a: boolean) => {
    dragFreezeRef.current = a;
  }, []);
  const onRegisterCb = useCallback((id: number, h: RowHandle | null) => {
    if (h) rowsRef.current.set(id, h);
    else rowsRef.current.delete(id);
  }, []);

  useEffect(() => {
    fetchLanguages().then(setLangs).catch(() => {});
    fetchWords(videoId).then(setWords).catch(() => setWords([]));
  }, [videoId]);

  // segments for the CURRENT track (ko source, or a forked language). Empty for
  // a non-forked translation language → the translation-review view is shown.
  useEffect(() => {
    // undo is per-track: restore-rows is scoped to one lang and rewrites rows
    // by original id. A snapshot from another track carries foreign ids that
    // would hit the wrong rows. Clear undo/focus whenever the track changes.
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
  const nHold = segments.filter((s) => s.review_flag === "hold" && !s.reviewed).length;
  const textMode = mode === "text";
  // 타이밍 모드 문제 큐: cues a human should look at — too fast to read, or an
  // implausible duration (자동 정리가 대부분 없애고, 남은 것만 순회)
  const issues = useMemo(
    () =>
      segments.filter(
        (s) => s.too_fast || s.end - s.start > 7.05 || s.end - s.start < 0.34,
      ),
    [segments],
  );
  // 따라하기 자동 시작: 첫 에디터 방문(기본기 미완료) + 내용 모드 + 자막 있는 트랙.
  // 코스 딥링크(pendingCourse)가 있으면 그쪽이 우선 — 같은 커밋에서 이 effect의
  // tour===null 가드는 startCourse의 setTour를 못 보고 basic으로 덮어썼다
  // (기본기 미완료 신규 사용자가 연습 2~6에 들어가면 엉뚱한 투어가 뜨던 버그).
  useEffect(() => {
    if (
      tour === null &&
      !pendingCourse &&
      segments.length > 0 &&
      (isKo || forked) &&
      mode === "text" &&
      !courseDone("basic")
    )
      setTour({ course: 0, step: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segments.length]);

  function nextIssue() {
    if (!issues.length) return;
    tourEvent("next-issue");
    const from = focusedIdRef.current;
    const i = from != null ? segments.findIndex((s) => s.id === from) : -1;
    const target =
      segments.slice(i + 1).find((s) => issues.includes(s)) ?? issues[0];
    focusSegment(target);
  }
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
    // 보류(잘 안 들림) rows are deliberately postponed — visit every fresh cue
    // first, and only land on held ones when nothing else is left
    const fresh = (s: Segment) => !s.reviewed && s.review_flag !== "hold";
    return (
      list.slice(startIndex).find(fresh) ??
      list.find(fresh) ??
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


  // 잘 안 들림/보류 toggle (ADR-0009): mark, skip to the next fresh cue, come
  // back later. Confirming a cue clears the flag server-side.
  function hold(seg: Segment | undefined) {
    if (!seg || seg.reviewed) return;
    const before = segmentsRef.current.find((s) => s.id === seg.id);
    if (!before) return;
    tourEvent("hold");
    const flag = before.review_flag === "hold" ? "" : "hold";
    pushOpUndo(flag ? "보류 표시" : "보류 해제", [before]);
    applyRows([{ ...before, review_flag: flag }]);
    void queueSave(seg.id, async () => {
      try {
        const updated = await updateSegment(seg.id, { review_flag: flag });
        applyRows([updated]);
      } catch (e) {
        applyRows([before]);
        setError(String(e));
      }
    });
    if (flag) {
      setStatusMsg("🙉 나중에 다시 듣기로 표시 — 다음 자막으로");
      focusSegment(nextWorkTarget(segmentsRef.current, seg.id));
    } else {
      setStatusMsg("보류를 해제했습니다");
    }
  }

  // 흘려듣기: Enter outside a text box confirms the cue the video is playing,
  // without pausing — the reviewer just keeps listening
  function confirmActive() {
    const segs = segmentsRef.current;
    const t = currentTimeRef.current;
    const cur = segs.find((s) => t >= s.start && t < s.end);
    if (!cur || cur.reviewed) return;
    void save(cur.id, displayText(cur), true, false);
    setStatusMsg("확인 완료 ✓ — 계속 재생");
  }

  // revisit held cues with a listening preset: slower + looped
  function replayHolds() {
    const list = segmentsRef.current;
    const from = focusedIdRef.current;
    const fromIndex = from != null ? list.findIndex((s) => s.id === from) : -1;
    const held =
      list.slice(fromIndex + 1).find((s) => s.review_flag === "hold" && !s.reviewed) ??
      list.find((s) => s.review_flag === "hold" && !s.reviewed);
    if (!held) return;
    setRate(0.75);
    setLoopSeg(true);
    // focus WITHOUT grabbing the textarea (focusSegment would fire onTyping →
    // pause-on-edit and immediately stop the playback we're starting)
    markFocused(held.id);
    seekTo(held.start);
    play();
    setStatusMsg("보류 자막 — 0.75배속 · 구간반복으로 다시 들려드려요");
  }

  // replay the subtitle you're on, from its start (works while typing)
  function replayCurrent() {
    tourEvent("replay");
    const segs = segmentsRef.current;
    const t = currentTimeRef.current;
    const cur =
      segs.find((s) => s.id === focusedIdRef.current) ??
      segs.find((s) => t >= s.start && t < s.end);
    if (cur) {
      seekTo(cur.start);
      play();
    }
  }

  async function continueWork() {
    tourEvent("nav-unreviewed"); // "이어서 작업하기"도 미검수 이동과 같은 동작
    await flushAll();
    const target = nextWorkTarget(segmentsRef.current, focusedIdRef.current ?? activeId ?? null);
    focusSegment(target);
    setStatusMsg(target ? "이어서 작업할 자막으로 이동했습니다" : "이동할 자막이 없습니다");
  }

  function pushEntry(entry: UndoEntry) {
    // ref is the source of truth (multiple pushes can land in one render)
    const next = [...undoStackRef.current.slice(-49), entry];
    undoStackRef.current = next;
    setUndoStack(next);
  }

  /** snapshot the rows an operation is about to change (call BEFORE mutating);
   *  createdIds = rows the op created (known after), deleted again on undo */
  function pushOpUndo(label: string, before: Segment[], createdIds: number[] = []) {
    pushEntry({
      label,
      kind: "op",
      segId: null,
      focusedId: focusedIdRef.current,
      upsert: before.map((s) => ({ ...s })),
      deleteIds: createdIds,
    });
  }

  /** text edits get one undo step per editing session of a cell: consecutive
   *  autosaves of the same segment coalesce into the first snapshot (fine-
   *  grained undo inside the textarea is the browser's native Ctrl+Z) */
  function pushTextUndo(before: Segment) {
    const top = undoStackRef.current[undoStackRef.current.length - 1];
    if (top && top.kind === "text" && top.segId === before.id) return;
    pushEntry({
      label: "글 수정",
      kind: "text",
      segId: before.id,
      focusedId: before.id,
      upsert: [{ ...before }],
      deleteIds: [],
    });
  }

  async function undoLast() {
    const entry = undoStackRef.current[undoStackRef.current.length - 1];
    if (!entry) return;
    try {
      // land any in-flight text edit AND queued background PUTs first, so a
      // late save can't overwrite the restore we're about to do
      await flushAll();
      await Promise.all(Array.from(saveQueuesRef.current.values()));
      const restored = await restoreRows(videoId, langRef.current, entry.upsert, entry.deleteIds);
      // keep client-computed fields (safe) from rows we already had
      const oldById = new Map(segmentsRef.current.map((s) => [s.id, s]));
      const merged = restored.map((r) => {
        const o = oldById.get(r.id);
        return o ? { ...o, ...r } : r;
      });
      segmentsRef.current = merged;
      setSegments(merged);
      const rest = undoStackRef.current.slice(0, -1);
      undoStackRef.current = rest;
      setUndoStack(rest);
      focusedIdRef.current = entry.focusedId;
      setFocusedId(entry.focusedId);
      setStatusMsg(`${entry.label} 되돌림`);
      tourEvent("undo");
      if (entry.focusedId) {
        window.setTimeout(() => rowsRef.current.get(entry.focusedId ?? -1)?.focus(), 0);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  // ---- global keyboard workflow (Amara/YouTube Studio conventions)
  // Registered ONCE: every mutable value is read through a ref (currentTimeRef,
  // segmentsRef, H). The old version re-registered on every player tick.
  useEffect(() => {
    function currentRow(): Segment | undefined {
      const segs = segmentsRef.current;
      const t = currentTimeRef.current;
      return (
        segs.find((s) => s.id === focusedIdRef.current) ??
        segs.find((s) => t >= s.start && t < s.end)
      );
    }
    function deleteRow(row: Segment | undefined) {
      if (!row) return;
      const handle = rowsRef.current.get(row.id);
      void (handle ? handle.flush() : Promise.resolve()).then(() =>
        H.current.structure("delete", row),
      );
    }
    function onKey(e: KeyboardEvent) {
      if ((e as any).isComposing) return;
      if (isCellUndoShortcut(e)) {
        e.preventDefault();
        void H.current.undoLast();
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
        H.current.replayCurrent();
        return;
      }

      // 흘려듣기 (내용 모드): Enter outside a text box = confirm the cue the
      // video is playing, without pausing. Inside a text box Enter keeps its
      // usual meaning (확인+다음) via the textarea handler.
      if (
        e.key === "Enter" &&
        !e.ctrlKey &&
        !e.altKey &&
        !e.shiftKey &&
        !e.metaKey &&
        !isTypingTarget(e.target) &&
        H.current.mode === "text"
      ) {
        e.preventDefault();
        H.current.confirmActive();
        return;
      }

      // ===== PLAYBACK & NAVIGATION — arrows and Tab NEVER edit data, so a
      // mis-press or a slipped Shift can only move the playhead/selection =====
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (e.shiftKey) {
          H.current.seekBy(-3);
          H.current.tourEvent("seek-back");
        } else {
          H.current.playPause();
          H.current.tourEvent("play");
        }
        return;
      }
      if (e.code === "Space" && !e.ctrlKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault();
        H.current.playPause();
        H.current.tourEvent("play");
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
        H.current.seekBy(e.key === "ArrowLeft" ? -step : step);
        H.current.tourEvent(
          e.shiftKey ? "seek-10" : e.key === "ArrowLeft" ? "seek-back" : "seek-fwd",
        );
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
          H.current.tourEvent("nav-unreviewed");
          const from = cur ? segs.findIndex((s) => s.id === cur.id) : dir === 1 ? -1 : segs.length;
          for (let i = from + dir; i >= 0 && i < segs.length; i += dir) {
            if (!segs[i].reviewed) {
              H.current.focusSegment(segs[i]);
              return;
            }
          }
          return;
        }
        H.current.tourEvent("nav");
        if (!cur) return;
        const next = segs[segs.findIndex((s) => s.id === cur.id) + dir];
        if (next) H.current.focusSegment(next);
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
        if (e.key === "[") flushThen(() => H.current.timing("start-here", row));
        else if (e.key === "]") flushThen(() => H.current.timing("next-here", row));
        else {
          const inside = H.current.words.filter((w) => {
            const m = (w.start + w.end) / 2;
            return row.start <= m && m < row.end;
          });
          if (inside.length) {
            const ns = Math.min(...inside.map((w) => w.start));
            const ne = Math.max(...inside.map((w) => w.end));
            H.current.setTimes(row, Math.round(ns * 1000) / 1000, Math.round(ne * 1000) / 1000);
          }
        }
        return;
      }
      // mode toggles + left-panel tools (Alt + letter) — safe while typing
      if (e.altKey && !e.ctrlKey && !e.shiftKey && /^[a-z]$/i.test(e.key)) {
        const actions: Record<string, () => void> = {
          r: () => {
            setLoopSeg((v) => !v);
            H.current.tourEvent("loop");
          },
          s: () => {
            setPauseOnType((v) => !v);
            H.current.tourEvent("pausetype");
          },
          p: () => {
            setShowPreview((v) => !v);
            H.current.tourEvent("preview");
          },
          b: () => {
            setFindOpen((v) => !v);
            H.current.tourEvent("find");
          },
          g: () => void H.current.runRepair(),
          m: () => void H.current.runTighten(),
          k: () => void H.current.runAbsorb(),
          h: () => H.current.hold(currentRow()),
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
  }, []);

  /** Patch the local list with server/optimistic rows — no whole-track refetch.
   *  Known ids are merged in place (keeping client-computed fields like `safe`),
   *  unknown ids (split's new half) are inserted; removeIds drop rows. The list
   *  is kept in time order. Untouched row objects keep their identity so
   *  MemoRow skips them. */
  function applyRows(changed: Segment[], removeIds: number[] = []) {
    let list =
      removeIds.length > 0
        ? segmentsRef.current.filter((s) => !removeIds.includes(s.id))
        : segmentsRef.current.slice();
    for (const row of changed) {
      const i = list.findIndex((s) => s.id === row.id);
      if (i >= 0) list[i] = { ...list[i], ...row };
      else list.push(row as Segment);
    }
    list.sort((a, b) => a.start - b.start || a.end - b.end);
    segmentsRef.current = list;
    setSegments(list);
    return list;
  }

  /** serialize background PUTs per segment so they land in typing order */
  function queueSave(id: number, task: () => Promise<void>): Promise<void> {
    const prev = saveQueuesRef.current.get(id) ?? Promise.resolve();
    const next = prev.then(task, task);
    saveQueuesRef.current.set(id, next);
    return next;
  }

  // Optimistic: the UI (and Enter's jump to the next cue) reacts instantly;
  // the PUT runs in the background and the server row reconciles when it lands.
  function save(id: number, text: string, reviewed: boolean | null, next: boolean): Promise<void> {
    if (reviewed) tourEvent("confirm");
    const before = segmentsRef.current.find((s) => s.id === id);
    if (!before) return Promise.resolve();
    const changed =
      text !== displayText(before) || (reviewed !== null && reviewed !== before.reviewed);
    if (changed) {
      pushTextUndo(before);
      applyRows([
        { ...before, text_final: text, ...(reviewed !== null ? { reviewed } : {}) },
      ]);
    }
    if (next) focusSegment(nextWorkTarget(segmentsRef.current, id));
    if (!changed) return Promise.resolve();
    const body: Parameters<typeof updateSegment>[1] = { text_final: text };
    if (reviewed !== null) body.reviewed = reviewed;
    return queueSave(id, async () => {
      try {
        const updated = await updateSegment(id, body);
        applyRows([updated]);
      } catch (e) {
        applyRows([before]); // roll the optimistic edit back
        setError(String(e));
      }
    });
  }

  // Optimistic nudge (◀▶ / time field): clamp locally exactly like the server
  // (independent resize, walled at the neighbour), then reconcile in background.
  function timeChange(seg: Segment, field: "start" | "end", value: number) {
    const list = segmentsRef.current;
    const i = list.findIndex((s) => s.id === seg.id);
    if (i < 0) return;
    const before = list[i];
    pushOpUndo("시간 조정", [before]);
    const v = Math.max(0, Math.round(value * 1000) / 1000);
    const optimistic = { ...before };
    if (field === "start") {
      const lo = i > 0 ? list[i - 1].end : 0;
      optimistic.start = Math.round(Math.min(Math.max(v, lo), before.end - 0.1) * 1000) / 1000;
    } else {
      const hi = i < list.length - 1 ? list[i + 1].start : v;
      optimistic.end = Math.round(Math.max(Math.min(v, hi), before.start + 0.1) * 1000) / 1000;
    }
    applyRows([optimistic]);
    setStatusMsg("시간 조정됨 - Alt+Z로 되돌릴 수 있습니다");
    void queueSave(seg.id, async () => {
      try {
        const updated = await updateSegment(seg.id, { [field]: v });
        applyRows([updated]);
      } catch (e) {
        applyRows([before]);
        setError(String(e));
      }
    });
  }

  // timeline-strip edge drag: hybrid neighbour push (see edge_drag endpoint).
  // The response carries the changed rows (this cue + maybe the pushed
  // neighbour) — patch them in, no track refetch.
  async function edgeDragCommit(seg: Segment, which: "start" | "end", time: number) {
    tourEvent("edge-drag");
    try {
      // let any queued background PUT for this segment land first (ordering)
      await (saveQueuesRef.current.get(seg.id) ?? Promise.resolve());
      const list = segmentsRef.current;
      const i = list.findIndex((s) => s.id === seg.id);
      const neighbour = which === "start" ? list[i - 1] : list[i + 1];
      pushOpUndo("시간 조정", neighbour ? [list[i], neighbour] : [list[i]]);
      const r = await edgeDrag(seg.id, which, Math.max(0, Math.round(time * 1000) / 1000));
      applyRows(r.segments);
      setStatusMsg("시간 조정됨 - Alt+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  // set both bounds at once (speech-map drag / 발화 맞춤) — one undo step
  function setTimes(seg: Segment, start: number, end: number) {
    tourEvent("set-times");
    const list = segmentsRef.current;
    const i = list.findIndex((s) => s.id === seg.id);
    if (i < 0) return;
    const before = list[i];
    pushOpUndo("시간 맞춤", [before]);
    const lo = i > 0 ? list[i - 1].end : 0;
    const hi = i < list.length - 1 ? list[i + 1].start : Math.max(start + 0.1, end);
    const ns = Math.min(Math.max(Math.max(0, start), lo), before.end - 0.1);
    const optimistic = {
      ...before,
      start: Math.round(ns * 1000) / 1000,
      end: Math.round(Math.max(Math.min(Math.max(start + 0.1, end), hi), ns + 0.1) * 1000) / 1000,
    };
    applyRows([optimistic]);
    setStatusMsg("발화 구간에 맞췄습니다 - Alt+Z로 되돌릴 수 있습니다");
    void queueSave(seg.id, async () => {
      try {
        const updated = await updateSegment(seg.id, {
          start: Math.max(0, start),
          end: Math.max(start + 0.1, end),
        });
        applyRows([updated]);
      } catch (e) {
        applyRows([before]);
        setError(String(e));
      }
    });
  }

  async function timing(action: "start-here" | "next-here", seg: Segment, atTime?: number) {
    tourEvent(action); // "start-here" | "next-here"
    try {
      const t = atTime ?? currentTimeRef.current;
      await (saveQueuesRef.current.get(seg.id) ?? Promise.resolve());
      const list = segmentsRef.current;
      const i = list.findIndex((s) => s.id === seg.id);
      const neighbour = action === "start-here" ? list[i - 1] : list[i + 1];
      pushOpUndo(
        action === "start-here" ? "시작 맞춤" : "넘김 맞춤",
        neighbour ? [list[i], neighbour] : [list[i]],
      );
      const r =
        action === "start-here" ? await boundaryPrev(seg.id, t) : await boundaryNext(seg.id, t);
      applyRows(r.segments);
      setStatusMsg("경계가 맞춰졌습니다 - Alt+Z로 되돌릴 수 있습니다");
    } catch (e) {
      setError(String(e));
    }
  }

  async function structure(action: "split" | "merge" | "delete", seg: Segment, position?: number) {
    tourEvent(action); // "split" | "merge" | "delete"
    try {
      const label = action === "split" ? "나누기" : action === "merge" ? "합치기" : "삭제";
      await (saveQueuesRef.current.get(seg.id) ?? Promise.resolve());
      const list = segmentsRef.current;
      const i = list.findIndex((s) => s.id === seg.id);
      if (i < 0) return;
      const before = list[i];
      if (action === "split") {
        const r = await splitSegment(seg.id, position ?? 0);
        // undo deletes the created right half and restores the original row
        pushOpUndo(label, [before], r.segments.slice(1).map((s) => s.id));
        applyRows(r.segments);
      } else if (action === "merge") {
        const nxt = list[i + 1];
        const r = await mergeNext(seg.id);
        pushOpUndo(label, nxt ? [before, nxt] : [before]);
        applyRows(r.segments, r.deleted_id != null ? [r.deleted_id] : []);
      } else {
        const r = await deleteSegment(seg.id);
        pushOpUndo(label, [before]);
        const nextSegments = applyRows([], [r.deleted_id]);
        focusSegment(nextTimelineTarget(nextSegments, seg));
      }
      setStatusMsg(
        action === "delete"
          ? "자막을 지웠습니다 - Alt+Z로 바로 복구할 수 있습니다"
          : `${label} 완료 - Alt+Z로 되돌릴 수 있습니다`,
      );
    } catch (e) {
      setError(String(e));
    }
  }

  async function refreshSegments() {
    const next = await fetchSegments(videoId, langRef.current);
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
      !(await askConfirm({
        title: "독립 편집 해제",
        body:
          `${langLabel} 독립 편집을 해제하고 한국어 구조를 따르는 번역 검수로 되돌려요. ` +
          `편집한 번역 텍스트는 한국어 자막에 맞춰 복원돼요 (재분할한 경우 근사 복원).`,
        ok: "되돌릴게요",
      }))
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
    tourEvent("repair");
    setToolBusy("repair");
    await flushAll();
    try {
      const r = await repairStt(videoId);
      await refreshSegments();
      const parts: string[] = [];
      if (r.repaired) parts.push(`오류 ${r.repaired}곳 복구`);
      if (r.filled) parts.push(`빈 구간 ${r.filled}곳 유튜브 자막으로 채움`);
      setToolMsg(
        parts.length
          ? `🛠 ${parts.join(", ")} (유튜브 자막 기반, 검수 필요)` +
              (r.no_caption ? ` · 자막 없는 ${r.no_caption}곳은 직접 수정` : "")
          : "🛠 복구·보충할 구간을 찾지 못했어요 — 이미 깨끗한 상태",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setToolBusy(null);
    }
  }

  // ✨ 자동 정리 (ADR-0009): server does absorb → snap → split → extend and
  // returns before-rows + created ids, so the whole cleanup is ONE undo step
  // 자체 확인 모달 (브라우저 confirm은 앱과 생김새가 달라 붕 뜬다 — 사용자 피드백)
  const [askAutoTiming, setAskAutoTiming] = useState(false);
  function runAutoTiming() {
    setAskAutoTiming(true);
  }
  async function doAutoTiming() {
    setAskAutoTiming(false);
    tourEvent("auto-timing");
    setToolBusy("auto");
    await flushAll();
    try {
      const r = await autoTiming(videoId, lang);
      if (r.before.length) {
        pushEntry({
          label: "자동 정리",
          kind: "op",
          segId: null,
          focusedId: focusedIdRef.current,
          upsert: r.before,
          deleteIds: r.created_ids,
        });
      }
      applyRows(r.segments);
      setToolMsg(
        r.tightened || r.split
          ? `✨ 자동 정리 완료 — 말소리에 맞춤 ${r.tightened}개 · 나눔 ${r.split}개 (↶로 되돌리기 가능)`
          : "✨ 이미 잘 정리되어 있어요 — 손볼 게 없습니다",
      );
    } catch (e) {
      // 연습판이 서버 정리로 사라진 경우(no job): 조용히 새 판을 만들어 복구
      if (practice && String(e).includes("no job")) {
        try {
          await practiceSession(ytVideoId, practiceKey(), true);
          const next = await fetchSegments(videoId, langRef.current);
          segmentsRef.current = next;
          setSegments(next);
          setUndoStack([]);
          undoStackRef.current = [];
          setToolMsg("연습판을 새로 준비했어요 — ✨ 버튼을 다시 눌러주세요");
          return;
        } catch {
          /* fall through to error */
        }
      }
      setError(String(e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runTighten() {
    tourEvent("tighten");
    setToolBusy("tighten");
    await flushAll();
    try {
      const r = await tightenTiming(videoId);
      await refreshSegments();
      setToolMsg(
        r.tightened
          ? `✂ ${r.tightened}개 자막을 실제 발화 구간에 맞춰 다듬었어요 — 침묵 구간엔 자막이 사라집니다`
          : "✂ 이미 발화 구간에 맞게 다듬어져 있어요",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runConfirmSafe() {
    tourEvent("confirm-safe");
    setToolBusy("safe");
    await flushAll();
    try {
      const r = await confirmSafe(videoId);
      await refreshSegments();
      setToolMsg(`✅ 안심 구간 ${r.confirmed}개를 한번에 확인했어요 — 이제 남은 것만 보세요`);
    } catch (e) {
      setError(String(e));
    } finally {
      setToolBusy(null);
    }
  }

  async function runAbsorb() {
    tourEvent("absorb");
    setToolBusy("absorb");
    await flushAll();
    try {
      const r = await absorbFeedback(videoId);
      await refreshSegments();
      setToolMsg(
        r.new_pairs || r.bumped || r.propagated_segments
          ? `📚 학습 완료 — 확인한 자막 ${r.reviewed_segments}개에서 고침 ${r.new_pairs}가지를 새로 배웠어요` +
              (r.bumped ? ` (${r.bumped}가지는 더 확실해짐)` : "") +
              (r.propagated_segments
                ? `, 뒤쪽 자막 ${r.propagated_segments}개에 ${r.propagated_replacements}곳 바로 반영`
                : "")
          : practice
            ? "📚 연습용 영상이라 실제 학습은 하지 않아요 (버튼 위치 연습 성공!)"
            : `📚 학습 완료 — 확인한 자막 ${r.reviewed_segments}개, 새로 배울 고침은 없었어요 (이미 다 아는 내용)`,
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setToolBusy(null);
    }
  }

  // "자막 받기" now goes through a pre-export check first (ADR-0009 follow-up):
  // rule QC is free and instant; AI 맞춤법 is an opt-in button inside the modal.
  async function openExportCheck() {
    tourEvent("export-check");
    if (!(isKo || forked)) {
      // inherited translation view has no own segments to QC — export directly
      void doExport();
      return;
    }
    await flushAll();
    setQcModal({ report: null, spell: null, spellBusy: false, accepted: new Set() });
    try {
      const report = await fetchQc(videoId, lang);
      setQcModal((m) => (m ? { ...m, report } : m));
    } catch (e) {
      setQcModal(null);
      setError(String(e));
    }
  }

  function jumpToQc(ids: number[]) {
    const target = segmentsRef.current.find((s) => ids.includes(s.id));
    setQcModal(null);
    if (target) focusSegment(target);
  }

  async function runSpell() {
    setQcModal((m) => (m ? { ...m, spellBusy: true } : m));
    try {
      const r = await runSpellcheck(videoId, lang);
      setQcModal((m) =>
        m
          ? {
              ...m,
              spellBusy: false,
              spell: r.suggestions,
              accepted: new Set(r.suggestions.map((s) => s.segment_id)),
            }
          : m,
      );
    } catch (e) {
      setQcModal((m) => (m ? { ...m, spellBusy: false } : m));
      setError(String(e));
    }
  }

  function applySpell() {
    const m = qcModal;
    if (!m || !m.spell) return;
    const chosen = m.spell.filter((s) => m.accepted.has(s.segment_id));
    if (!chosen.length) {
      setQcModal(null);
      return;
    }
    const before = segmentsRef.current.filter((s) =>
      chosen.some((c) => c.segment_id === s.id),
    );
    // one undo step for the whole batch — Alt+Z reverts every accepted fix
    pushOpUndo("맞춤법 적용", before);
    applyRows(
      chosen.map((c) => {
        const old = before.find((s) => s.id === c.segment_id)!;
        return { ...old, text_final: c.after };
      }),
    );
    for (const c of chosen) {
      void queueSave(c.segment_id, async () => {
        try {
          const updated = await updateSegment(c.segment_id, { text_final: c.after });
          applyRows([updated]);
        } catch (e) {
          setError(String(e));
        }
      });
    }
    setQcModal(null);
    setStatusMsg(`✏️ 맞춤법 ${chosen.length}곳 적용 — Alt+Z로 전체 되돌릴 수 있어요`);
  }

  async function doExport() {
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
    <div
      className={
        "editor" +
        (showPreview ? " preview" : "") +
        (bigType ? " bigtype" : "") +
        (fontScale === 2 ? " bigtype2" : "")
      }
    >
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
          {/* 글씨 크기 3단계 세그먼트 — .bigtype-btn 클래스는 투어 타겟 유지 */}
          <span className="bigtype-btn font-seg" role="group" aria-label="글씨 크기">
            <span className="font-seg-label">글씨</span>
            {(["보통", "크게", "최대"] as const).map((label, i) => (
              <button
                key={label}
                className={"font-seg-btn s" + i + (fontScale === i ? " on" : "")}
                title={`글씨 ${label}`}
                onClick={() => {
                  setFontScale(i);
                  tourEvent("bigtype");
                }}
              >
                가
              </button>
            ))}
          </span>
          <button
            className="mset-btn"
            title="재생 설정 (구간반복·멈춤·따라가기·미리보기)"
            onClick={() => setMobileSettings(true)}
          >
            ⚙ 설정
          </button>
          <ThemeToggle />
        </div>
        {practice && (
          <div className="practice-banner" title="연습용 영상 — 여기서의 편집은 학습 데이터에 반영되지 않아요">
            🎓 <b>연습용 영상</b>이에요 — 마음껏 눌러보고 고쳐보세요. 실제 작업에
            영향이 없어요.
            {videoId.includes("~") && (
              <button
                className="practice-restart"
                disabled={practiceResetting}
                title="내 연습 내용을 지우고 처음 상태로 (다른 분들에게는 영향 없음)"
                onClick={() => void practiceRestart()}
              >
                {practiceResetting ? "되돌리는 중..." : "↺ 처음부터 다시"}
              </button>
            )}
          </div>
        )}
        <div className="player-wrap">
          <div id="yt-player" />
          {showPreview &&
            (() => {
              // show the language being reviewed on the video, not Korean.
              let cc = "";
              let ccKey: number | undefined;
              if (isKo || forked) {
                // current track has its own segments/timing
                if (activeSeg) {
                  cc = displayText(activeSeg);
                  ccKey = activeSeg.id;
                }
              } else {
                // non-forked translation: no lang segments exist, so drive the
                // overlay off the inherited Korean timing (koRefSegs) and show
                // this language's translation for the active Korean cue. Without
                // this the on-video preview was dead until the track was forked.
                const koSeg = koRefSegs.find(
                  (k) => currentTime >= k.start && currentTime < k.end,
                );
                if (koSeg) {
                  cc = transMap[koSeg.id] ?? "";
                  ccKey = koSeg.id;
                }
              }
              return cc ? (
                <div className="cc-overlay">
                  {/* key by cue id → React remounts the span per cue, replaying
                      the fade-in (a caption change reads as a new line) */}
                  <span key={ccKey}>{cc}</span>
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
          <button
            className="pc-btn"
            title="3초 뒤로 (Ctrl+← 또는 Shift+Tab)"
            onClick={() => {
              seekBy(-3);
              tourEvent("seek-back");
            }}
          >
            ⟲ 3초
          </button>
          <button
            className="pc-btn play"
            title="재생 / 일시정지 (Tab, 또는 편집칸 밖에서 Space)"
            onClick={() => {
              tourEvent("play");
              playPause();
            }}
          >
            {playing ? "⏸ 멈춤" : "▶ 재생"}
          </button>
          <button
            className="pc-btn"
            title="3초 앞으로 (Ctrl+→)"
            onClick={() => {
              seekBy(3);
              tourEvent("seek-fwd");
            }}
          >
            3초 ⟳
          </button>
          <div className="pc-speed" title="재생 속도 — 느리게 하면 타이밍·발음 검수가 쉬워요">
            {[0.5, 0.75, 1, 1.5].map((r) => (
              <button
                key={r}
                type="button"
                className={"pc-speed-btn" + (rate === r ? " on" : "")}
                onClick={() => {
                  setRate(r);
                  tourEvent("rate");
                }}
              >
                {r}×
              </button>
            ))}
          </div>
          <div className="pc-settings">
            <label className="pc-toggle pc-toggle-loop" title="편집 중인 구간의 소리를 반복 재생 (되감기 없이 다시 듣기) (Alt+R)">
              <input
                type="checkbox"
                checked={loopSeg}
                onChange={(e) => {
                  setLoopSeg(e.target.checked);
                  tourEvent("loop");
                }}
              />
              🔁 구간반복
            </label>
            <label
              className="pc-toggle pc-toggle-pause"
              title="구간을 클릭해 편집을 시작할 때 영상을 한 번 멈춤 (타이핑·백스페이스로는 안 멈춰서 재생·구간반복 들으며 편집 가능) (Alt+S)"
            >
              <input
                type="checkbox"
                checked={pauseOnType}
                onChange={(e) => {
                  setPauseOnType(e.target.checked);
                  tourEvent("pausetype");
                }}
              />
              편집 시작 시 멈춤
            </label>
            {textMode && (
              <label
                className="pc-toggle pc-toggle-follow"
                title="영상을 계속 틀어두면 지금 나오는 자막이 화면 가운데로 따라옵니다. 맞으면 Enter만 누르세요 (확인+계속 재생)"
              >
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(e) => {
                    setFollow(e.target.checked);
                    tourEvent("follow");
                  }}
                />
                🎧 자동 따라가기
              </label>
            )}
            <label
              className="pc-toggle pc-toggle-preview"
              title="미리보기(극장) 모드 — 영상을 크게, 자막을 영상 위에 얹고, 재생 중인 자막을 화면 가운데로 따라 스크롤. 최종 확인용 (편집은 끄고) (Alt+P)"
            >
              <input
                type="checkbox"
                checked={showPreview}
                onChange={(e) => {
                  setShowPreview(e.target.checked);
                  tourEvent("preview");
                }}
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
        {/* 내용 모드에선 타임라인 자체를 치움 — 시간을 만질 일이 없다는 시각적 약속 */}
        {!textMode && (
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
        )}
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
            title="방금 작업 하나 되돌리기 (Alt+Z)"
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
                <span>
                  {nRemaining
                    ? nHold && nRemaining === nHold
                      ? `남은 건 보류 ${nHold}개뿐`
                      : `${nRemaining}개 남음${nHold ? ` (보류 ${nHold})` : ""}`
                    : "모두 확인 🎉"}
                </span>
                {eta && <em className="flow-eta">{eta}</em>}
              </div>
              {nHold > 0 && (
                <button
                  className="hold-replay"
                  title="잘 안 들려서 보류한 자막을 0.75배속 + 구간반복으로 다시 들려드립니다"
                  onClick={() => replayHolds()}
                >
                  🙉 보류 {nHold}개 다시 듣기
                </button>
              )}
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
              className="tool accent tool-safe"
              disabled={!!toolBusy}
              title="두 음성인식이 일치하고 어려운 용어도 없는 '안심' 구간을 한번에 확인. 나머지에만 집중하세요."
              onClick={() => void runConfirmSafe()}
            >
              {toolBusy === "safe" ? "⏳ 확인 중..." : `✅ 안심 ${nSafe}개 확인`}
            </button>
          )}
          {!textMode && (
            <button
              className="tool accent tool-auto"
              disabled={!!toolBusy}
              title="타이밍을 기계가 먼저 정리 — 말소리에 맞추고, 너무 긴 자막은 나누고, 너무 빠른 자막은 표시 시간을 늘림 (되돌리기 가능)"
              onClick={() => void runAutoTiming()}
            >
              {toolBusy === "auto" ? "⏳ 정리 중..." : "✨ 타이밍 자동 정리"}
            </button>
          )}
          {!textMode && (
            <button
              className="tool tool-tighten"
              disabled={!!toolBusy}
              title="자막을 실제 발화 시작~끝 구간에 딱 맞춰 다듬어 침묵 구간엔 자막이 안 보이게 함 (텍스트·검수 상태는 그대로, API 사용 안 함) (Alt+M)"
              onClick={() => void runTighten()}
            >
              {toolBusy === "tighten" ? "⏳ 다듬는 중..." : "✂ 무음 다듬기"}
            </button>
          )}
          <button
            className="tool tool-repair"
            disabled={!!toolBusy}
            title="음성인식이 놓치거나 잘못 뱉은 구간을 유튜브 자막으로 복구·보충 (API 사용 안 함) (Alt+G)"
            onClick={() => void runRepair()}
          >
            {toolBusy === "repair" ? "⏳ 복구 중..." : "🛠 복구·채우기"}
          </button>
          <button
            className="tool tool-absorb"
            disabled={!!toolBusy}
            title="이번에 고친 내용을 뒤쪽 미검수 자막에 반영하고 다음 실행에도 기억 (Alt+K)"
            onClick={() => void runAbsorb()}
          >
            {toolBusy === "absorb" ? "⏳ 학습 중..." : "📚 학습"}
          </button>
        </div>
        )}
        {toolMsg && (
          <div className="tool-msg" role="status" aria-live="polite">
            {toolMsg}
          </div>
        )}

        {/* export footer */}
        <div className="export-footer">
          {(isKo || forked) && !textMode && (
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
            <Dropdown
              value={lang}
              onChange={setLang}
              title={koDone ? "편집·내보낼 언어 트랙 선택" : "한국어 검수를 마치면 번역 언어를 선택할 수 있어요"}
              options={langs.map((l) => {
                // a forked track is independent of Korean completeness — never
                // lock/mislabel it. Only inherited (non-forked) translations are
                // gated on ko being done.
                const locked = l.code !== "ko" && !koDone && !forkedLangs.has(l.code);
                return {
                  value: l.code,
                  label: l.label,
                  disabled: locked,
                  note: locked ? "한국어 검수 후" : undefined,
                };
              })}
            />
            <button className="export" disabled={exporting} onClick={() => void openExportCheck()}>
              {exporting
                ? lang === "ko"
                  ? "저장하는 중..."
                  : "번역하는 중... (처음엔 1~2분)"
                : "자막 받기 (.srt)"}
            </button>
          </div>
          <div className="hint">받으면 고친 내용이 뒤쪽 자막과 다음 실행에 자동 반영됩니다</div>
        </div>
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
        {/* sticky right-panel header — mode tabs + issue queue + find bar in ONE
            opaque sticky container. Before, .mode-tabs and .findbar were each
            `sticky; top:0` (and the closed findbar was transparent), so they
            overlapped and rows bled through above the tabs. */}
        {(isKo || forked) && (
          <div className="right-head">
          <div className="mode-tabs" role="tablist" aria-label="검수 단계">
            <button
              role="tab"
              aria-selected={textMode}
              className={"mode-tab" + (textMode ? " on" : "")}
              title="말한 내용과 자막 글이 맞는지만 봅니다 — 시간은 신경 쓰지 마세요"
              onClick={() => setMode("text")}
            >
              <strong>① 내용 확인</strong>
              <span>
                {segments.length
                  ? nReviewed === segments.length
                    ? "완료 ✓"
                    : `${nReviewed}/${segments.length}`
                  : ""}
              </span>
            </button>
            <button
              role="tab"
              aria-selected={!textMode}
              className={"mode-tab" + (!textMode ? " on" : "")}
              title="자막이 뜨고 사라지는 시간을 맞춥니다 — 내용 확인이 끝난 뒤에"
              onClick={() => {
                setMode("timing");
                tourEvent("mode-timing");
              }}
            >
              <strong>② 타이밍</strong>
              <span>{(isKo ? timingDone : langTimingDone) ? "완료 ✓" : "자막 시간 맞추기"}</span>
            </button>
          </div>
          {/* 타이밍 모드: 남은 문제 자막만 골라 순회 */}
          {!textMode && issues.length > 0 && (
            <div className="issue-bar">
              <span>⏱ 다듬을 자막 {issues.length}개 (너무 빠르거나 길거나 짧음)</span>
              <button className="issue-next" onClick={() => nextIssue()}>
                다음 문제 →
              </button>
            </div>
          )}
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
                onClick={() => {
                  setFindOpen(true);
                  tourEvent("find");
                }}
              >
                🔎 찾기·바꾸기
              </button>
            )}
          </div>
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
            {segments.map((seg, i) => (
            <MemoRow
              key={seg.id}
              seg={seg}
              active={seg.id === activeId}
              focused={seg.id === focusedId}
              // 흘려듣기: follow-along centering reuses the preview behaviour
              // (active cue centered + expanded) without the theater layout
              preview={showPreview || (textMode && follow)}
              textMode={textMode}
              // only the row that actually shows the playhead re-renders per
              // player tick — the rest get a constant and MemoRow skips them
              currentTime={seg.id === activeId || seg.id === focusedId ? currentTime : -1}
              hasNext={i < segments.length - 1}
              koRef={
                isKo
                  ? undefined
                  : koRefSegs
                      .filter((k) => k.start < seg.end && k.end > seg.start)
                      .map((k) => displayText(k))
                      .join(" ")
                      .trim() || undefined
              }
              words={words}
              onRegister={onRegisterCb}
              onSeek={onSeekCb}
              onPlayFrom={onPlayFromCb}
              onSave={onSaveCb}
              onTime={onTimeCb}
              onSetTimes={onSetTimesCb}
              onTiming={onTimingCb}
              onStructure={onStructureCb}
              onTyping={onTypingCb}
              onFocusRow={onFocusRowCb}
              onOpenRow={onOpenRowCb}
              onHold={onHoldCb}
              onDragActive={onDragActiveCb}
            />
            ))}
          </>
        )}
      </div>
      {/* 모바일 재생 설정 시트 — 데스크톱 체크박스 2줄의 모바일 문법 대체 */}
      {mobileSettings && (
        <div className="sheet-back" onMouseDown={(e) => e.target === e.currentTarget && setMobileSettings(false)}>
          <div className="sheet" role="dialog" aria-label="재생 설정">
            <h3>재생 설정</h3>
            <button
              className="sheet-row"
              onClick={() => {
                replayCurrent();
                setMobileSettings(false);
              }}
            >
              ⏮ 이 자막 처음부터 다시 재생
            </button>
            <label className="sheet-row">
              <input
                type="checkbox"
                checked={loopSeg}
                onChange={(e) => {
                  setLoopSeg(e.target.checked);
                  tourEvent("loop");
                }}
              />
              🔁 구간반복 — 지금 자막 소리를 계속 반복
            </label>
            <label className="sheet-row">
              <input
                type="checkbox"
                checked={pauseOnType}
                onChange={(e) => {
                  setPauseOnType(e.target.checked);
                  tourEvent("pausetype");
                }}
              />
              편집 시작 시 멈춤
            </label>
            {textMode && (
              <label className="sheet-row">
                <input
                  type="checkbox"
                  checked={follow}
                  onChange={(e) => {
                    setFollow(e.target.checked);
                    tourEvent("follow");
                  }}
                />
                🎧 자동 따라가기 — 나오는 자막을 화면 가운데로
              </label>
            )}
            <label className="sheet-row">
              <input
                type="checkbox"
                checked={showPreview}
                onChange={(e) => {
                  setShowPreview(e.target.checked);
                  tourEvent("preview");
                }}
              />
              💬 미리보기 모드 — 영화 보듯 최종 확인
            </label>
            <button className="sheet-close" onClick={() => setMobileSettings(false)}>
              닫기
            </button>
          </div>
        </div>
      )}
      {/* 모바일 하단 바 (CSS로 좁은 화면에서만 표시): 흘려듣기 루프의 핵심
          동작을 엄지 영역에 — 3초 뒤 / 재생 / 🙉 / 지금 나온 자막 확인.
          데스크톱의 "입력칸 밖 Enter" 확인을 터치로 대체. */}
      {textMode && (isKo || forked) && (
        <div className="mobile-bar">
          <button
            className="mb-btn"
            onClick={() => {
              seekBy(-3);
              tourEvent("seek-back");
            }}
          >
            ⟲ 3초
          </button>
          <button
            className="mb-btn"
            onClick={() => {
              tourEvent("play");
              playPause();
            }}
          >
            {playing ? "⏸ 멈춤" : "▶ 재생"}
          </button>
          <button
            className="mb-btn"
            title="잘 안 들림 — 나중에 다시"
            onClick={() =>
              hold(activeSeg ?? segments.find((s) => s.id === focusedId))
            }
          >
            🙉
          </button>
          <button
            className="mb-btn"
            title="방금 한 일 되돌리기 (Alt+Z와 동일)"
            disabled={undoStack.length === 0}
            onClick={() => void undoLast()}
          >
            ↶
          </button>
          <button
            className="mb-btn mb-confirm"
            title="지금 나오는 자막이 맞으면 확인"
            onClick={() => confirmActive()}
          >
            ✔ 맞아요
          </button>
        </div>
      )}
      {confirmNode}
      {/* ✨ 자동 정리 확인 — 앱 디자인의 자체 모달 (브라우저 confirm 대체) */}
      {askAutoTiming && (
        <div
          className="srt-modal-back"
          onMouseDown={(e) => e.target === e.currentTarget && setAskAutoTiming(false)}
        >
          <div className="srt-modal confirm-mini" onClick={(e) => e.stopPropagation()}>
            <h3>✨ 타이밍 자동 정리</h3>
            <p className="srt-summary">
              자막 시간을 실제 말소리에 맞추고, 너무 긴 자막은 나누고, 너무 빠른
              자막은 표시 시간을 늘려요.
              <br />글 내용과 확인 완료 상태는 그대로예요. <b>Alt+Z(↶)</b>로 전체
              되돌릴 수 있어요.
            </p>
            <div className="confirm-actions">
              <button className="tour-exit" onClick={() => setAskAutoTiming(false)}>
                취소
              </button>
              <button className="tour-finish" onClick={() => void doAutoTiming()}>
                ✨ 정리할게요
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 따라하기 투어 — 실제 컨트롤을 하나씩 밝혀 직접 해보게 함.
          동기화 코스에선 나레이션이 지시를 마친 순간에만 뜬다 (체크포인트). */}
      {tour !== null && tourGate && (
        <Tour
          steps={COURSES[tour.course].steps}
          step={tour.step}
          onExit={() => endTour(false)}
          onSkipStep={skipTourStep}
          onFinish={() => endTour(true)}
          targetOverride={resolveTourTarget()}
          note={tourNote()}
        />
      )}
      {/* 체크포인트 대기 중: 영상이 선생 — 화면은 자유, 작은 안내만 */}
      {tour !== null && !tourGate && (
        <div className="tour-wait">
          <span>
            🎓 {tour.step + 1}단계 준비 중 — <b>영상 설명을 따라가세요</b>
          </span>
          <button onClick={() => endTour(false)}>그만두기</button>
        </div>
      )}
      {/* 🎓 코스 선택 메뉴 */}
      {tourMenu && (
        <div
          className="srt-modal-back"
          onMouseDown={(e) => e.target === e.currentTarget && setTourMenu(false)}
        >
          <div className="srt-modal tour-menu" onClick={(e) => e.stopPropagation()}>
            <h3>🎓 따라하기 — 무엇을 연습할까요?</h3>
            <p className="srt-summary">
              실제 화면에서 한 단계씩 직접 해보는 연습이에요. 순서대로 하셔도 되고,
              필요한 것만 골라 하셔도 돼요.
              {practice
                ? " 이 영상은 연습용이라 마음껏 만져도 돼요."
                : " 연습은 🎓 연습용 영상에서 하는 걸 권해요. (모든 연습은 Alt+Z로 되돌릴 수 있어요)"}
            </p>
            <div className="tour-courses">
              {COURSES.map((c, i) => {
                // 코스 전용 연습 영상이 따로 있으면 그 영상으로 건너가서 시작
                // (App이 이 브라우저 전용 클론을 만들어 열어줌 — 항상 처음 상태)
                const dedicated = tutorials[c.id];
                const goElsewhere =
                  !!dedicated && dedicated !== ytVideoId && !!onOpenCourseVideo;
                return (
                  <button
                    key={c.id}
                    className="tour-course"
                    onClick={() => {
                      if (goElsewhere) {
                        setTourMenu(false);
                        onOpenCourseVideo!(c.id);
                      } else {
                        startCourse(i);
                      }
                    }}
                  >
                    <span className="tc-icon">{c.icon}</span>
                    <span className="tc-body">
                      <strong>{c.title}</strong>
                      <span>
                        {c.desc}
                        {goElsewhere && (
                          <em className="tc-jump"> · 전용 연습 영상에서 열려요 →</em>
                        )}
                      </span>
                    </span>
                    <span className={"tc-state" + (courseDone(c.id) ? " done" : "")}>
                      {courseDone(c.id) ? "다시 하기 ✓" : `${c.steps.length - 1}단계`}
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="srt-actions">
              <button className="srt-cancel" onClick={() => setTourMenu(false)}>
                닫기
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 내보내기 전 점검 (QC + AI 맞춤법) — reuses the .srt modal styling */}
      {qcModal && (
        <div
          className="srt-modal-back"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !qcModal.spellBusy) setQcModal(null);
          }}
        >
          <div className="srt-modal qc-modal" onClick={(e) => e.stopPropagation()}>
            <h3>📋 내보내기 전 점검</h3>
            {!qcModal.report ? (
              <p className="srt-summary">점검하는 중...</p>
            ) : qcModal.spell !== null ? (
              // ---- 맞춤법 결과: diff checklist, 선택 적용 ----
              qcModal.spell.length === 0 ? (
                <>
                  <p className="srt-summary">✅ 맞춤법 문제를 찾지 못했습니다.</p>
                  <div className="srt-actions">
                    <button className="srt-cancel" onClick={() => setQcModal(null)}>
                      닫기
                    </button>
                    <button
                      className="srt-apply"
                      onClick={() => {
                        setQcModal(null);
                        void doExport();
                      }}
                    >
                      자막 받기 (.srt)
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="srt-summary">
                    맞춤법 제안 <strong>{qcModal.spell.length}곳</strong> — 체크한 것만
                    적용됩니다 (적용 후 Alt+Z로 전체 되돌리기 가능)
                  </p>
                  <div className="spell-list">
                    {qcModal.spell.map((s) => (
                      <label key={s.segment_id} className="spell-row">
                        <input
                          type="checkbox"
                          checked={qcModal.accepted.has(s.segment_id)}
                          onChange={(e) =>
                            setQcModal((m) => {
                              if (!m) return m;
                              const next = new Set(m.accepted);
                              if (e.target.checked) next.add(s.segment_id);
                              else next.delete(s.segment_id);
                              return { ...m, accepted: next };
                            })
                          }
                        />
                        <span className="spell-diff">
                          <span className="spell-before">{s.before}</span>
                          <span className="spell-arrow">→</span>
                          <span className="spell-after">{s.after}</span>
                        </span>
                        <span className="spell-time">{fmt(s.start)}</span>
                      </label>
                    ))}
                  </div>
                  <div className="srt-actions">
                    <button className="srt-cancel" onClick={() => setQcModal(null)}>
                      취소
                    </button>
                    <button
                      className="srt-apply"
                      disabled={qcModal.accepted.size === 0}
                      onClick={() => applySpell()}
                    >
                      선택한 {qcModal.accepted.size}곳 적용
                    </button>
                  </div>
                </>
              )
            ) : (
              // ---- QC 요약 ----
              <>
                {qcModal.report.issues === 0 && qcModal.report.unreviewed === 0 ? (
                  <p className="srt-summary">
                    ✅ 자막 {qcModal.report.total}개 — 문제를 찾지 못했습니다. 받아도
                    좋아요.
                  </p>
                ) : (
                  <p className="srt-summary">
                    자막 {qcModal.report.total}개를 점검했습니다. 아래 항목은 그대로
                    받아도 되지만, 한 번 보고 받는 걸 권해요.
                  </p>
                )}
                <div className="qc-list">
                  {(
                    [
                      ["미확인 자막", qcModal.report.unreviewed, null],
                      ["🙉 보류 (잘 안 들림)", qcModal.report.hold.length, qcModal.report.hold],
                      ["빈 자막", qcModal.report.empty.length, qcModal.report.empty],
                      ["너무 빠름 (17자/초 초과)", qcModal.report.too_fast.length, qcModal.report.too_fast],
                      ["두 줄 초과 (36자 넘음)", qcModal.report.too_long_text.length, qcModal.report.too_long_text],
                      ["너무 짧거나 긴 자막", qcModal.report.bad_duration.length, qcModal.report.bad_duration],
                      ["중복 공백", qcModal.report.double_space.length, qcModal.report.double_space],
                    ] as [string, number, number[] | null][]
                  ).map(([label, count, ids]) => (
                    <div key={label} className={"qc-row" + (count ? " warn" : "")}>
                      <span className="qc-mark">{count ? "⚠" : "✓"}</span>
                      <span className="qc-label">{label}</span>
                      <span className="qc-count">{count ? `${count}개` : "없음"}</span>
                      {count > 0 && ids && (
                        <button className="qc-jump" onClick={() => jumpToQc(ids)}>
                          보기 →
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <div className="srt-actions">
                  <button className="srt-cancel" onClick={() => setQcModal(null)}>
                    닫기
                  </button>
                  {isKo && (
                    <button
                      className="qc-spell"
                      disabled={qcModal.spellBusy}
                      title="AI가 맞춤법·띄어쓰기 오타를 찾아 제안합니다. 제안만 하고, 적용은 직접 고릅니다."
                      onClick={() => void runSpell()}
                    >
                      {qcModal.spellBusy ? "검사 중... (수십 초)" : "✏️ 맞춤법 검사 (AI)"}
                    </button>
                  )}
                  <button
                    className="srt-apply"
                    onClick={() => {
                      setQcModal(null);
                      void doExport();
                    }}
                  >
                    자막 받기 (.srt)
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
