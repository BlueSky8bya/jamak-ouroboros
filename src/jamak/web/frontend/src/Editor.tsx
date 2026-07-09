import { useEffect, useMemo, useRef, useState } from "react";
import {
  absorbFeedback,
  boundaryNext,
  boundaryPrev,
  deleteSegment,
  exportUrl,
  fetchLanguages,
  fetchSegments,
  mergeNext,
  repairStt,
  restoreSegments,
  splitSegment,
  updateSegment,
} from "./api";
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
  onSeek,
  onBoundaryDrag,
}: {
  segments: Segment[];
  currentTime: number;
  activeId: number | undefined;
  focusedId: number | null;
  onSeek: (t: number) => void;
  onBoundaryDrag: (segId: number, time: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  // while dragging a boundary, freeze the window + show a live preview time.
  // dragRef mirrors state so move/up handlers see the current drag even
  // between renders (fast drags would otherwise read a stale closure).
  const [drag, setDrag] = useState<{ segId: number; time: number } | null>(null);
  const dragRef = useRef<{ segId: number; time: number } | null>(null);
  const winRef = useRef<{ start: number; span: number } | null>(null);
  function setDragState(v: { segId: number; time: number } | null) {
    dragRef.current = v;
    setDrag(v);
  }

  const focused = segments.find((s) => s.id === focusedId);
  const live = (() => {
    if (drag && winRef.current) return winRef.current;
    const center = focused ? (focused.start + focused.end) / 2 : currentTime;
    const start = Math.max(0, center - 8);
    const end = Math.max(start + 12, center + 8);
    return { start, span: end - start };
  })();
  const { start, span } = live;
  const end = start + span;
  const local = segments.filter((s) => s.end >= start && s.start <= end);
  const marker = clamp(((currentTime - start) / span) * 100, 0, 100);

  function timeAtClientX(clientX: number): number {
    const rect = trackRef.current!.getBoundingClientRect();
    const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
    return start + ratio * span;
  }

  function startDrag(e: React.PointerEvent, seg: Segment) {
    e.stopPropagation();
    e.preventDefault();
    winRef.current = { start, span }; // freeze window for the whole drag
    try {
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    } catch {
      /* capture unavailable (e.g. synthetic pointer) — drag still works */
    }
    setDragState({ segId: seg.id, time: seg.end });
  }
  function moveDrag(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    setDragState({ segId: d.segId, time: timeAtClientX(e.clientX) });
  }
  function endDrag(e: React.PointerEvent) {
    const d = dragRef.current;
    if (!d) return;
    const t = timeAtClientX(e.clientX);
    onBoundaryDrag(d.segId, t);
    setDragState(null);
    winRef.current = null;
  }

  return (
    <div className="timing-strip">
      <div className="strip-track" ref={trackRef} onPointerMove={moveDrag} onPointerUp={endDrag}>
        {local.map((s) => {
          const left = clamp(((s.start - start) / span) * 100, 0, 100);
          const right = clamp(((s.end - start) / span) * 100, 0, 100);
          const hasNext = segments.some((o) => o.job_id === s.job_id && o.idx === s.idx + 1);
          const handleLeft =
            drag?.segId === s.id ? clamp(((drag.time - start) / span) * 100, 0, 100) : right;
          return (
            <div key={s.id}>
              <button
                className={
                  "strip-seg" +
                  (s.id === activeId ? " active" : "") +
                  (s.id === focusedId ? " focused" : "")
                }
                style={{ left: `${left}%`, width: `${Math.max(1.5, right - left)}%` }}
                title={`#${segmentNo(segments, s.id)} ${fmt(s.start)} - ${fmt(s.end)}`}
                aria-label={`자막 ${segmentNo(segments, s.id)}로 이동`}
                onClick={() => onSeek(s.start)}
              />
              {hasNext && (
                <span
                  className={"strip-handle" + (drag?.segId === s.id ? " dragging" : "")}
                  style={{ left: `${handleLeft}%` }}
                  title="드래그해서 이 자막과 다음 자막의 경계를 조절"
                  onPointerDown={(e) => startDrag(e, s)}
                />
              )}
            </div>
          );
        })}
        <span className="strip-marker" style={{ left: `${marker}%` }} />
        {drag && (
          <span className="strip-drag-time" style={{ left: `${clamp(((drag.time - start) / span) * 100, 0, 100)}%` }}>
            {fmt(drag.time)}
          </span>
        )}
      </div>
      <div className="strip-meta">
        <span>{fmt(start)}</span>
        <span className="strip-hint">경계를 드래그해 미세조정</span>
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
  return (
    (e.altKey && e.key === "Delete" && !e.ctrlKey && !e.metaKey && !e.shiftKey) ||
    (e.ctrlKey && e.key === "Escape" && !e.altKey && !e.metaKey && !e.shiftKey)
  );
}

function isCellUndoShortcut(e: KeyboardEvent): boolean {
  return e.altKey && e.key.toLowerCase() === "z" && !e.ctrlKey && !e.metaKey && !e.shiftKey;
}

function Row({
  seg,
  active,
  focused,
  currentTime,
  hasNext,
  register,
  onSeek,
  onSave,
  onTime,
  onTiming,
  onStructure,
  onTyping,
  onFocusRow,
}: {
  seg: Segment;
  active: boolean;
  focused: boolean;
  currentTime: number;
  hasNext: boolean;
  register: (h: RowHandle | null) => void;
  onSeek: (t: number) => void;
  onSave: (id: number, text: string, reviewed: boolean | null, next: boolean) => Promise<void>;
  onTime: (seg: Segment, field: "start" | "end", value: number) => void;
  onTiming: (action: "start-here" | "next-here", seg: Segment) => void;
  onStructure: (action: "split" | "merge" | "delete", seg: Segment, position?: number) => void;
  onTyping: () => void;
  onFocusRow: (id: number) => void;
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
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  const showSources = seg.flagged || seg.llm_uncertain;
  const playPct =
    currentTime >= seg.start && currentTime <= seg.end
      ? clamp(((currentTime - seg.start) / Math.max(0.001, seg.end - seg.start)) * 100, 0, 100)
      : null;

  return (
    <div
      ref={ref}
      className={
        "row" +
        (active ? " active" : "") +
        (focused ? " focused" : "") +
        (seg.reviewed ? " reviewed" : "") +
        (seg.flagged || seg.llm_uncertain ? " needs-attention" : "")
      }
    >
      <div className="row-head">
        <button className="time" onClick={() => onSeek(seg.start)} title="이 구간 재생">
          ▶
        </button>
        <TimeField value={seg.start} title="시작 시간" onCommit={(v) => onTime(seg, "start", v)} />
        <span className="time-sep">→</span>
        <TimeField value={seg.end} title="끝 시간" onCommit={(v) => onTime(seg, "end", v)} />
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
          {seg.reviewed && <span className="badge ok">확인 완료</span>}
        </span>
      </div>
      {playPct !== null && (
        <div className="cue-rail" title={`영상 위치 ${fmt(currentTime)}`}>
          <span className="cue-fill" style={{ width: `${playPct}%` }} />
          <span className="cue-dot" style={{ left: `${playPct}%` }} />
        </div>
      )}
      <textarea
        ref={taRef}
        value={text}
        rows={Math.max(2, Math.ceil(text.length / 40))}
        onFocus={() => onFocusRow(seg.id)}
        onChange={(e) => {
          setText(e.target.value);
          dirtyRef.current = true;
          onTyping();
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
      {showSources && (
        <div className="sources">
          <div className="sources-title">
            참고용 — 기계가 각자 들은 내용. 맞는 걸 <b>가져오기</b>로 바로 채울 수 있어요
          </div>
          <div className="src-line">
            <span className="src-label w">음성인식</span>
            <span className="src-text">{seg.text_whisper}</span>
            {seg.text_whisper.trim() && (
              <button className="src-fill" title="이 내용을 편집칸에 채우기" onClick={() => fillFrom(seg.text_whisper.trim())}>
                가져오기
              </button>
            )}
          </div>
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
        <span className="timing-tools">
          <button
            title="현재 영상 시간을 이 자막의 시작으로 맞추고, 이전 자막 끝도 같이 맞춤"
            onClick={() => void flush().then(() => onTiming("start-here", seg))}
          >
            여기서 시작
          </button>
          <button
            title="현재 영상 시간에서 이 자막을 끝내고 다음 자막으로 넘김"
            onClick={() => void flush().then(() => onTiming("next-here", seg))}
          >
            {hasNext ? "여기서 넘김" : "여기서 끝"}
          </button>
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
    title: "재생과 이동",
    items: [
      { keys: ["Tab"], label: "재생 / 일시정지", detail: "스페이스바는 입력 전용" },
      { keys: ["Ctrl+\\"], label: "이 자막 처음부터 다시 재생", detail: "편집 중에도 동작" },
      { keys: ["Shift+Tab"], label: "3초 뒤로", detail: "놓친 부분 다시 듣기" },
      { keys: ["Alt+↑", "Alt+↓"], label: "이전 / 다음 자막으로 이동" },
    ],
  },
  {
    title: "글자 편집",
    items: [
      { keys: ["Delete"], label: "글자 삭제", detail: "편집칸 안에서는 기본 텍스트 삭제" },
      { keys: ["Ctrl+Z"], label: "글자 되돌리기", detail: "편집칸 안에서는 텍스트 Undo" },
      { keys: ["Enter"], label: "확인 완료 후 다음 자막" },
    ],
  },
  {
    title: "자막 셀 조작",
    items: [
      { keys: ["Alt+Delete"], label: "현재 셀 바로 삭제", detail: "편집 중에도 마우스 없이 삭제" },
      { keys: ["Delete"], label: "현재 셀 삭제", detail: "편집칸 밖에서만" },
      { keys: ["Alt+Z"], label: "셀 조작 되돌리기", detail: "편집 중에도 세그먼트 Undo" },
      { keys: ["Ctrl+Z"], label: "셀 조작 되돌리기", detail: "편집칸 밖에서만" },
      { keys: ["Ctrl+Esc"], label: "셀 삭제 보조키", detail: "브라우저가 전달할 때만" },
      { keys: ["Ctrl+Enter"], label: "커서 위치에서 나누기" },
      { keys: ["Ctrl+Shift+Enter"], label: "아래 자막과 합치기" },
    ],
  },
  {
    title: "시간 보정",
    items: [
      { keys: ["Alt+←", "Alt+→"], label: "시작 시간 0.1초 조절" },
      { keys: ["Alt+Shift+←", "Alt+Shift+→"], label: "끝 시간 0.1초 조절" },
    ],
  },
];

export function Editor({ videoId, onBack }: { videoId: string; onBack: () => void }) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [error, setError] = useState("");
  const [absorbMsg, setAbsorbMsg] = useState("");
  const [langs, setLangs] = useState<{ code: string; label: string }[]>([]);
  const [lang, setLang] = useState("ko");
  const [exporting, setExporting] = useState(false);
  const [pauseOnType, setPauseOnType] = useState(true);
  const [showKeys, setShowKeys] = useState(true);
  const [focusedId, setFocusedId] = useState<number | null>(null);
  const [undoStack, setUndoStack] = useState<UndoEntry[]>([]);
  const [statusMsg, setStatusMsg] = useState("");
  const { currentTime, playing, seekTo, seekBy, play, pause, playPause } = usePlayer(videoId);

  const rowsRef = useRef(new Map<number, RowHandle>());
  const focusedIdRef = useRef<number | null>(null);
  const segmentsRef = useRef<Segment[]>([]);
  const undoStackRef = useRef<UndoEntry[]>([]);
  segmentsRef.current = segments;
  undoStackRef.current = undoStack;

  useEffect(() => {
    fetchSegments(videoId)
      .then((nextSegments) => {
        segmentsRef.current = nextSegments;
        setSegments(nextSegments);
      })
      .catch((e) => setError(String(e)));
    fetchLanguages().then(setLangs).catch(() => {});
  }, [videoId]);

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

  const nReviewed = segments.filter((s) => s.reviewed).length;
  const nRemaining = Math.max(0, segments.length - nReviewed);
  const koComplete = segments.length > 0 && nReviewed === segments.length;
  const langLabel = langs.find((l) => l.code === lang)?.label ?? lang;

  // never let a locked language stay selected
  useEffect(() => {
    if (lang !== "ko" && !koComplete) setLang("ko");
  }, [lang, koComplete]);

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
      const restored = await restoreSegments(videoId, entry.segments);
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
    function focusRow(id: number) {
      rowsRef.current.get(id)?.focus();
    }
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
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) {
        if (!isTypingTarget(e.target)) {
          e.preventDefault();
          void undoLast();
        }
        return;
      }
      if (e.key === "Delete" && !isTypingTarget(e.target)) {
        e.preventDefault();
        deleteRow(currentRow());
        return;
      }
      // Ctrl+\ = replay the current subtitle from its start (safe while typing)
      if ((e.ctrlKey || e.metaKey) && (e.code === "Backslash" || e.key === "\\")) {
        e.preventDefault();
        replayCurrent();
        return;
      }
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (e.shiftKey) seekBy(-3);
        else playPause();
        return;
      }
      // Space toggles play only OUTSIDE text fields (inside, it types a space)
      if (e.code === "Space" && !e.ctrlKey && !e.altKey && !isTypingTarget(e.target)) {
        e.preventDefault();
        playPause();
        return;
      }
      if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
        e.preventDefault();
        const segs = segmentsRef.current;
        const cur = currentRow();
        if (!cur) return;
        const i = segs.findIndex((s) => s.id === cur.id);
        const next = segs[e.key === "ArrowDown" ? i + 1 : i - 1];
        if (next) {
          focusRow(next.id);
          seekTo(next.start);
        }
        return;
      }
      if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        e.preventDefault();
        const row = currentRow();
        if (!row) return;
        const delta = e.key === "ArrowLeft" ? -0.1 : 0.1;
        const field = e.shiftKey ? "end" : "start";
        timeChange(row, field as "start" | "end", (field === "start" ? row.start : row.end) + delta);
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
      const nextSegments = await fetchSegments(videoId);
      segmentsRef.current = nextSegments;
      setSegments(nextSegments);
      setStatusMsg("시간 조정됨 - Ctrl+Z로 되돌릴 수 있습니다");
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
      const nextSegments = await fetchSegments(videoId);
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
      const nextSegments = await fetchSegments(videoId);
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

  return (
    <div className="editor">
      <div className="left">
        <button
          className="back"
          onClick={async () => {
            await flushAll();
            onBack();
          }}
        >
          ← 목록
        </button>
        <div id="yt-player" />
        <div className="play-controls">
          <button
            className="pc-btn"
            title="지금 편집 중인 자막을 처음부터 다시 재생 (Ctrl+\)"
            onClick={replayCurrent}
          >
            ⏮ 구간처음
          </button>
          <button className="pc-btn" title="3초 뒤로 (Shift+Tab)" onClick={() => seekBy(-3)}>
            ⟲ 3초
          </button>
          <button
            className="pc-btn play"
            title="재생 / 일시정지 (Tab, 또는 편집칸 밖에서 Space)"
            onClick={() => playPause()}
          >
            {playing ? "⏸ 멈춤" : "▶ 재생"}
          </button>
          <button className="pc-btn" title="3초 앞으로" onClick={() => seekBy(3)}>
            3초 ⟳
          </button>
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
          onSeek={seekTo}
          onBoundaryDrag={(segId, time) => {
            const seg = segmentsRef.current.find((s) => s.id === segId);
            if (seg) void timing("next-here", { ...seg }, time);
          }}
        />
        <div className="workbar">
          <button className="undo-btn" disabled={!undoStack.length} onClick={() => void undoLast()}>
            ↶ 되돌리기
          </button>
          <span className="work-status">
            {statusMsg || (undoStack.length ? `${undoStack[undoStack.length - 1].label} 되돌릴 수 있음` : "변경 대기")}
          </span>
        </div>
        <button
          className="repair-btn"
          title="음성인식이 프롬프트를 반복 출력한 구간을 유튜브 자막으로 한 번에 되돌립니다 (API 사용 안 함)"
          onClick={async () => {
            await flushAll();
            try {
              const r = await repairStt(videoId);
              const next = await fetchSegments(videoId);
              segmentsRef.current = next;
              setSegments(next);
              setStatusMsg(
                r.repaired
                  ? `음성인식 오류 ${r.repaired}곳을 유튜브 자막으로 복구했습니다` +
                      (r.no_caption ? ` (유튜브 자막 없는 ${r.no_caption}곳은 직접 수정 필요)` : "")
                  : "복구할 음성인식 오류를 찾지 못했습니다",
              );
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          🛠 음성인식 오류 복구
        </button>
        <label className="pause-on-type" title="유튜브 스튜디오와 같은 기능">
          <input
            type="checkbox"
            checked={pauseOnType}
            onChange={(e) => setPauseOnType(e.target.checked)}
          />
          입력하는 동안 영상 자동 멈춤
        </label>
        <div className="progress">
          확인 {nReviewed}/{segments.length}
          <progress value={nReviewed} max={segments.length} />
        </div>
        <button className="continue-btn" disabled={!segments.length} onClick={() => void continueWork()}>
          <span>이어서 작업하기</span>
          <strong>{nRemaining ? `${nRemaining}개 남음` : "완료"}</strong>
        </button>
        <div className="export-row">
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            title={koComplete ? "" : "한국어 검수를 마치면 번역 언어를 선택할 수 있어요"}
          >
            {langs.map((l) => (
              <option key={l.code} value={l.code} disabled={l.code !== "ko" && !koComplete}>
                {l.label}
                {l.code !== "ko" && !koComplete ? " (한국어 검수 후)" : ""}
              </option>
            ))}
          </select>
          <button
            className="export"
            disabled={exporting}
            onClick={async () => {
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
            }}
          >
            {exporting
              ? lang === "ko"
                ? "저장하는 중..."
                : "번역하는 중... (처음엔 1~2분)"
              : "자막 파일 받기 (.srt)"}
          </button>
        </div>
        <div className="hint">파일을 받으면 고친 내용이 현재 영상 뒤쪽 자막과 다음 실행에 자동 반영됩니다</div>
        <button
          className="absorb"
          title="이번에 고친 내용을 현재 영상의 뒤쪽 미검수 자막에 먼저 반영하고 다음 실행에도 기억합니다"
          onClick={async () => {
            await flushAll();
            try {
              const r = await absorbFeedback(videoId);
              const nextSegments = await fetchSegments(videoId);
              segmentsRef.current = nextSegments;
              setSegments(nextSegments);
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
          }}
        >
          📚 고친 내용 학습시키기
        </button>
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
        {lang !== "ko" ? (
          <TranslateReview
            videoId={videoId}
            lang={lang}
            langLabel={langLabel}
            currentTime={currentTime}
            onSeek={seekTo}
          />
        ) : (
          segments.map((seg) => (
            <Row
              key={seg.id}
              seg={seg}
              active={seg.id === activeId}
              focused={seg.id === focusedId}
              currentTime={currentTime}
              hasNext={segments.some((s) => s.job_id === seg.job_id && s.idx === seg.idx + 1)}
              register={(h) => {
                if (h) rowsRef.current.set(seg.id, h);
                else rowsRef.current.delete(seg.id);
              }}
              onSeek={seekTo}
              onSave={save}
              onTime={timeChange}
              onTiming={timing}
              onStructure={structure}
              onTyping={() => {
                if (pauseOnType && playing) pause();
              }}
              onFocusRow={markFocused}
            />
          ))
        )}
      </div>
    </div>
  );
}
