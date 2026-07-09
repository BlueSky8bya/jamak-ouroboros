import { useEffect, useMemo, useRef, useState } from "react";
import { exportUrl, fetchSegments, updateSegment } from "./api";
import type { Filter, Segment } from "./types";
import { usePlayer } from "./usePlayer";

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function displayText(seg: Segment): string {
  return seg.text_final || seg.text_llm || seg.text_whisper;
}

function Row({
  seg,
  active,
  onSeek,
  onSave,
  onNudge,
}: {
  seg: Segment;
  active: boolean;
  onSeek: (t: number) => void;
  onSave: (id: number, text: string, reviewed: boolean | null, next: boolean) => void;
  onNudge: (seg: Segment, field: "start" | "end", delta: number) => void;
}) {
  const [text, setText] = useState(displayText(seg));
  const [dirty, setDirty] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setText(displayText(seg));
    setDirty(false);
  }, [seg.id, seg.text_final]);

  useEffect(() => {
    if (active) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [active]);

  const machineDraft = seg.text_llm || seg.text_whisper;
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
        <button className="time" onClick={() => onSeek(seg.start)} title="이 구간으로 이동">
          ▶ {fmt(seg.start)}–{fmt(seg.end)}
        </button>
        <span className="badges">
          {seg.flagged && <span className="badge flag" title="whisper와 자동자막 불일치">불일치</span>}
          {seg.llm_uncertain && <span className="badge unc" title="Claude가 확신 없음 표시">불확실</span>}
          {seg.reviewed && <span className="badge ok">검수됨</span>}
          {dirty && <span className="badge dirty">수정중</span>}
        </span>
        {active && (
          <span className="nudge">
            <button onClick={() => onNudge(seg, "start", -0.1)}>시작−.1</button>
            <button onClick={() => onNudge(seg, "start", +0.1)}>시작+.1</button>
            <button onClick={() => onNudge(seg, "end", -0.1)}>끝−.1</button>
            <button onClick={() => onNudge(seg, "end", +0.1)}>끝+.1</button>
          </span>
        )}
      </div>
      <textarea
        value={text}
        rows={Math.max(2, Math.ceil(text.length / 40))}
        onChange={(e) => {
          setText(e.target.value);
          setDirty(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            onSave(seg.id, text, true, true);
            setDirty(false);
          }
        }}
        onBlur={() => {
          if (dirty) {
            // reviewed=null: blur must not race the checkbox's own save
            onSave(seg.id, text, null, false);
            setDirty(false);
          }
        }}
      />
      {showSources && (
        <div className="sources">
          <div title="faster-whisper 원문">W: {seg.text_whisper}</div>
          {seg.text_youtube && <div title="유튜브 자동자막">Y: {seg.text_youtube}</div>}
          {seg.text_llm && seg.text_llm !== machineDraft && <div>L: {seg.text_llm}</div>}
        </div>
      )}
      <label className="reviewed-check">
        <input
          type="checkbox"
          checked={seg.reviewed}
          onChange={(e) => onSave(seg.id, text, e.target.checked, false)}
        />
        검수 완료 (Ctrl+Enter = 저장+완료+다음)
      </label>
    </div>
  );
}

export function Editor({ videoId, onBack }: { videoId: string; onBack: () => void }) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState("");
  const { currentTime, seekTo } = usePlayer(videoId);

  useEffect(() => {
    fetchSegments(videoId).then(setSegments).catch((e) => setError(String(e)));
  }, [videoId]);

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

  async function save(id: number, text: string, reviewed: boolean | null, next: boolean) {
    try {
      const body: Parameters<typeof updateSegment>[1] = { text_final: text };
      if (reviewed !== null) body.reviewed = reviewed;
      const updated = await updateSegment(id, body);
      setSegments((prev) => prev.map((s) => (s.id === id ? updated : s)));
      if (next) {
        const i = visible.findIndex((s) => s.id === id);
        const nxt = visible[i + 1];
        if (nxt) {
          seekTo(nxt.start);
          document
            .querySelectorAll<HTMLTextAreaElement>(".row textarea")
            [i + 1]?.focus();
        }
      }
    } catch (e) {
      setError(String(e));
    }
  }

  async function nudge(seg: Segment, field: "start" | "end", delta: number) {
    const v = Math.max(0, (field === "start" ? seg.start : seg.end) + delta);
    const updated = await updateSegment(seg.id, { [field]: v });
    setSegments((prev) => prev.map((s) => (s.id === seg.id ? updated : s)));
  }

  return (
    <div className="editor">
      <div className="left">
        <button className="back" onClick={onBack}>← 목록</button>
        <div id="yt-player" />
        <div className="progress">
          검수 {nReviewed}/{segments.length}
          <progress value={nReviewed} max={segments.length} />
        </div>
        <div className="filters">
          {(["all", "flagged", "unreviewed"] as Filter[]).map((f) => (
            <button
              key={f}
              className={filter === f ? "on" : ""}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? `전체 ${segments.length}` : f === "flagged" ? "우선검토" : "미검수"}
            </button>
          ))}
        </div>
        <a className="export" href={exportUrl(videoId)} download>
          .srt 다운로드
        </a>
        {error && <div className="error">{error}</div>}
      </div>
      <div className="right">
        {visible.map((seg) => (
          <Row
            key={seg.id}
            seg={seg}
            active={seg.id === activeId}
            onSeek={seekTo}
            onSave={save}
            onNudge={nudge}
          />
        ))}
      </div>
    </div>
  );
}
