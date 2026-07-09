import { useEffect, useRef, useState } from "react";
import { createJob, fetchJobs } from "./api";
import { Editor } from "./Editor";
import type { JobSummary } from "./types";

const STATUS_LABEL: Record<string, string> = {
  starting: "시작 중...",
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
    if (j.status === "starting") return "다운로드 중...";
    if (j.status === "ingested") return "음성 인식 중 (GPU)";
    if (j.status === "transcribed") return "교차검증 중";
    return STATUS_LABEL[j.status] ?? j.status;
  }
  return STATUS_LABEL[j.status] ?? j.status;
}

export function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const timer = useRef<number | null>(null);

  async function refresh() {
    try {
      const list = await fetchJobs();
      setJobs(list);
      const anyRunning = list.some((j) => j.running);
      if (timer.current) window.clearTimeout(timer.current);
      // poll fast while a pipeline is running, slowly otherwise
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

  if (selected) return <Editor videoId={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="landing">
      <header>
        <h1>jamak<span>-ouroboros</span></h1>
        <p>유튜브 링크를 넣으면 자막 초안을 만들고, 검수할수록 정확해집니다.</p>
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
          {submitting ? "시작 중..." : "자막 만들기"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="job-grid">
        {jobs.map((j) => {
          const openable = j.segments > 0;
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
                  <span className="meta">
                    {Math.round(j.duration_seconds / 60)}분 · {j.segments} 세그먼트 · 검수{" "}
                    {j.reviewed}/{j.segments}
                  </span>
                )}
              </div>
            </button>
          );
        })}
        {jobs.length === 0 && !error && (
          <p className="empty">아직 작업이 없습니다. 위에 링크를 붙여넣어 시작하세요.</p>
        )}
      </div>
    </div>
  );
}
