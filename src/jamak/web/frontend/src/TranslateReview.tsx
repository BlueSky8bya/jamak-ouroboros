import { useEffect, useRef, useState } from "react";
import {
  fetchTranslations,
  makeTranslations,
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
}: {
  row: TranslationRow;
  langLabel: string;
  onSeek: (t: number) => void;
  onSave: (segId: number, text: string, reviewed: boolean | null) => void;
}) {
  const [text, setText] = useState(row.text);
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
    <div className={"trow" + (row.reviewed ? " reviewed" : "") + (row.stale ? " stale" : "")}>
      <button className="time" onClick={() => onSeek(row.start)} title="이 구간 재생">
        ▶ {fmt(row.start)}
      </button>
      <div className="tcol">
        <div className="tko" title="한국어 원문 (확정)">
          <span className="tlabel ko">한국어</span> {row.ko}
        </div>
        {row.stale && (
          <div className="tstale" title="번역을 만든 뒤 한국어 원문이 바뀌었습니다. 다시 번역하거나 확인하세요.">
            ⚠️ 원문이 바뀜 — 재번역/재확인 필요
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
              onSave(row.segment_id, text, true);
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
}: {
  videoId: string;
  lang: string;
  langLabel: string;
  currentTime: number;
  onSeek: (t: number) => void;
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
    } catch (e) {
      setError(String(e));
    } finally {
      setTranslating(false);
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

  return (
    <div className="translate-review">
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
        />
      ))}
    </div>
  );
}
