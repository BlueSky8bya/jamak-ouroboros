import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  cancelRequest,
  createJob,
  exportUrl,
  fetchJobs,
  fetchMe,
  fetchQueue,
  fetchVersion,
  importSrt,
  logout,
  retranscribe,
  setAssignee,
  undoSrt,
  type Me,
  type QueueItem,
  type SrtPreview,
} from "./api";
import { Login } from "./Login";
import { Dropdown } from "./Dropdown";
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

const SHORT_MAX = 60; // <= this many seconds counts as a Short

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
/** Three overlaid progress rings: text review, timing, translation. Text at
 *  100% no longer reads as "done" while timing/translation lag behind. */
function MultiRing({ text, timing, trans }: { text: number; timing: number; trans: number }) {
  const rings = [
    { pct: text, r: 25, cls: "text" },
    { pct: timing, r: 19, cls: "timing" },
    { pct: trans, r: 13, cls: "trans" },
  ];
  return (
    <svg className="mring" viewBox="0 0 60 60" width="72" height="72" aria-hidden>
      {rings.map((ring) => {
        const c = 2 * Math.PI * ring.r;
        return (
          <g key={ring.cls}>
            <circle className="mring-bg" cx="30" cy="30" r={ring.r} />
            <circle
              className={"mring-fg " + ring.cls}
              cx="30"
              cy="30"
              r={ring.r}
              strokeDasharray={`${(c * ring.pct) / 100} ${c}`}
              transform="rotate(-90 30 30)"
            />
          </g>
        );
      })}
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
type Chip = { label: string; tone: Tone; icon?: string };

/** status chips for a card's selected language track.
 *  ko  → two axes: 자막(text review) + 타이밍
 *  lang → one chip: translation progress */
function chipsFor(j: JobSummary, lang: string, proc?: QueueItem): Chip[] {
  if (j.running) {
    const note = proc?.note && proc.note !== "처리 중" ? proc.note : "처리 중";
    // only flag a stall during STT, where the heartbeat updates every few
    // seconds — the correction step is a black box that legitimately runs for
    // minutes without a beat, so a growing age there is not a stall.
    const stalled =
      typeof proc?.age === "number" && proc.age > 150 && note.startsWith("음성인식");
    return [{ label: stalled ? `${note} ⚠` : note, tone: "live" }];
  }
  if (lang === "ko") {
    if (j.segments === 0) return [{ label: "대기 중", tone: "muted" }];
    const text: Chip = j.ko_complete
      ? { label: "자막 ✓", tone: "done" }
      : {
          label: `자막 ${j.reviewed}/${j.segments} (${Math.round((j.reviewed / j.segments) * 100)}%)`,
          tone: "progress",
        };
    const timing: Chip = !j.ko_complete
      ? { label: "타이밍", tone: "muted", icon: "⏱" }
      : j.timing_done
        ? { label: "타이밍 ✓", tone: "done" }
        : { label: "타이밍 필요", tone: "warn", icon: "⏱" };
    return [text, timing];
  }
  const l = j.languages.find((x) => x.code === lang);
  if (!l || l.translated === 0) return [{ label: "번역 전", tone: "muted" }];
  const denom = l.forked ? l.translated : j.segments;
  const text: Chip = l.complete
    ? { label: "번역 ✓", tone: "done" }
    : l.reviewed > 0
      ? {
          label: `번역 ${l.reviewed}/${denom} (${Math.round((l.reviewed / denom) * 100)}%)`,
          tone: "progress",
        }
      : { label: "번역됨 · 검수 전", tone: "muted" };
  // a forked track is retimed independently — surface its own timing axis
  if (!l.forked) return [text];
  const timing: Chip = l.timing_done
    ? { label: "타이밍 ✓", tone: "done" }
    : { label: "타이밍", tone: "muted", icon: "⏱" };
  return [text, timing];
}

function JobCard({
  job: j,
  query,
  isCursor,
  dataIdx,
  canIngest,
  proc,
  onOpen,
  onReroll,
  onExport,
  onCopyLink,
  onSrtFile,
  onUndoSrt,
  onAssign,
}: {
  job: JobSummary;
  query: string;
  isCursor: boolean;
  dataIdx: number;
  canIngest: boolean;
  proc?: QueueItem;
  onOpen: (videoId: string, lang: string) => void;
  onReroll: (e: ReactMouseEvent, j: JobSummary) => void;
  onExport: (e: ReactMouseEvent, j: JobSummary, lang?: string) => void;
  onCopyLink: (e: ReactMouseEvent, j: JobSummary) => void;
  onSrtFile: (videoId: string, file: File) => void;
  onUndoSrt: (videoId: string) => void;
  onAssign: (videoId: string, current: string) => void;
}) {
  const [lang, setLang] = useState("ko");
  const [dragOver, setDragOver] = useState(false);
  const srtInputRef = useRef<HTMLInputElement>(null);
  const openable = j.segments > 0;
  const chips = chipsFor(j, lang, proc);
  const allDone = chips.length > 0 && chips.every((c) => c.tone === "done");
  const koPct = j.segments ? Math.round((j.reviewed / j.segments) * 100) : 0;
  const selPct =
    lang === "ko"
      ? koPct
      : (() => {
          const l = j.languages.find((x) => x.code === lang);
          // a forked track has its OWN segment count (l.translated); the ko
          // count (j.segments) would give a wrong % (>100%) once it's re-split
          const denom = l ? (l.forked ? l.translated : j.segments) : 0;
          return l && denom ? Math.round((l.reviewed / denom) * 100) : 0;
        })();
  const langOpts = [
    { code: "ko", label: "한국어", done: j.ko_complete && j.timing_done },
    ...j.languages.map((l) => ({ code: l.code, label: l.label, done: l.complete })),
  ];
  const langLabel = langOpts.find((o) => o.code === lang)?.label ?? lang;

  return (
    <div
      data-idx={dataIdx}
      data-card-lang={lang}
      className={
        "job-card" +
        (j.running ? " running" : "") +
        (openable ? "" : " disabled") +
        (isCursor ? " cursor" : "") +
        (dragOver ? " drag-over" : "")
      }
      role="button"
      tabIndex={openable ? 0 : -1}
      onDragOver={
        canIngest
          ? (e) => {
              e.preventDefault();
              setDragOver(true);
            }
          : undefined
      }
      onDragLeave={canIngest ? () => setDragOver(false) : undefined}
      onDrop={
        canIngest
          ? (e) => {
              e.preventDefault();
              setDragOver(false);
              const files = Array.from(e.dataTransfer.files);
              // prefer a .srt; otherwise pass the first file so onSrtFile can
              // reject it with a clear message (not a silent no-op)
              const f = files.find((x) => x.name.toLowerCase().endsWith(".srt")) ?? files[0];
              if (f) onSrtFile(j.video_id, f);
            }
          : undefined
      }
      onClick={() => openable && onOpen(j.video_id, lang)}
      onKeyDown={(e) => {
        if (openable && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onOpen(j.video_id, lang);
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
        {j.duration_seconds > 0 && j.duration_seconds <= SHORT_MAX && (
          <span className="thumb-form">쇼츠</span>
        )}
        {j.duration_seconds > 0 && (
          <span className="thumb-dur">
            {j.duration_seconds < 60
              ? `${Math.round(j.duration_seconds)}초`
              : `${Math.round(j.duration_seconds / 60)}분`}
          </span>
        )}
        {openable && !j.ko_complete && (
          <span className="thumb-prog">
            <span style={{ width: `${koPct}%` }} />
          </span>
        )}
        {openable && (
          <span className="quick-actions">
            {(() => {
              const l = j.languages.find((x) => x.code === lang);
              // only offer the card quick-download when it will be fast/cached:
              // ko complete, or a COMPLETE translation. A partly-translated lang
              // would trigger a synchronous 1-2 min Claude translation on a bare
              // <a download> click with no spinner — do that in the editor, which
              // shows a "번역하는 중" state. (finish it in the editor first.)
              const exportable = lang === "ko" ? j.ko_complete : !!(l && l.complete);
              if (!exportable) return null;
              const label = lang === "ko" ? "⬇ .srt" : `⬇ .srt (${langLabel})`;
              return (
                <span
                  className="qa"
                  role="button"
                  tabIndex={0}
                  title={`${langLabel} .srt 자막 바로 내려받기`}
                  onClick={(e) => onExport(e, j, lang)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") onExport(e as unknown as ReactMouseEvent, j, lang);
                  }}
                >
                  {label}
                </span>
              );
            })()}
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
            {canIngest && (
              <span
                className="qa"
                role="button"
                tabIndex={0}
                title="검수 완료한 .srt를 올려 DB에 적용 (드래그도 됨)"
                onClick={(e) => {
                  e.stopPropagation();
                  srtInputRef.current?.click();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") srtInputRef.current?.click();
                }}
              >
                📄 .srt
              </span>
            )}
            {canIngest && j.srt_undo && (
              <span
                className="qa qa-undo"
                role="button"
                tabIndex={0}
                title="방금 올린 .srt 적용을 취소하고 이전 상태로 되돌리기"
                onClick={(e) => {
                  e.stopPropagation();
                  onUndoSrt(j.video_id);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onUndoSrt(j.video_id);
                }}
              >
                ↩ .srt 취소
              </span>
            )}
          </span>
        )}
      </span>
      {canIngest && (
        <input
          ref={srtInputRef}
          type="file"
          accept=".srt"
          hidden
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onSrtFile(j.video_id, f);
            e.target.value = "";
          }}
        />
      )}
      <div className="job-info">
        <div className="job-head">
          <span className="stages">
            {chips.map((c, i) => (
              <span key={i} className={"stage stage-" + c.tone}>
                {j.running && i === 0 && <span className="spinner" />}
                {c.icon && <span className="stage-ic">{c.icon}</span>}
                {c.label}
              </span>
            ))}
          </span>
          {langOpts.length > 1 && (
            <Dropdown
              className="card-lang"
              value={lang}
              onChange={setLang}
              title="언어별 진행 상태 보기"
              stopPropagation
              options={langOpts.map((o) => ({
                value: o.code,
                label: o.label,
                // "완료" text (not ✓) so it doesn't collide with the dropdown's
                // own selection check on the selected+done language
                note: o.done ? "완료" : undefined,
              }))}
            />
          )}
        </div>
        <strong>{highlight(j.title || j.video_id, query)}</strong>
        {openable && (
          <>
            <span
              className={"job-progress" + (allDone ? " done" : "")}
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
              <button
                className={"assignee-chip" + (j.assignee ? " has" : "")}
                title="담당 검수자 지정·변경 (비우면 해제)"
                onClick={(e) => {
                  e.stopPropagation();
                  onAssign(j.video_id, j.assignee ?? "");
                }}
              >
                👤 {j.assignee || "담당 지정"}
              </button>
              {canIngest && !j.ko_complete && !j.running && (
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

/** copyable worker command — the local GPU worker that drains the queue.
 *  Auto-start on this machine is best-effort (logon task), so surface the exact
 *  command with one-click copy for when it isn't running. */
function WorkerCmd() {
  const [copied, setCopied] = useState(false);
  const cmd = "uv run jamak worker";
  return (
    <span className="worker-cmd">
      <code>{cmd}</code>
      <button
        className="worker-copy"
        title="명령 복사"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(cmd);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          } catch {
            /* clipboard blocked — user can select the text manually */
          }
        }}
      >
        {copied ? "복사됨 ✓" : "📋 복사"}
      </button>
    </span>
  );
}

export function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [srtModal, setSrtModal] = useState<{
    videoId: string;
    filename: string;
    content: string;
    preview: SrtPreview;
  } | null>(null);
  const [srtBusy, setSrtBusy] = useState(false);
  const [assignModal, setAssignModal] = useState<{
    videoId: string;
    title: string;
    current: string;
  } | null>(null);
  const [assignName, setAssignName] = useState("");
  const [version, setVersion] = useState("");
  useEffect(() => {
    fetchVersion().then(setVersion);
  }, []);
  const [loaded, setLoaded] = useState(false);
  // who am I? drives the login gate + admin-only pipeline UI. Until /api/me
  // answers we render nothing (avoids a flash of the app before the login form).
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => {
    fetchMe()
      .then(setMe)
      .catch(() =>
        setMe({ name: "", is_admin: true, authed: true, auth_on: false, can_ingest: true }),
      );
  }, []);
  // can this host actually run the GPU pipeline? False on the cloud app (no GPU)
  // -> hide the create box / re-roll so videos are only made on the local machine.
  const canIngest = me?.can_ingest ?? false;
  const [selected, setSelected] = useState<string | null>(null);
  // language track to open the editor on (the track the reviewer was viewing
  // on the card). Falls back to Korean for resume-hero / paste-to-open.
  const [selectedLang, setSelectedLang] = useState("ko");
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
  const [form, setForm] = useState<"all" | "short" | "long">(
    () => (localStorage.getItem("jamak.form") as "all" | "short" | "long") || "all",
  );
  const [query, setQuery] = useState("");
  // "내 담당만": one click narrows the board to videos assigned to me
  const [mineOnly, setMineOnly] = useState(() => localStorage.getItem("jamak.mine") === "1");
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
  useEffect(() => localStorage.setItem("jamak.form", form), [form]);
  useEffect(() => localStorage.setItem("jamak.mine", mineOnly ? "1" : "0"), [mineOnly]);

  async function refresh() {
    try {
      const [list, q] = await Promise.all([fetchJobs(), fetchQueue()]);
      setJobs(list);
      setQueue(q);
      setLoaded(true);
      const busy = list.some((j) => j.running) || q.length > 0;
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(refresh, busy ? 3000 : 30000);
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
        if (j && j.segments > 0) {
          // honor the cursored card's selected language, matching a mouse click
          // (the card's lang is local state, mirrored onto data-card-lang)
          const card = document.querySelector<HTMLElement>(
            `.job-card[data-idx="${cursorRef.current}"]`,
          );
          setSelectedLang(card?.dataset.cardLang || "ko");
          setSelected(j.video_id);
        }
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

  // read the dropped/selected .srt and open the preview modal (a dry run — no
  // DB write yet, so a wrong-video drop is cancelled before anything changes)
  async function onSrtFile(videoId: string, file: File) {
    setError("");
    if (!file.name.toLowerCase().endsWith(".srt")) {
      setError(`.srt 파일만 올릴 수 있어요 (받은 파일: ${file.name})`);
      return;
    }
    try {
      const content = await file.text();
      const preview = await importSrt(videoId, content, file.name, true);
      setSrtModal({ videoId, filename: file.name, content, preview });
    } catch (e) {
      setError(`.srt 미리보기 실패: ${e instanceof Error ? e.message : e}`);
    }
  }

  async function applySrt() {
    if (!srtModal || srtBusy) return;
    setSrtBusy(true);
    try {
      await importSrt(srtModal.videoId, srtModal.content, srtModal.filename, false);
      setSrtModal(null);
      await refresh();
    } catch (e) {
      setError(`.srt 적용 실패: ${e instanceof Error ? e.message : e}`);
    } finally {
      setSrtBusy(false);
    }
  }

  function assignReviewer(videoId: string, current: string) {
    const title = jobs.find((j) => j.video_id === videoId)?.title ?? "";
    setAssignName(current || me?.name || "");
    setAssignModal({ videoId, title, current });
  }

  async function saveAssign(name: string) {
    if (!assignModal) return;
    setError("");
    try {
      await setAssignee(assignModal.videoId, name.trim());
      setAssignModal(null);
      await refresh();
    } catch (e) {
      setError(`담당 지정 실패: ${e instanceof Error ? e.message : e}`);
    }
  }

  async function undoSrtImport(videoId: string) {
    if (!window.confirm(".srt 적용을 취소하고 이전 상태로 되돌릴까요?")) return;
    setError("");
    try {
      await undoSrt(videoId);
      await refresh();
    } catch (e) {
      setError(`되돌리기 실패: ${e instanceof Error ? e.message : e}`);
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

  function exportSrt(e: ReactMouseEvent, j: JobSummary, lang = "ko") {
    e.stopPropagation();
    const a = document.createElement("a");
    a.href = exportUrl(j.video_id, "best", lang);
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
    // search matches the title OR the assigned reviewer's name, so typing a
    // reviewer instantly narrows to their videos
    if (q)
      list = list.filter(
        (j) =>
          (j.title || j.video_id).toLowerCase().includes(q) ||
          (j.assignee || "").toLowerCase().includes(q),
      );
    if (mineOnly && me?.name) list = list.filter((j) => (j.assignee || "") === me.name);
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
    if (filter !== "all")
      list = list.filter((j) => j.languages.some((l) => l.code === filter));
    if (form === "short")
      list = list.filter((j) => j.duration_seconds > 0 && j.duration_seconds <= SHORT_MAX);
    else if (form === "long") list = list.filter((j) => j.duration_seconds > SHORT_MAX);
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
  }, [jobs, filter, status, form, sort, dir, query, mineOnly, me]);

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

  // wait for /api/me, then gate on login
  if (!me) return null;
  if (me.auth_on && !me.authed) return <Login onLogin={() => window.location.reload()} />;

  if (selected)
    return (
      <Editor
        videoId={selected}
        onBack={() => setSelected(null)}
        koComplete={jobs.find((j) => j.video_id === selected)?.ko_complete ?? false}
        timingDone={jobs.find((j) => j.video_id === selected)?.timing_done ?? false}
        initialLang={selectedLang}
        languages={jobs.find((j) => j.video_id === selected)?.languages ?? []}
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
  // three progress axes (text review is NOT the whole job): text ko review,
  // timing pass, and translation review — shown as overlaid rings so text
  // hitting 100% doesn't hide that timing/translation are still outstanding.
  const textPct = totalSegments ? Math.round((totalReviewed / totalSegments) * 100) : 0;
  const timingDoneSegs = jobs.reduce((a, j) => a + (j.timing_done ? j.segments : 0), 0);
  const timingPct = totalSegments ? Math.round((timingDoneSegs / totalSegments) * 100) : 0;
  let transReviewed = 0;
  let transTotal = 0;
  for (const j of jobs)
    for (const l of j.languages) {
      transReviewed += l.reviewed;
      transTotal += l.forked ? l.translated : j.segments;
    }
  const transPct = transTotal ? Math.round((transReviewed / transTotal) * 100) : 0;
  const resumePct = resume ? Math.round((resume.reviewed / resume.segments) * 100) : 0;
  const previewId = parseVideoId(url);
  const filtersActive =
    status !== "all" || filter !== "all" || form !== "all" || query.trim() !== "" || mineOnly;

  function resetFilters() {
    setStatus("all");
    setFilter("all");
    setForm("all");
    setQuery("");
    setMineOnly(false);
  }

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="header-top">
          <span className="deploy-tag" title="현재 배포된 버전(커밋)">
            {version ? `배포 ${version}` : ""}
          </span>
          <div className="header-actions">
            {me.auth_on && me.authed && (
              <span className="user-chip">
                <span className={"role-badge" + (me.is_admin ? " admin" : "")}>
                  {me.is_admin ? "관리자" : "검수자"}
                </span>
                {me.name && <span className="user-name">{me.name}</span>}
                <button
                  className="switch-btn"
                  title="다른 이름·비밀번호로 다시 로그인"
                  onClick={async () => {
                    await logout();
                    window.location.reload();
                  }}
                >
                  계정 변경
                </button>
              </span>
            )}
            <button className="help-btn" title="단축키 (?)" onClick={() => setShowHelp((v) => !v)}>
              ?
            </button>
            <ThemeToggle />
          </div>
        </div>
        <h1>
          자막 검수 작업대 <span className="brand-inf">♾️</span>
        </h1>
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

      {canIngest && (
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
      )}

      {canIngest &&
        queue.length > 0 &&
        (() => {
          const proc = queue.find((q) => q.status === "processing");
          const queued = queue.filter((q) => q.status === "queued");
          const errored = queue.filter((q) => q.status === "error");
          const cancel = async (vid: string) => {
            await cancelRequest(vid);
            await refresh();
          };
          return (
            <div className="queue-bar">
              <span className={"queue-spin" + (proc ? "" : " idle")} aria-hidden>
                ⏳
              </span>
              <span className="queue-txt">
                {proc ? (
                  <>
                    처리 중 <strong>{proc.video_id}</strong>
                    {proc.note && ` · ${proc.note}`}
                    {typeof proc.age === "number" &&
                      (proc.age > 150 && (proc.note ?? "").startsWith("음성인식") ? (
                        <span className="queue-err"> · ⚠ {proc.age}초째 응답 없음</span>
                      ) : (
                        ` · ${proc.age < 5 ? "방금" : `${proc.age}초 전`} 갱신`
                      ))}
                    {queued.length > 0 && ` · 대기 ${queued.length}개`}
                  </>
                ) : queued.length > 0 ? (
                  <>
                    대기 {queued.length}개 — 처리하려면 이 PC에서 아래 명령을 실행하세요
                    <WorkerCmd />
                  </>
                ) : (
                  errored.length > 0 && <>대기 없음</>
                )}
                {errored.length > 0 && (
                  <span className="queue-err"> · 실패 {errored.length}개</span>
                )}
              </span>
              <span className="queue-cancels">
                {[...(proc ? [proc] : []), ...queued, ...errored].map((q) => (
                  <button
                    key={q.video_id}
                    className="queue-cancel"
                    title={`${q.video_id} 요청 취소 (멈춘 처리도 지움)`}
                    onClick={() => cancel(q.video_id)}
                  >
                    ✕ {q.video_id}
                  </button>
                ))}
              </span>
            </div>
          );
        })()}
      {error && <div className="error">{error}</div>}

      {resume && (
        <button
          className="resume-hero"
          onClick={() => {
            setSelectedLang("ko");
            setSelected(resume.video_id);
          }}
        >
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
          <MultiRing text={textPct} timing={timingPct} trans={transPct} />
          <div className="ws-ring-legend">
            <span className="rleg text"><i />텍스트 {textPct}%</span>
            <span className="rleg timing"><i />타이밍 {timingPct}%</span>
            <span className="rleg trans"><i />번역 {transPct}%</span>
          </div>
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
              <strong>
                <span className="wstat-dot" aria-label="처리 중" />
              </strong>
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
          // 처리 중 is always 0 or 1 — the number is noise. Show a live dot +
          // highlight when something is processing instead of a count.
          const isRunning = s.key === "running";
          return (
            <button
              key={s.key}
              className={
                "pill" +
                (status === s.key ? " on" : "") +
                (isRunning && count > 0 ? " pill-live" : "")
              }
              onClick={() => setStatus(s.key)}
            >
              {s.label}
              {isRunning ? count > 0 && <span className="pill-dot" /> : <em>{count}</em>}
            </button>
          );
        })}
      </div>

      <div className="filter-bar">
        <input
          ref={searchRef}
          className="search"
          type="search"
          placeholder="🔍 제목·담당자 검색  ( / )"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setQuery("");
              (e.target as HTMLInputElement).blur();
            }
          }}
        />
        {me?.name && (
          <button
            className={"mine-chip" + (mineOnly ? " on" : "")}
            title={`${me.name} 담당으로 지정된 영상만 보기`}
            onClick={() => setMineOnly((v) => !v)}
          >
            👤 내 담당만
          </button>
        )}
        {/* YouTube form is only ever 롱폼 vs 쇼츠 — a 3-way segmented toggle
            reads faster than a dropdown */}
        <div className="form-toggle" role="group" aria-label="영상 형식">
          {([
            ["all", "전체"],
            ["long", "롱폼"],
            ["short", "쇼츠"],
          ] as [typeof form, string][]).map(([v, label]) => (
            <button
              key={v}
              className={form === v ? "on" : ""}
              onClick={() => setForm(v)}
            >
              {label}
            </button>
          ))}
        </div>
        {allLangs.length > 0 && (
          <label>
            번역 언어
            <Dropdown
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "전체" },
                ...allLangs.map((l) => ({ value: l.code, label: `${l.label} 있는 영상` })),
              ]}
            />
          </label>
        )}
        <label>
          정렬
          <Dropdown
            value={sort}
            onChange={(v) => setSort(v as SortField)}
            options={(Object.keys(SORT_LABEL) as SortField[]).map((k) => ({
              value: k,
              label: SORT_LABEL[k],
            }))}
          />
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
              canIngest={canIngest}
              proc={queue.find((q) => q.status === "processing" && q.video_id === j.video_id)}
              onSrtFile={onSrtFile}
              onUndoSrt={undoSrtImport}
              onAssign={assignReviewer}
              onOpen={(v, l) => {
                setSelectedLang(l);
                setSelected(v);
              }}
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

      {srtModal && (
        <div
          className="srt-modal-back"
          onMouseDown={(e) => {
            // only close on a press that STARTS on the backdrop — not a text
            // drag-select inside the modal that happens to release out here
            if (e.target === e.currentTarget && !srtBusy) setSrtModal(null);
          }}
        >
          <div className="srt-modal" onClick={(e) => e.stopPropagation()}>
            <h3>📄 이 .srt를 적용할까요?</h3>

            <div className="srt-kv">
              <span className="srt-k">파일</span>
              <span className="srt-v" title={srtModal.filename}>
                {srtModal.filename}
              </span>
              <span className="srt-k">적용 대상</span>
              <span className="srt-v strong" title={srtModal.preview.title}>
                {srtModal.preview.title || srtModal.videoId}
              </span>
            </div>

            <p className="srt-summary">
              이 영상의 자막 <strong>{srtModal.preview.total}개</strong> 중{" "}
              <strong>{srtModal.preview.matched}개</strong>에 이 .srt 내용이 채워집니다.
            </p>

            {srtModal.preview.total > 0 &&
              srtModal.preview.matched / srtModal.preview.total < 0.8 && (
                <p className="srt-warn">
                  ⚠ 매칭 {Math.round((srtModal.preview.matched / srtModal.preview.total) * 100)}%
                  — 이 .srt의 자막 나눔·시간이 영상과 달라 일부만 채워져요. 확인 후 적용하세요.
                </p>
              )}
            {srtModal.preview.already_reviewed > 0 && (
              <p className="srt-warn">
                ⚠ 이미 검수한 {srtModal.preview.already_reviewed}개 자막을 덮어씁니다. (적용 후
                ↩ 취소로 되돌릴 수 있어요)
              </p>
            )}

            {srtModal.preview.sample.length > 0 && (
              <div className="srt-sample">
                <div className="srt-sample-head">
                  <span>지금 자막</span>
                  <span>→ 바뀔 자막</span>
                </div>
                {srtModal.preview.sample.map((s) => (
                  <div key={s.idx} className="srt-row">
                    <span className="srt-old" title={s.old}>
                      {s.old || "(비어 있음)"}
                    </span>
                    <span className="srt-new" title={s.new}>
                      {s.new}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <div className="srt-actions">
              <button className="srt-cancel" onClick={() => setSrtModal(null)} disabled={srtBusy}>
                취소
              </button>
              <button
                className="srt-apply"
                onClick={applySrt}
                disabled={srtBusy || srtModal.preview.matched === 0}
              >
                {srtBusy ? "적용 중..." : `${srtModal.preview.matched}개 적용`}
              </button>
            </div>
          </div>
        </div>
      )}

      {assignModal && (
        <div
          className="srt-modal-back"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setAssignModal(null);
          }}
        >
          <form
            className="assign-modal"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => {
              e.preventDefault();
              saveAssign(assignName);
            }}
          >
            <h3>👤 담당 검수자</h3>
            <p className="assign-target" title={assignModal.title}>
              {assignModal.title || assignModal.videoId}
            </p>
            <input
              autoFocus
              className="assign-input"
              value={assignName}
              onChange={(e) => setAssignName(e.target.value)}
              placeholder="검수자 이름"
              onKeyDown={(e) => {
                if (e.key === "Escape") setAssignModal(null);
              }}
            />
            {me?.name && assignName.trim() !== me.name && (
              <button
                type="button"
                className="assign-me"
                onClick={() => setAssignName(me.name)}
              >
                내 이름({me.name})으로
              </button>
            )}
            <div className="srt-actions">
              {assignModal.current && (
                <button type="button" className="assign-clear" onClick={() => saveAssign("")}>
                  담당 해제
                </button>
              )}
              <button type="button" className="srt-cancel" onClick={() => setAssignModal(null)}>
                취소
              </button>
              <button type="submit" className="srt-apply" disabled={!assignName.trim()}>
                지정
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
