import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { createJob, exportUrl, fetchJobs, retranscribe } from "./api";
import { Editor } from "./Editor";
import { ThemeToggle } from "./theme";
import type { JobSummary } from "./types";

type SortField = "uploaded" | "added" | "title" | "progress" | "timing" | "duration";
const SORT_LABEL: Record<SortField, string> = {
  uploaded: "유튜브 업로드일",
  added: "추가한 날짜",
  progress: "텍스트 검수율",
  timing: "타이밍 완료",
  duration: "영상 길이",
  title: "제목",
};

type StatusKey = "all" | "text" | "timing" | "translate" | "done" | "running";
const STATUS_FILTERS: { key: StatusKey; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "text", label: "텍스트 검수 중" },
  { key: "timing", label: "타이밍 필요" },
  { key: "translate", label: "번역 중" },
  { key: "done", label: "완료" },
  { key: "running", label: "처리 중" },
];

/** pull the 11-char YouTube id out of a pasted URL (or a bare id) */
function parseVideoId(u: string): string | null {
  const s = u.trim();
  const m = s.match(/(?:v=|youtu\.be\/|embed\/|shorts\/|\/v\/)([\w-]{11})/);
  if (m) return m[1];
  return /^[\w-]{11}$/.test(s) ? s : null;
}

/** "오늘 / 어제 / N일 전 / N달 전" from an ISO timestamp */
function relTime(iso: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const d = (Date.now() - t) / 86_400_000;
  if (d < 1) return "오늘";
  if (d < 2) return "어제";
  if (d < 30) return `${Math.floor(d)}일 전`;
  if (d < 365) return `${Math.floor(d / 30)}달 전`;
  return `${Math.floor(d / 365)}년 전`;
}

/** highlight the searched substring inside a title */
function highlight(text: string, q: string) {
  const query = q.trim();
  if (!query) return text;
  const i = text.toLowerCase().indexOf(query.toLowerCase());
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <mark>{text.slice(i, i + query.length)}</mark>
      {text.slice(i + query.length)}
    </>
  );
}

/** overall completion donut */
function Ring({ pct }: { pct: number }) {
  const r = 17;
  const c = 2 * Math.PI * r;
  return (
    <svg className="ring" viewBox="0 0 44 44" width="46" height="46" aria-hidden>
      <circle className="ring-bg" cx="22" cy="22" r={r} />
      <circle
        className="ring-fg"
        cx="22"
        cy="22"
        r={r}
        strokeDasharray={`${(c * pct) / 100} ${c}`}
        transform="rotate(-90 22 22)"
      />
      <text className="ring-label" x="22" y="23">
        {pct}%
      </text>
    </svg>
  );
}

const SHORTCUTS: { k: string; d: string }[] = [
  { k: "/", d: "제목 검색으로 이동" },
  { k: "N", d: "새 링크 입력칸으로 이동" },
  { k: "Esc", d: "검색어 지우기" },
  { k: "?", d: "이 도움말 열기/닫기" },
];

type Tone = "muted" | "progress" | "warn" | "done" | "live";

/** the one clear status chip for a card, for the selected language track */
function stageFor(j: JobSummary, lang: string): { label: string; tone: Tone; icon?: string } {
  if (j.running) return { label: "처리 중", tone: "live" };
  if (lang === "ko") {
    if (j.segments === 0) return { label: "대기 중", tone: "muted" };
    if (!j.ko_complete) return { label: `텍스트 ${j.reviewed}/${j.segments}`, tone: "progress" };
    if (!j.timing_done) return { label: "타이밍 조정 필요", tone: "warn", icon: "⏱" };
    return { label: "완료", tone: "done", icon: "✓" };
  }
  const l = j.languages.find((x) => x.code === lang);
  if (!l || l.translated === 0) return { label: "번역 전", tone: "muted" };
  if (l.complete) return { label: "완료", tone: "done", icon: "✓" };
  if (l.reviewed > 0) return { label: `번역 검수 ${l.reviewed}/${j.segments}`, tone: "progress" };
  return { label: `번역됨 · 검수 전`, tone: "muted" };
}

function JobCard({
  job: j,
  query,
  isCursor,
  dataIdx,
  onOpen,
  onReroll,
  onExport,
  onCopyLink,
}: {
  job: JobSummary;
  query: string;
  isCursor: boolean;
  dataIdx: number;
  onOpen: (videoId: string) => void;
  onReroll: (e: ReactMouseEvent, j: JobSummary) => void;
  onExport: (e: ReactMouseEvent, j: JobSummary) => void;
  onCopyLink: (e: ReactMouseEvent, j: JobSummary) => void;
}) {
  const [lang, setLang] = useState("ko");
  const openable = j.segments > 0;
  const stage = stageFor(j, lang);
  const koPct = j.segments ? Math.round((j.reviewed / j.segments) * 100) : 0;
  const selPct =
    lang === "ko"
      ? koPct
      : (() => {
          const l = j.languages.find((x) => x.code === lang);
          return l && j.segments ? Math.round((l.reviewed / j.segments) * 100) : 0;
        })();
  const langOpts = [
    { code: "ko", label: "한국어", done: j.ko_complete && j.timing_done },
    ...j.languages.map((l) => ({ code: l.code, label: l.label, done: l.complete })),
  ];

  return (
    <div
      data-idx={dataIdx}
      className={
        "job-card" +
        (j.running ? " running" : "") +
        (openable ? "" : " disabled") +
        (isCursor ? " cursor" : "")
      }
      role="button"
      tabIndex={openable ? 0 : -1}
      onClick={() => openable && onOpen(j.video_id)}
      onKeyDown={(e) => {
        if (openable && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onOpen(j.video_id);
        }
      }}
      title={openable ? "검수 열기" : "파이프라인 처리 중"}
    >
      <span className="thumb">
        <img
          src={`https://img.youtube.com/vi/${j.video_id}/mqdefault.jpg`}
          alt=""
          loading="lazy"
          onError={(e) => e.currentTarget.classList.add("broken")}
        />
        {j.running && <span className="thumb-scan" />}
        {j.duration_seconds > 0 && (
          <span className="thumb-dur">{Math.round(j.duration_seconds / 60)}분</span>
        )}
        {j.ko_complete && j.timing_done && <span className="thumb-done">✓ 완료</span>}
        {openable && !j.ko_complete && (
          <span className="thumb-prog">
            <span style={{ width: `${koPct}%` }} />
          </span>
        )}
        {openable && (
          <span className="quick-actions">
            {j.ko_complete && (
              <span
                className="qa"
                role="button"
                tabIndex={0}
                title=".srt 자막 바로 내려받기"
                onClick={(e) => onExport(e, j)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onExport(e as unknown as ReactMouseEvent, j);
                }}
              >
                ⬇ .srt
              </span>
            )}
            <span
              className="qa"
              role="button"
              tabIndex={0}
              title="유튜브 링크 복사"
              onClick={(e) => onCopyLink(e, j)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onCopyLink(e as unknown as ReactMouseEvent, j);
              }}
            >
              🔗 링크
            </span>
          </span>
        )}
      </span>
      <div className="job-info">
        <div className="job-head">
          <span className={"stage " + stage.tone}>
            {j.running && <span className="spinner" />}
            {stage.icon && <span className="stage-ic">{stage.icon}</span>}
            {stage.label}
          </span>
          {langOpts.length > 1 && (
            <select
              className="card-lang"
              value={lang}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setLang(e.target.value)}
              title="언어별 진행 상태 보기"
            >
              {langOpts.map((o) => (
                <option key={o.code} value={o.code}>
                  {o.label}
                  {o.done ? " ✓" : ""}
                </option>
              ))}
            </select>
          )}
        </div>
        <strong>{highlight(j.title || j.video_id, query)}</strong>
        {openable && (
          <>
            <span
              className={"job-progress" + (stage.tone === "done" ? " done" : "")}
              aria-label={`진행률 ${selPct}%`}
            >
              <span style={{ width: `${selPct}%` }} />
            </span>
            <div className="job-foot">
              <span className="meta">
                자막 {j.segments}개
                {j.upload_date
                  ? ` · 업로드 ${j.upload_date.slice(0, 4)}.${j.upload_date.slice(4, 6)}.${j.upload_date.slice(6, 8)}`
                  : j.created_at
                    ? ` · ${relTime(j.created_at)} 추가`
                    : ""}
              </span>
              {!j.ko_complete && !j.running && (
                <span
                  className="reroll"
                  role="button"
                  tabIndex={0}
                  title="현재 용어사전으로 음성인식 다시 시도 (리세마라). 용어가 많을수록 인식이 좋아집니다."
                  onClick={(e) => onReroll(e, j)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onReroll(e as unknown as ReactMouseEvent, j);
                  }}
                >
                  🎲 다시 인식
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // remembered view preferences (less re-setup between visits)
  const [filter, setFilter] = useState(() => localStorage.getItem("jamak.filter") || "all");
  const [status, setStatus] = useState<StatusKey>(
    () => (localStorage.getItem("jamak.status") as StatusKey) || "all",
  );
  const [sort, setSort] = useState<SortField>(() => {
    const s = localStorage.getItem("jamak.sort");
    return s && s in SORT_LABEL ? (s as SortField) : "uploaded";
  });
  const [dir, setDir] = useState<"asc" | "desc">(
    () => (localStorage.getItem("jamak.dir") === "asc" ? "asc" : "desc"),
  );
  const [view, setView] = useState<"grid" | "list">(
    () => (localStorage.getItem("jamak.view") === "list" ? "list" : "grid"),
  );
  const [query, setQuery] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [cursor, setCursor] = useState(-1); // keyboard-selected card index
  const timer = useRef<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const urlRef = useRef<HTMLInputElement>(null);
  const visibleRef = useRef<JobSummary[]>([]);
  const cursorRef = useRef(-1);
  cursorRef.current = cursor;

  useEffect(() => localStorage.setItem("jamak.filter", filter), [filter]);
  useEffect(() => localStorage.setItem("jamak.status", status), [status]);
  useEffect(() => localStorage.setItem("jamak.sort", sort), [sort]);
  useEffect(() => localStorage.setItem("jamak.dir", dir), [dir]);
  useEffect(() => localStorage.setItem("jamak.view", view), [view]);

  async function refresh() {
    try {
      const list = await fetchJobs();
      setJobs(list);
      setLoaded(true);
      const anyRunning = list.some((j) => j.running);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(refresh, anyRunning ? 3000 : 30000);
    } catch (e) {
      setError(String(e));
      setLoaded(true);
    }
  }

  useEffect(() => {
    if (selected === null) refresh();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  // keyboard: "/" search, "n" url box, "?" help — all skip while typing.
  // Only bound on the workbench: never let these leak into the editor.
  useEffect(() => {
    if (selected) return;
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      const typing =
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing) {
        if (e.key === "Escape") (el as HTMLElement).blur();
        return;
      }
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault();
        urlRef.current?.focus();
      } else if (e.key === "?") {
        e.preventDefault();
        setShowHelp((v) => !v);
      } else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
        const n = visibleRef.current.length;
        if (!n) return;
        e.preventDefault();
        const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1;
        setCursor((c) => {
          const base = c < 0 ? (step > 0 ? -1 : 0) : c;
          return Math.max(0, Math.min(n - 1, base + step));
        });
      } else if (e.key === "Enter") {
        const j = visibleRef.current[cursorRef.current];
        if (j && j.segments > 0) setSelected(j.video_id);
      } else if (e.key === "Escape") {
        setShowHelp(false);
        setCursor(-1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  // paste a YouTube link anywhere on the page → drop it in the create box
  useEffect(() => {
    if (selected) return;
    function onPaste(e: ClipboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      const text = e.clipboardData?.getData("text") ?? "";
      if (parseVideoId(text)) {
        setUrl(text.trim());
        urlRef.current?.focus();
      }
    }
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  async function submit() {
    if (!url.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await createJob(url.trim());
      setUrl("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  async function reroll(e: ReactMouseEvent, j: JobSummary) {
    e.stopPropagation();
    const msg =
      j.reviewed > 0
        ? `검수 중인 편집 ${j.reviewed}개가 초기화됩니다. 현재 용어사전으로 음성인식을 다시 할까요?`
        : "현재 용어사전으로 음성인식을 다시 시도할까요?";
    if (!window.confirm(msg)) return;
    setError("");
    try {
      await retranscribe(j.video_id);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  function exportSrt(e: ReactMouseEvent, j: JobSummary) {
    e.stopPropagation();
    const a = document.createElement("a");
    a.href = exportUrl(j.video_id, "best", "ko");
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function copyLink(e: ReactMouseEvent, j: JobSummary) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(`https://www.youtube.com/watch?v=${j.video_id}`);
      setError("");
    } catch {
      /* clipboard blocked — no-op */
    }
  }

  const allLangs = useMemo(() => {
    const map = new Map<string, string>();
    for (const j of jobs) for (const l of j.languages) map.set(l.code, l.label);
    return [...map.entries()].map(([code, label]) => ({ code, label }));
  }, [jobs]);

  const visible = useMemo(() => {
    let list = jobs.slice();
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((j) => (j.title || j.video_id).toLowerCase().includes(q));
    if (status === "text")
      list = list.filter((j) => j.segments > 0 && !j.ko_complete && !j.running);
    else if (status === "timing")
      list = list.filter((j) => j.ko_complete && !j.timing_done && !j.running);
    else if (status === "translate")
      list = list.filter(
        (j) => j.ko_complete && j.languages.length > 0 && j.languages.some((l) => !l.complete),
      );
    else if (status === "done") list = list.filter((j) => j.ko_complete && j.timing_done);
    else if (status === "running") list = list.filter((j) => j.running);
    if (filter === "ko") list = list.filter((j) => j.ko_complete);
    else if (filter !== "all")
      list = list.filter((j) => j.languages.some((l) => l.code === filter && l.complete));
    list.sort((a, b) => {
      let cmp = 0;
      if (sort === "title") {
        cmp = (a.title || a.video_id).localeCompare(b.title || b.video_id, "ko");
      } else if (sort === "progress") {
        const pa = a.segments ? a.reviewed / a.segments : 0;
        const pb = b.segments ? b.reviewed / b.segments : 0;
        cmp = pa - pb;
      } else if (sort === "timing") {
        cmp = (a.timing_done ? 1 : 0) - (b.timing_done ? 1 : 0);
      } else if (sort === "duration") {
        cmp = (a.duration_seconds || 0) - (b.duration_seconds || 0);
      } else if (sort === "uploaded") {
        const ua = a.upload_date || "0";
        const ub = b.upload_date || "0";
        cmp = ua !== ub ? ua.localeCompare(ub) : (a.created_at || "").localeCompare(b.created_at || "");
      } else {
        cmp = (a.created_at || "").localeCompare(b.created_at || "");
      }
      return dir === "desc" ? -cmp : cmp;
    });
    return list;
  }, [jobs, filter, status, sort, dir, query]);

  const resume = useMemo(() => {
    const wip = jobs.filter((j) => j.segments > 0 && !j.ko_complete && !j.running);
    if (!wip.length) return null;
    return wip.slice().sort((a, b) => {
      const pa = a.reviewed / a.segments;
      const pb = b.reviewed / b.segments;
      if (pb !== pa) return pb - pa;
      return (b.created_at || "").localeCompare(a.created_at || "");
    })[0];
  }, [jobs]);

  // keep the keyboard handler's view of the list current; keep cursor in range
  useEffect(() => {
    visibleRef.current = visible;
    if (cursor >= visible.length) setCursor(visible.length ? visible.length - 1 : -1);
  }, [visible, cursor]);

  // bring the keyboard-selected card into view
  useEffect(() => {
    if (cursor < 0) return;
    document.querySelector(`.job-card[data-idx="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  // ambient progress in the browser tab title
  useEffect(() => {
    const rem = jobs.reduce((a, j) => a + Math.max(0, j.segments - j.reviewed), 0);
    document.title = rem > 0 ? `작업대 · 남은 ${rem}` : "자막 검수 작업대";
  }, [jobs]);

  if (selected)
    return (
      <Editor
        videoId={selected}
        onBack={() => setSelected(null)}
        timingDone={jobs.find((j) => j.video_id === selected)?.timing_done ?? false}
      />
    );

  const runningCount = jobs.filter((j) => j.running).length;
  const koDoneCount = jobs.filter((j) => j.ko_complete).length;
  const timingDoneCount = jobs.filter((j) => j.timing_done).length;
  const transTracksDone = jobs.reduce(
    (a, j) => a + j.languages.filter((l) => l.complete).length,
    0,
  );
  const totalSegments = jobs.reduce((a, j) => a + j.segments, 0);
  const totalReviewed = jobs.reduce((a, j) => a + j.reviewed, 0);
  const totalRemaining = Math.max(0, totalSegments - totalReviewed);
  const overallPct = totalSegments ? Math.round((totalReviewed / totalSegments) * 100) : 0;
  const resumePct = resume ? Math.round((resume.reviewed / resume.segments) * 100) : 0;
  const previewId = parseVideoId(url);
  const filtersActive = status !== "all" || filter !== "all" || query.trim() !== "";

  function resetFilters() {
    setStatus("all");
    setFilter("all");
    setQuery("");
  }

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="header-top">
          <span className="product-label">Jamak Ouroboros</span>
          <div className="header-actions">
            <button className="help-btn" title="단축키 (?)" onClick={() => setShowHelp((v) => !v)}>
              ?
            </button>
            <ThemeToggle />
          </div>
        </div>
        <h1>자막 검수 작업대</h1>
        <p>유튜브 강연 자막을 만들고, 검수하고, 고친 내용을 다음 작업에 되먹임합니다.</p>
      </header>

      {showHelp && (
        <div className="help-popover" onClick={() => setShowHelp(false)}>
          <div className="help-card" onClick={(e) => e.stopPropagation()}>
            <div className="help-head">
              <strong>단축키</strong>
              <button onClick={() => setShowHelp(false)}>✕</button>
            </div>
            {SHORTCUTS.map((s) => (
              <div className="help-row" key={s.k}>
                <kbd>{s.k}</kbd>
                <span>{s.d}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="url-box">
        <input
          ref={urlRef}
          type="text"
          placeholder="https://youtube.com/watch?v=... 강연 영상 링크 붙여넣기  (N)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit} disabled={submitting || !url.trim()}>
          {submitting ? "시작 중" : "자막 만들기"}
        </button>
        {previewId && (
          <div className="url-preview">
            <img
              src={`https://img.youtube.com/vi/${previewId}/mqdefault.jpg`}
              alt=""
              loading="lazy"
            />
            <span>이 영상으로 자막을 만듭니다 · Enter</span>
          </div>
        )}
      </div>
      {error && <div className="error">{error}</div>}

      {resume && (
        <button className="resume-hero" onClick={() => setSelected(resume.video_id)}>
          <span className="resume-thumb">
            <img
              src={`https://img.youtube.com/vi/${resume.video_id}/mqdefault.jpg`}
              alt=""
              loading="lazy"
            />
          </span>
          <span className="resume-body">
            <span className="resume-kicker">이어서 검수</span>
            <strong className="resume-title">{resume.title || resume.video_id}</strong>
            <span className="resume-bar">
              <span style={{ width: `${resumePct}%` }} />
            </span>
            <span className="resume-meta">
              {resume.reviewed}/{resume.segments} · {resumePct}% · 남은{" "}
              {Math.max(0, resume.segments - resume.reviewed)}개
            </span>
          </span>
          <span className="resume-cta">이어서 →</span>
        </button>
      )}

      <div className="workbench-stats">
        <div className="ws-ring">
          <Ring pct={overallPct} />
          <span>전체 검수</span>
        </div>
        <div className="ws-nums">
          <div className="wstat">
            <strong>{jobs.length}</strong>
            <span>영상</span>
          </div>
          <div className="wstat ok">
            <strong>{koDoneCount}</strong>
            <span>텍스트 완료</span>
          </div>
          <div className="wstat ok">
            <strong>{timingDoneCount}</strong>
            <span>타이밍 완료</span>
          </div>
          <div className="wstat ok">
            <strong>{transTracksDone}</strong>
            <span>번역 완료</span>
          </div>
          <div className="wstat">
            <strong>{totalReviewed.toLocaleString()}</strong>
            <span>검수한 자막</span>
          </div>
          <div className="wstat warn">
            <strong>{totalRemaining.toLocaleString()}</strong>
            <span>남은 자막</span>
          </div>
          {runningCount > 0 && (
            <div className="wstat live">
              <strong>{runningCount}</strong>
              <span>처리 중</span>
            </div>
          )}
        </div>
      </div>

      <div className="wb-controls">
      <div className="status-pills">
        {STATUS_FILTERS.map((s) => {
          const count =
            s.key === "all"
              ? jobs.length
              : s.key === "text"
                ? jobs.filter((j) => j.segments > 0 && !j.ko_complete && !j.running).length
                : s.key === "timing"
                  ? jobs.filter((j) => j.ko_complete && !j.timing_done && !j.running).length
                  : s.key === "translate"
                    ? jobs.filter(
                        (j) =>
                          j.ko_complete &&
                          j.languages.length > 0 &&
                          j.languages.some((l) => !l.complete),
                      ).length
                    : s.key === "done"
                      ? jobs.filter((j) => j.ko_complete && j.timing_done).length
                      : runningCount;
          return (
            <button
              key={s.key}
              className={"pill" + (status === s.key ? " on" : "")}
              onClick={() => setStatus(s.key)}
            >
              {s.label}
              <em>{count}</em>
            </button>
          );
        })}
      </div>

      <div className="filter-bar">
        <input
          ref={searchRef}
          className="search"
          type="search"
          placeholder="🔍 제목으로 검색  ( / )"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setQuery("");
              (e.target as HTMLInputElement).blur();
            }
          }}
        />
        {allLangs.length > 0 && (
          <label>
            번역
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">전체</option>
              <option value="ko">한국어 완료</option>
              {allLangs.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label} 완료
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          정렬
          <select value={sort} onChange={(e) => setSort(e.target.value as SortField)}>
            {(Object.keys(SORT_LABEL) as SortField[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <button
          className="dir-toggle"
          onClick={() => setDir((d) => (d === "desc" ? "asc" : "desc"))}
          title={dir === "desc" ? "내림차순 (큰 값·최신·높은 진행률 먼저)" : "오름차순 (작은 값·오래된·낮은 진행률 먼저)"}
        >
          {dir === "desc" ? "↓ 내림차순" : "↑ 오름차순"}
        </button>
        <div className="view-toggle" role="group" aria-label="보기 전환">
          <button
            className={view === "grid" ? "on" : ""}
            title="카드 보기"
            onClick={() => setView("grid")}
          >
            ▦
          </button>
          <button
            className={view === "list" ? "on" : ""}
            title="목록 보기"
            onClick={() => setView("list")}
          >
            ☰
          </button>
        </div>
        {filtersActive && (
          <button className="reset-chip" onClick={resetFilters} title="필터·검색 초기화">
            초기화 ✕
          </button>
        )}
        <span className="filter-count">{visible.length}개</span>
      </div>
      </div>

      <div className={"job-grid " + view}>
        {!loaded &&
          Array.from({ length: 4 }).map((_, i) => <div className="job-card skeleton" key={i} />)}
        {loaded &&
          visible.map((j, idx) => (
            <JobCard
              key={j.video_id}
              job={j}
              query={query}
              isCursor={idx === cursor}
              dataIdx={idx}
              onOpen={setSelected}
              onReroll={reroll}
              onExport={exportSrt}
              onCopyLink={copyLink}
            />
          ))}
        {loaded && visible.length === 0 && !error && (
          <div className="empty">
            {jobs.length === 0 ? (
              <>
                <strong>아직 작업이 없어요</strong>
                <span>위에 유튜브 강연 링크를 붙여넣으면 자막 초안이 만들어집니다.</span>
              </>
            ) : (
              <>
                <strong>이 조건에 맞는 영상이 없어요</strong>
                <button className="reset-chip" onClick={resetFilters}>
                  필터 초기화
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
