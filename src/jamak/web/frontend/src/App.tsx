import { useEffect, useMemo, useRef, useState } from "react";
import { createJob, fetchJobs } from "./api";
import { Editor } from "./Editor";
import type { JobLang, JobSummary } from "./types";

const STATUS_LABEL: Record<string, string> = {
  starting: "시작 중",
  pending: "대기",
  ingested: "음성 인식 중",
  transcribed: "인식 완료",
  correcting: "AI 교정 중",
  corrected: "검수 대기",
  reviewing: "검수 중",
  done: "완료",
};

function statusLabel(j: JobSummary): string {
  if (j.running) {
    if (j.status === "starting") return "다운로드 중";
    if (j.status === "ingested") return "음성 인식 중(GPU)";
    if (j.status === "transcribed") return "교차검증 중";
    return STATUS_LABEL[j.status] ?? j.status;
  }
  return STATUS_LABEL[j.status] ?? j.status;
}

type SortKey = "uploaded" | "recent" | "oldest" | "title" | "progress";
const SORT_LABEL: Record<SortKey, string> = {
  uploaded: "유튜브 업로드 최신순",
  recent: "최근 추가순",
  oldest: "오래된 순",
  title: "제목순",
  progress: "검수 진행률순",
};

export function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [filter, setFilter] = useState("all"); // all | ko | <langcode>
  const [sort, setSort] = useState<SortKey>("uploaded");
  const [query, setQuery] = useState("");
  const timer = useRef<number | null>(null);

  async function refresh() {
    try {
      const list = await fetchJobs();
      setJobs(list);
      const anyRunning = list.some((j) => j.running);
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(refresh, anyRunning ? 3000 : 30000);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    if (selected === null) refresh();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
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

  // every translation language that appears across all jobs (for the filter)
  const allLangs = useMemo(() => {
    const map = new Map<string, string>();
    for (const j of jobs) for (const l of j.languages) map.set(l.code, l.label);
    return [...map.entries()].map(([code, label]) => ({ code, label }));
  }, [jobs]);

  const visible = useMemo(() => {
    let list = jobs.slice();
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((j) => (j.title || j.video_id).toLowerCase().includes(q));
    if (filter === "ko") list = list.filter((j) => j.ko_complete);
    else if (filter !== "all")
      list = list.filter((j) => j.languages.some((l) => l.code === filter && l.complete));
    list.sort((a, b) => {
      if (sort === "title") return (a.title || a.video_id).localeCompare(b.title || b.video_id, "ko");
      if (sort === "progress") {
        const pa = a.segments ? a.reviewed / a.segments : 0;
        const pb = b.segments ? b.reviewed / b.segments : 0;
        return pb - pa;
      }
      if (sort === "uploaded") {
        // real YouTube upload date; jobs without one sort last
        const ua = a.upload_date || "0";
        const ub = b.upload_date || "0";
        if (ua !== ub) return ub.localeCompare(ua);
        return (b.created_at || "").localeCompare(a.created_at || "");
      }
      const cmp = (a.created_at || "").localeCompare(b.created_at || "");
      return sort === "oldest" ? cmp : -cmp;
    });
    return list;
  }, [jobs, filter, sort, query]);

  if (selected) return <Editor videoId={selected} onBack={() => setSelected(null)} />;

  const runningCount = jobs.filter((j) => j.running).length;
  const koDoneCount = jobs.filter((j) => j.ko_complete).length;

  return (
    <div className="landing">
      <header className="landing-header">
        <div>
          <span className="product-label">Jamak Ouroboros</span>
          <h1>자막 검수 작업대</h1>
        </div>
        <p>유튜브 강연 자막을 만들고, 검수하고, 고친 내용을 다음 작업에 되먹임합니다.</p>
      </header>

      <div className="url-box">
        <input
          type="text"
          placeholder="https://youtube.com/watch?v=... 강연 영상 링크 붙여넣기"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <button onClick={submit} disabled={submitting || !url.trim()}>
          {submitting ? "시작 중" : "자막 만들기"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="dashboard-summary">
        <span>작업 {jobs.length}</span>
        <span>진행 중 {runningCount}</span>
        <span>한국어 완료 {koDoneCount}</span>
      </div>

      <div className="filter-bar">
        <input
          className="search"
          type="search"
          placeholder="🔍 제목으로 검색"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label>
          보기
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">모든 영상</option>
            <option value="ko">한국어 완료</option>
            {allLangs.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label} 완료
              </option>
            ))}
          </select>
        </label>
        <label>
          정렬
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABEL[k]}
              </option>
            ))}
          </select>
        </label>
        <span className="filter-count">{visible.length}개</span>
      </div>

      <div className="job-grid">
        {visible.map((j) => {
          const openable = j.segments > 0;
          const reviewedPct = j.segments ? Math.round((j.reviewed / j.segments) * 100) : 0;
          return (
            <button
              key={j.video_id}
              className={"job-card" + (j.running ? " running" : "")}
              disabled={!openable}
              onClick={() => openable && setSelected(j.video_id)}
              title={openable ? "검수 열기" : "파이프라인 처리 중"}
            >
              <img
                src={`https://img.youtube.com/vi/${j.video_id}/mqdefault.jpg`}
                alt=""
                loading="lazy"
              />
              <div className="job-info">
                <strong>{j.title || j.video_id}</strong>
                <span className={"status" + (j.running ? " live" : "")}>
                  {j.running && <span className="spinner" />} {statusLabel(j)}
                </span>
                {j.segments > 0 && (
                  <>
                    <span className="lang-badges">
                      <span
                        className={"lbadge ko" + (j.ko_complete ? " done" : "")}
                        title={`한국어 검수 ${j.reviewed}/${j.segments}`}
                      >
                        {j.ko_complete ? "한국어 ✓" : `한국어 ${j.reviewed}/${j.segments}`}
                      </span>
                      {j.languages.map((l: JobLang) => (
                        <span
                          key={l.code}
                          className={"lbadge" + (l.complete ? " done" : "")}
                          title={`${l.label} 번역 검수 ${l.reviewed}/${j.segments}`}
                        >
                          {l.complete ? `${l.label} ✓` : `${l.label} ${l.reviewed}/${j.segments}`}
                        </span>
                      ))}
                    </span>
                    <span className="meta">
                      {Math.round(j.duration_seconds / 60)}분 · 자막 {j.segments}개
                      {j.upload_date &&
                        ` · 업로드 ${j.upload_date.slice(0, 4)}.${j.upload_date.slice(4, 6)}.${j.upload_date.slice(6, 8)}`}
                    </span>
                    <span className="job-progress" aria-label={`검수 진행률 ${reviewedPct}%`}>
                      <span style={{ width: `${reviewedPct}%` }} />
                    </span>
                  </>
                )}
              </div>
            </button>
          );
        })}
        {visible.length === 0 && !error && (
          <p className="empty">
            {jobs.length === 0
              ? "아직 작업이 없습니다. 위에 링크를 붙여넣어 시작하세요."
              : "이 조건에 맞는 영상이 없습니다."}
          </p>
        )}
      </div>
    </div>
  );
}
