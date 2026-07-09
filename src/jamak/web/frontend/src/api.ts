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

export function exportUrl(videoId: string, stage = "best", lang = "ko"): string {
  return `/api/jobs/${videoId}/export?stage=${stage}&lang=${lang}`;
}

export async function fetchLanguages(): Promise<{ code: string; label: string }[]> {
  const r = await fetch("/api/languages");
  if (!r.ok) throw new Error(`languages: ${r.status}`);
  return r.json();
}

export async function absorbFeedback(videoId: string): Promise<{
  reviewed_segments: number;
  new_pairs: number;
  bumped: number;
}> {
  const r = await fetch(`/api/jobs/${videoId}/absorb`, { method: "POST" });
  if (!r.ok) throw new Error(`absorb: ${r.status}`);
  return r.json();
}
