import { useEffect, useRef, useState } from "react";
import {
  fetchTranslations,
  makeTranslations,
  retranslateSegment,
  updateTranslation,
  type TranslationRow,
} from "./api";

function fmt(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

function Row({
  row,
  langLabel,
  onSeek,
  onSave,
  onSaveNext,
  onRetranslate,
}: {
  row: TranslationRow;
  langLabel: string;
  onSeek: (t: number) => void;
  onSave: (segId: number, text: string, reviewed: boolean | null) => void;
  onSaveNext: (segId: number, text: string) => void;
  onRetranslate: (segId: number) => Promise<void>;
}) {
  const [text, setText] = useState(row.text);
  const [retranslating, setRetranslating] = useState(false);
  const dirty = useRef(false);
  const textRef = useRef(text);
  textRef.current = text;

  useEffect(() => {
    setText(row.text);
    dirty.current = false;
  }, [row.segment_id, row.text]);

  function flush() {
    if (dirty.current) {
      dirty.current = false;
      onSave(row.segment_id, textRef.current, null);
    }
  }

  return (
    <div
      data-seg={row.segment_id}
      className={"trow" + (row.reviewed ? " reviewed" : "") + (row.stale ? " stale" : "")}
    >
      <button className="time" onClick={() => onSeek(row.start)} title="이 구간 재생">
        ▶ {fmt(row.start)}
      </button>
      <div className="tcol">
        <div className="tko" title="한국어 원문 (확정)">
          <span className="tlabel ko">한국어</span> {row.ko}
        </div>
        {row.stale && (
          <div className="tstale" title="번역을 만든 뒤 한국어 원문이 바뀌었습니다. 바뀐 원문에 맞춰 이 자막만 다시 번역할 수 있어요.">
            <span>⚠️ 원문이 바뀜 — 이 자막만 다시 번역할 수 있어요</span>
            <button
              className="tretranslate"
              disabled={retranslating}
              onClick={async () => {
                setRetranslating(true);
                try {
                  await onRetranslate(row.segment_id);
                } finally {
                  setRetranslating(false);
                }
              }}
            >
              {retranslating ? "번역 중…" : "🔄 다시 번역"}
            </button>
          </div>
        )}
        <textarea
          className="ttext"
          value={text}
          rows={Math.max(2, Math.ceil((text.length || 1) / 40))}
          placeholder={`${langLabel} 번역`}
          onChange={(e) => {
            setText(e.target.value);
            dirty.current = true;
          }}
          onBlur={flush}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing) return;
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              dirty.current = false;
              onSaveNext(row.segment_id, text); // 확인 + 다음 미검수로 이동
            }
          }}
        />
        <label className="reviewed-check">
          <input
            type="checkbox"
            checked={row.reviewed}
            onChange={(e) => onSave(row.segment_id, text, e.target.checked)}
          />
          번역 확인 완료 (Enter = 확인+다음)
        </label>
      </div>
    </div>
  );
}

export function TranslateReview({
  videoId,
  lang,
  langLabel,
  currentTime,
  onSeek,
  onGenerated,
}: {
  videoId: string;
  lang: string;
  langLabel: string;
  currentTime: number;
  onSeek: (t: number) => void;
  // notify parent that translations now exist for this lang, so it can refetch
  // its own transMap (which gates the fork button / on-video overlay)
  onGenerated?: () => void;
}) {
  const [rows, setRows] = useState<TranslationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [translating, setTranslating] = useState(false);
  const [error, setError] = useState("");
  const seekTo = onSeek;

  async function load() {
    setLoading(true);
    try {
      setRows(await fetchTranslations(videoId, lang));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId, lang]);

  const hasAny = rows.some((r) => r.has_translation);
  const nReviewed = rows.filter((r) => r.reviewed).length;
  const activeId = rows.find((r) => currentTime >= r.start && currentTime < r.end)?.segment_id;

  async function generate() {
    setTranslating(true);
    setError("");
    try {
      await makeTranslations(videoId, lang);
      await load();
      onGenerated?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setTranslating(false);
    }
  }

  async function retranslate(segId: number) {
    setError("");
    try {
      const r = await retranslateSegment(videoId, lang, segId);
      setRows((prev) =>
        prev.map((row) =>
          row.segment_id === segId
            ? { ...row, text: r.text, reviewed: r.reviewed, stale: r.stale, has_translation: true }
            : row,
        ),
      );
      onGenerated?.();
    } catch (e) {
      setError(String(e));
    }
  }

  async function save(segId: number, text: string, reviewed: boolean | null) {
    try {
      const body: { text?: string; reviewed?: boolean } = { text };
      if (reviewed !== null) body.reviewed = reviewed;
      const updated = await updateTranslation(segId, lang, body);
      setRows((prev) =>
        prev.map((r) =>
          r.segment_id === segId
            ? { ...r, text: updated.text, reviewed: updated.reviewed, has_translation: true }
            : r,
        ),
      );
      if (updated.text.trim()) onGenerated?.();
    } catch (e) {
      setError(String(e));
    }
  }

  if (loading) return <div className="tinfo">불러오는 중...</div>;

  if (!hasAny) {
    return (
      <div className="tempty">
        <p>
          <strong>{langLabel}</strong> 번역이 아직 없습니다. 한국어 원문을 문맥에 맞게 번역합니다.
        </p>
        <button className="export" disabled={translating} onClick={generate}>
          {translating ? "번역 만드는 중... (1~2분)" : `${langLabel} 번역 만들기`}
        </button>
        {error && <div className="error">{error}</div>}
      </div>
    );
  }

  const pct = rows.length ? Math.round((nReviewed / rows.length) * 100) : 0;
  const remaining = rows.length - nReviewed;

  function continueToNext(fromSegId?: number) {
    // find the next unreviewed row AFTER the given one (rows state may not yet
    // reflect the just-saved reviewed flip, so exclude fromSegId explicitly)
    const start = fromSegId != null ? rows.findIndex((r) => r.segment_id === fromSegId) + 1 : 0;
    const next =
      rows.slice(start).find((r) => !r.reviewed && r.segment_id !== fromSegId) ||
      rows.find((r) => !r.reviewed && r.segment_id !== fromSegId);
    if (!next) return;
    seekTo(next.start);
    const el = document.querySelector<HTMLElement>(`.trow[data-seg="${next.segment_id}"]`);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.querySelector("textarea")?.focus();
  }

  function saveNext(segId: number, text: string) {
    void save(segId, text, true);
    continueToNext(segId);
  }

  return (
    <div className="translate-review">
      {/* per-language progress hero — same momentum system the Korean track
          gets: a progress bar, remaining count, and a continue affordance, so
          a (often large) translation review isn't a pacing-blind slog */}
      <div className="tflow-hero">
        <div className="tflow-top">
          <strong>
            {langLabel} 번역 검수 {nReviewed}/{rows.length}
          </strong>
          <span className="tflow-pct">{pct}%</span>
        </div>
        <div className="tflow-bar">
          <span style={{ width: `${pct}%` }} />
        </div>
        {remaining > 0 ? (
          <button className="continue-btn" onClick={() => continueToNext()}>
            이어서 작업하기 · 남은 {remaining}개 →
          </button>
        ) : (
          <div className="tflow-done">✓ {langLabel} 번역 검수 완료</div>
        )}
      </div>
      <div className="treview-head">
        <span>
          {langLabel} 번역 검수 {nReviewed}/{rows.length}
        </span>
        <button className="mini" disabled={translating} onClick={generate} title="확인 안 한 자막만 새로 번역">
          {translating ? "번역 중..." : "미검수 다시 번역"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      {rows.map((r) => (
        <Row
          key={r.segment_id}
          row={{ ...r, ["_active" as never]: r.segment_id === activeId } as TranslationRow}
          langLabel={langLabel}
          onSeek={seekTo}
          onSave={save}
          onSaveNext={saveNext}
          onRetranslate={retranslate}
        />
      ))}
    </div>
  );
}
