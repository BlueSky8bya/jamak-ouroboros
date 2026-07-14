import { useEffect, useRef, useState } from "react";
import {
  fetchTranslations,
  makeTranslations,
  replaceText,
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
        {(row.stale || !text.trim()) && (
          <div
            className="tstale"
            title="한국어를 나누거나 고친 뒤 생긴 빈칸·달라진 번역을, 이 자막과 주변의 이어진 문제 자막까지 문맥을 살려 한 번에 다시 번역해요."
          >
            <span>
              {row.stale
                ? "⚠️ 원문이 바뀜 — 주변 문맥까지 살려 다시 번역할 수 있어요"
                : "⚠️ 번역이 비어 있어요 — 주변 문맥으로 채울 수 있어요"}
            </span>
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
  // 배치 루프 진행 상황 — 동적 진행바 렌더용 (숫자 문자열 아님)
  const [tprog, setTprog] = useState<{ done: number; total: number } | null>(null);
  const [error, setError] = useState("");
  // 번역 텍스트 찾기·바꾸기 (ko 트랙의 Alt+B와 동일 UX)
  const [findOpen, setFindOpen] = useState(false);
  const [findText, setFindText] = useState("");
  const [replText, setReplText] = useState("");
  const [findMatches, setFindMatches] = useState<number | null>(null);
  const [notice, setNotice] = useState(""); // 일괄 작업 성공을 한 줄로 명시
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
    setTprog(null);
    try {
      // 60 cues per request = one model call — a 2h video as ONE request blows
      // past the proxy timeout (502) with nothing saved. Each batch commits,
      // so an interruption keeps all finished batches.
      let guard = 0;
      for (;;) {
        const r = await makeTranslations(videoId, lang, 60);
        setTprog({ done: r.translated, total: r.segments });
        if (r.done) break;
        if (++guard > 300) throw new Error("번역 반복 한도 초과 — 다시 시도해주세요");
      }
      await load();
      onGenerated?.();
    } catch (e) {
      setError(String(e));
      await load(); // partial batches are already saved — show them
    } finally {
      setTranslating(false);
      setTprog(null);
    }
  }

  // 찾기 미리보기: 입력 멈추면 전체 번역에서 몇 곳인지 (서버 count, 무과금)
  useEffect(() => {
    if (!findOpen || !findText.trim()) {
      setFindMatches(null);
      return;
    }
    const t = window.setTimeout(() => {
      replaceText(videoId, findText, "", false, lang)
        .then((r) => setFindMatches(r.matches))
        .catch(() => setFindMatches(null));
    }, 300);
    return () => window.clearTimeout(t);
  }, [findText, findOpen, videoId, lang]);

  async function applyReplace() {
    if (!findText.trim()) return;
    try {
      const r = await replaceText(videoId, findText, replText, true, lang);
      setFindMatches(null);
      setFindText("");
      setReplText("");
      setFindOpen(false);
      await load();
      onGenerated?.();
      // 결과는 상단에 한 줄로 (성공 인지)
      setNotice(`🔎 ${r.segments}개 자막에서 ${r.matches}곳 바꿨어요`);
      window.setTimeout(() => setNotice(""), 4000);
    } catch (e) {
      setError(String(e));
    }
  }

  async function retranslate(segId: number) {
    setError("");
    try {
      const r = await retranslateSegment(videoId, lang, segId);
      // the server may have re-translated a cluster (clicked cue + contiguous
      // stale/empty neighbours) — patch every returned row
      const byId = new Map(r.updated.map((u) => [u.segment_id, u]));
      setRows((prev) =>
        prev.map((row) => {
          const u = byId.get(row.segment_id);
          return u
            ? { ...row, text: u.text, reviewed: u.reviewed, stale: u.stale, has_translation: true }
            : row;
        }),
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
          {translating ? "번역 만드는 중..." : `${langLabel} 번역 만들기`}
        </button>
        {translating && (
          <div className="tprogress" role="status" aria-live="polite">
            <div className="tprog-top">
              <span className="busy-spin" aria-hidden />
              <span>
                {tprog
                  ? `번역 진행 중 — 남은 ${Math.max(0, tprog.total - tprog.done)}개`
                  : "번역 시작하는 중..."}
              </span>
              {tprog && (
                <strong>{Math.round((tprog.done / Math.max(1, tprog.total)) * 100)}%</strong>
              )}
            </div>
            <div className="tprog-bar">
              <span
                style={{
                  width: tprog
                    ? `${(tprog.done / Math.max(1, tprog.total)) * 100}%`
                    : "4%",
                }}
              />
            </div>
            {tprog && (
              <div className="tprog-nums">
                {tprog.done.toLocaleString()} / {tprog.total.toLocaleString()}
              </div>
            )}
          </div>
        )}
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
        {(() => {
          // .srt 구조 교체 후 산발적으로 비거나(stale 포함) 남는 셀 — 한 번에.
          // 서버 배치 번역이 원래 '빈 곳·바뀐 곳만' 골라 과금하므로 그대로 재사용.
          // 사람이 직접 고친(edited) 번역은 서버가 보호(자동 덮어쓰기 금지)라
          // 카운트에서 제외 — 안 그러면 눌러도 숫자가 안 줄어 혼란.
          const missing = rows.filter(
            (r) => !r.text.trim() || (r.stale && !r.edited),
          ).length;
          if (missing === 0) return null;
          return (
            <div className="tmissing">
              <span>
                ⚠ 번역이 비었거나 원문이 바뀐 자막 <strong>{missing}개</strong>
              </span>
              <button className="tmissing-btn" disabled={translating} onClick={generate}>
                {translating ? "번역 중..." : `🔄 한 번에 다 채우기 (${missing}개만 과금)`}
              </button>
            </div>
          );
        })()}
        {translating && (
          <div className="tprogress" role="status" aria-live="polite">
            <div className="tprog-top">
              <span className="busy-spin" aria-hidden />
              <span>
                {tprog
                  ? `번역 진행 중 — 남은 ${Math.max(0, tprog.total - tprog.done)}개`
                  : "번역 시작하는 중..."}
              </span>
              {tprog && (
                <strong>{Math.round((tprog.done / Math.max(1, tprog.total)) * 100)}%</strong>
              )}
            </div>
            <div className="tprog-bar">
              <span
                style={{
                  width: tprog
                    ? `${(tprog.done / Math.max(1, tprog.total)) * 100}%`
                    : "4%",
                }}
              />
            </div>
            {tprog && (
              <div className="tprog-nums">
                {tprog.done.toLocaleString()} / {tprog.total.toLocaleString()}
              </div>
            )}
          </div>
        )}
        {notice && <div className="tnotice">{notice}</div>}
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
        <button
          className="mini"
          onClick={() => setFindOpen((v) => !v)}
          title="같은 번역 실수를 전체에서 한 번에 교정"
        >
          🔎 찾기·바꾸기
        </button>
        <button className="mini" disabled={translating} onClick={generate} title="확인 안 한 자막만 새로 번역">
          {translating ? "번역 중..." : "미검수 다시 번역"}
        </button>
      </div>
      {findOpen && (
        <div className="findbar open tfind">
          <input
            className="find-in"
            placeholder={`찾을 ${langLabel} 내용`}
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
          <button className="find-apply" disabled={!findMatches} onClick={() => void applyReplace()}>
            모두 바꾸기
          </button>
          <button className="find-close" title="닫기 (Esc)" onClick={() => setFindOpen(false)}>
            ✕
          </button>
        </div>
      )}
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
