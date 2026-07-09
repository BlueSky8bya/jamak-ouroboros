import { useEffect, useState } from "react";
import { fetchJobs } from "./api";
import { Editor } from "./Editor";
import type { JobSummary } from "./types";

export function App() {
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (selected === null)
      fetchJobs().then(setJobs).catch((e) => setError(String(e)));
  }, [selected]);

  if (selected) return <Editor videoId={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="job-list">
      <h1>jamak-ouroboros 검수</h1>
      {error && <div className="error">{error}</div>}
      {jobs.length === 0 && !error && (
        <p>작업이 없습니다. <code>uv run jamak run &lt;url&gt;</code>로 먼저 파이프라인을 실행하세요.</p>
      )}
      {jobs.map((j) => (
        <button key={j.video_id} className="job-card" onClick={() => setSelected(j.video_id)}>
          <strong>{j.title || j.video_id}</strong>
          <span>
            {Math.round(j.duration_seconds / 60)}분 · {j.segments} 세그먼트 · 검수 {j.reviewed}/{j.segments} · {j.status}
          </span>
        </button>
      ))}
    </div>
  );
}
