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

export async function restoreSegments(videoId: string, segments: Segment[]): Promise<Segment[]> {
  const r = await fetch(`/api/jobs/${videoId}/segments/restore`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `restore: ${r.status}`);
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

export async function createJob(url: string): Promise<{ video_id: string; status: string }> {
  const r = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `create: ${r.status}`);
  return r.json();
}

export async function replaceText(
  videoId: string,
  find: string,
  replace: string,
  apply: boolean,
): Promise<{ matches: number; segments: number; applied: boolean }> {
  const r = await fetch(`/api/jobs/${videoId}/replace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ find, replace, apply }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `replace: ${r.status}`);
  return r.json();
}

export async function setTimingDone(
  videoId: string,
  done: boolean,
): Promise<{ video_id: string; timing_done: boolean }> {
  const r = await fetch(`/api/jobs/${videoId}/timing-done`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ done }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `timing-done: ${r.status}`);
  return r.json();
}

export async function confirmSafe(videoId: string): Promise<{ confirmed: number }> {
  const r = await fetch(`/api/jobs/${videoId}/confirm-safe`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `confirm-safe: ${r.status}`);
  return r.json();
}

export async function retranscribe(
  videoId: string,
): Promise<{ video_id: string; status: string }> {
  const r = await fetch(`/api/jobs/${videoId}/retranscribe`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `retranscribe: ${r.status}`);
  return r.json();
}

export async function splitSegment(id: number, position: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `split: ${r.status}`);
}

export async function mergeNext(id: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}/merge-next`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `merge: ${r.status}`);
}

export async function boundaryNext(id: number, time: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}/boundary-next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `boundary: ${r.status}`);
}

export async function boundaryPrev(id: number, time: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}/boundary-prev`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `boundary: ${r.status}`);
}

export async function redistributeNext(id: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}/redistribute-next`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `redistribute: ${r.status}`);
}

export async function deleteSegment(id: number): Promise<void> {
  const r = await fetch(`/api/segments/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete: ${r.status}`);
}

export async function repairStt(
  videoId: string,
): Promise<{ repaired: number; no_caption: number; filled: number }> {
  const r = await fetch(`/api/jobs/${videoId}/repair-stt`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `repair: ${r.status}`);
  return r.json();
}

export async function tightenTiming(
  videoId: string,
): Promise<{ tightened: number; total: number }> {
  const r = await fetch(`/api/jobs/${videoId}/tighten`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `tighten: ${r.status}`);
  return r.json();
}

export interface WordTime {
  start: number;
  end: number;
  word: string;
}

export async function fetchWords(videoId: string): Promise<WordTime[]> {
  const r = await fetch(`/api/jobs/${videoId}/words`);
  if (!r.ok) throw new Error(`words: ${r.status}`);
  return (await r.json()).words;
}

export interface TranslationRow {
  segment_id: number;
  idx: number;
  start: number;
  end: number;
  ko: string;
  text: string;
  reviewed: boolean;
  has_translation: boolean;
  stale?: boolean; // Korean changed after this translation was made
}

export async function makeTranslations(
  videoId: string,
  lang: string,
): Promise<{ lang: string; translated: number; segments: number }> {
  const r = await fetch(`/api/jobs/${videoId}/translate?lang=${lang}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `translate: ${r.status}`);
  return r.json();
}

export async function fetchTranslations(videoId: string, lang: string): Promise<TranslationRow[]> {
  const r = await fetch(`/api/jobs/${videoId}/translations?lang=${lang}`);
  if (!r.ok) throw new Error(`translations: ${r.status}`);
  return r.json();
}

export async function updateTranslation(
  segmentId: number,
  lang: string,
  body: { text?: string; reviewed?: boolean },
): Promise<{ segment_id: number; text: string; reviewed: boolean }> {
  const r = await fetch(`/api/translations/${segmentId}?lang=${lang}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`save translation: ${r.status}`);
  return r.json();
}

export async function absorbFeedback(videoId: string): Promise<{
  reviewed_segments: number;
  new_pairs: number;
  bumped: number;
  applied: number;
  propagated_segments: number;
  propagated_replacements: number;
  propagation_pairs: number;
}> {
  const r = await fetch(`/api/jobs/${videoId}/absorb`, { method: "POST" });
  if (!r.ok) throw new Error(`absorb: ${r.status}`);
  return r.json();
}
