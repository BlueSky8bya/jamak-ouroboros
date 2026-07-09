import { useEffect, useMemo, useRef, useState } from "react";
import {
  absorbFeedback,
  deleteSegment,
  exportUrl,
  fetchLanguages,
  fetchSegments,
  mergeNext,
  splitSegment,
  updateSegment,
} from "./api";
import type { Filter, Segment } from "./types";
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
  flush: () => void;
  focus: () => void;
  segId: number;
}

function Row({
  seg,
  active,
  register,
  onSeek,
  onSave,
  onTime,
  onStructure,
  onTyping,
  onFocusRow,
}: {
  seg: Segment;
  active: boolean;
  register: (h: RowHandle | null) => void;
  onSeek: (t: number) => void;
  onSave: (id: number, text: string, reviewed: boolean | null, next: boolean) => void;
  onTime: (seg: Segment, field: "start" | "end", value: number) => void;
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
  }, [seg.id, seg.text_final]);

  // autosave + unmount flush: edits can never be lost by navigation
  function flush() {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    if (dirtyRef.current) {
      dirtyRef.current = false;
      onSave(seg.id, textRef.current, null, false);
    }
  }

  useEffect(() => {
    const handle: RowHandle = {
      flush,
      focus: () => taRef.current?.focus(),
      segId: seg.id,
    };
    register(handle);
    return () => {
      flush();
      register(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seg.id]);

  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  const showSources = seg.flagged || seg.llm_uncertain;

  return (
    <div
      ref={ref}
      className={
        "row" +
        (active ? " active" : "") +
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
          saveTimer.current = window.setTimeout(flush, 900);
        }}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return; // 한글 조합 중 무시
          if (e.key === "Enter" && e.ctrlKey && e.shiftKey) {
            // Amara 관례: Ctrl+Shift+Enter = 병합
            e.preventDefault();
            flush();
            onStructure("merge", seg);
          } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            // Amara 관례: Ctrl+Enter = 커서 위치에서 분할
            e.preventDefault();
            flush();
            onStructure("split", seg, taRef.current?.selectionStart ?? 0);
          } else if (e.key === "Enter") {
            // Enter = 확정하고 다음 자막으로 (줄바꿈은 내보낼 때 자동)
            e.preventDefault();
            dirtyRef.current = false;
            if (saveTimer.current) window.clearTimeout(saveTimer.current);
            onSave(seg.id, text, true, true);
          }
        }}
        onBlur={flush}
      />
      {showSources && (
        <div className="sources">
          <div className="sources-title">참고용 — 기계가 각자 들은 내용 (판단은 사람이)</div>
          <div>
            <span className="src-label w">음성인식</span> {seg.text_whisper}
          </div>
          {seg.text_youtube && (
            <div>
              <span className="src-label y">유튜브 자막</span> {seg.text_youtube}
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
        <span className="structure">
          <button
            title="텍스트 커서 위치에서 자막을 둘로 나누기 (Ctrl+Enter)"
            onClick={() => {
              flush();
              onStructure("split", seg, taRef.current?.selectionStart ?? 0);
            }}
          >
            ✂ 나누기
          </button>
          <button
            title="아래 자막과 합치기 (Ctrl+Shift+Enter)"
            onClick={() => {
              flush();
              onStructure("merge", seg);
            }}
          >
            ⇣ 합치기
          </button>
          <button
            className="danger"
            title="이 자막 지우기 (박수/잡음 구간 등)"
            onClick={() => {
              if (window.confirm("이 자막을 지울까요?\n" + displayText(seg).slice(0, 40)))
                onStructure("delete", seg);
            }}
          >
            ✕ 지우기
          </button>
        </span>
      </div>
    </div>
  );
}

const SHORTCUTS: [string, string][] = [
  ["Tab", "영상 재생 / 일시정지 (입력 중에도)"],
  ["Shift+Tab", "3초 뒤로 (다시 듣기)"],
  ["Enter", "이 자막 확정 + 다음으로"],
  ["Ctrl+Enter", "커서 위치에서 자막 나누기"],
  ["Ctrl+Shift+Enter", "아래 자막과 합치기"],
  ["Ctrl+Space", "지금 자막 처음부터 다시 재생"],
  ["Alt+↑ / Alt+↓", "이전 / 다음 자막으로 이동"],
  ["Alt+← / Alt+→", "시작 시간 0.1초 조절"],
  ["Alt+Shift+← / →", "끝 시간 0.1초 조절"],
];

export function Editor({ videoId, onBack }: { videoId: string; onBack: () => void }) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");
  const [absorbMsg, setAbsorbMsg] = useState("");
  const [langs, setLangs] = useState<{ code: string; label: string }[]>([]);
  const [lang, setLang] = useState("ko");
  const [exporting, setExporting] = useState(false);
  const [pauseOnType, setPauseOnType] = useState(true);
  const [showKeys, setShowKeys] = useState(true);
  const { currentTime, playing, seekTo, seekBy, pause, playPause } = usePlayer(videoId);

  const rowsRef = useRef(new Map<number, RowHandle>());
  const focusedIdRef = useRef<number | null>(null);
  const segmentsRef = useRef<Segment[]>([]);
  segmentsRef.current = segments;

  useEffect(() => {
    fetchSegments(videoId).then(setSegments).catch((e) => setError(String(e)));
    fetchLanguages().then(setLangs).catch(() => {});
  }, [videoId]);

  // 어떤 경로로 떠나도 수정 내용은 저장된다 (구조적 보장)
  function flushAll() {
    rowsRef.current.forEach((h) => h.flush());
  }
  useEffect(() => {
    const onUnload = () => flushAll();
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      flushAll();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activeId = useMemo(() => {
    const s = segments.find((x) => currentTime >= x.start && currentTime < x.end);
    return s?.id;
  }, [segments, currentTime]);

  const visible = useMemo(() => {
    if (filter === "flagged") return segments.filter((s) => s.flagged || s.llm_uncertain);
    if (filter === "unreviewed") return segments.filter((s) => !s.reviewed);
    return segments;
  }, [segments, filter]);

  const nReviewed = segments.filter((s) => s.reviewed).length;

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
    function onKey(e: KeyboardEvent) {
      if ((e as any).isComposing) return;
      if (e.key === "Tab" && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        if (e.shiftKey) seekBy(-3);
        else playPause();
        return;
      }
      if (e.code === "Space" && e.ctrlKey) {
        const row = currentRow();
        if (row) {
          e.preventDefault();
          seekTo(row.start);
        }
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
      setSegments((prev) => prev.map((s) => (s.id === id ? updated : s)));
      if (next) {
        const list = visible;
        const i = list.findIndex((s) => s.id === id);
        const nxt = list[i + 1];
        if (nxt) {
          seekTo(nxt.start);
          rowsRef.current.get(nxt.id)?.focus();
        }
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function timeChange(seg: Segment, field: "start" | "end", value: number) {
    try {
      const updated = await updateSegment(seg.id, { [field]: Math.max(0, Math.round(value * 1000) / 1000) });
      setSegments((prev) => prev.map((s) => (s.id === seg.id ? updated : s)));
    } catch (e) {
      setError(String(e));
    }
  }

  async function structure(action: "split" | "merge" | "delete", seg: Segment, position?: number) {
    try {
      if (action === "split") await splitSegment(seg.id, position ?? 0);
      else if (action === "merge") await mergeNext(seg.id);
      else await deleteSegment(seg.id);
      setSegments(await fetchSegments(videoId));
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="editor">
      <div className="left">
        <button
          className="back"
          onClick={() => {
            flushAll();
            onBack();
          }}
        >
          ← 목록
        </button>
        <div id="yt-player" />
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
        <div className="filters">
          {(["all", "flagged", "unreviewed"] as Filter[]).map((f) => (
            <button key={f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
              {f === "all" ? `전체 ${segments.length}` : f === "flagged" ? "먼저 볼 곳" : "안 본 곳"}
            </button>
          ))}
        </div>
        <div className="export-row">
          <select value={lang} onChange={(e) => setLang(e.target.value)}>
            {langs.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
          <button
            className="export"
            disabled={exporting}
            onClick={async () => {
              flushAll();
              setExporting(true);
              try {
                const r = await fetch(exportUrl(videoId, "best", lang));
                if (!r.ok) throw new Error(`export: ${r.status}`);
                const blob = await r.blob();
                const cd = r.headers.get("content-disposition") ?? "";
                const m = /filename\*=utf-8''([^;]+)/i.exec(cd);
                const name = m ? decodeURIComponent(m[1]) : `${videoId}_자막_${lang}.srt`;
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
        <div className="hint">파일을 받으면 고친 내용이 자동으로 학습됩니다</div>
        <button
          className="absorb"
          title="이번에 고친 내용을 기억해서 다음 영상부터 같은 실수를 줄입니다"
          onClick={async () => {
            flushAll();
            try {
              const r = await absorbFeedback(videoId);
              setAbsorbMsg(
                `학습 완료 — 확인한 자막 ${r.reviewed_segments}개에서 고침 ${r.new_pairs}가지를 새로 배웠습니다` +
                  (r.bumped ? ` (${r.bumped}가지는 더 확실해짐)` : ""),
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
            ⌨ 단축키 {showKeys ? "접기" : "펼치기"}
          </button>
          {showKeys && (
            <table>
              <tbody>
                {SHORTCUTS.map(([k, desc]) => (
                  <tr key={k}>
                    <td>
                      <kbd>{k}</kbd>
                    </td>
                    <td>{desc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="right">
        {visible.map((seg) => (
          <Row
            key={seg.id}
            seg={seg}
            active={seg.id === activeId}
            register={(h) => {
              if (h) rowsRef.current.set(seg.id, h);
              else rowsRef.current.delete(seg.id);
            }}
            onSeek={seekTo}
            onSave={save}
            onTime={timeChange}
            onStructure={structure}
            onTyping={() => {
              if (pauseOnType && playing) pause();
            }}
            onFocusRow={(id) => (focusedIdRef.current = id)}
          />
        ))}
      </div>
    </div>
  );
}
