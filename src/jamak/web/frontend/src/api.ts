import type { JobSummary, Segment } from "./types";

export async function fetchJobs(): Promise<JobSummary[]> {
  const r = await fetch("/api/jobs");
  if (!r.ok) throw new Error(`jobs: ${r.status}`);
  return r.json();
}

export async function fetchSegments(videoId: string): Promise<Segment[]> {
  const r = await fetch(`/api/jobs/${videoId}/segments`);
  if (!r.ok) throw new Error(`segments: ${r.status}`);
  return r.json();
}

export async function updateSegment(
  id: number,
  body: Partial<Pick<Segment, "text_final" | "start" | "end" | "reviewed">>,
): Promise<Segment> {
  const r = await fetch(`/api/segments/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`save: ${r.status}`);
  return r.json();
}

export function exportUrl(videoId: string, stage = "best"): string {
  return `/api/jobs/${videoId}/export?stage=${stage}`;
}
