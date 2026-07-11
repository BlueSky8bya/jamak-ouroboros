import type { JobSummary, Segment } from "./types";

export async function fetchJobs(): Promise<JobSummary[]> {
  const r = await fetch("/api/jobs");
  if (!r.ok) throw new Error(`jobs: ${r.status}`);
  return r.json();
}

export interface QueueItem {
  video_id: string;
  status: "processing" | "queued";
  position?: number;
}

export async function fetchQueue(): Promise<QueueItem[]> {
  const r = await fetch("/api/queue");
  if (!r.ok) return [];
  return r.json();
}

export interface Me {
  name: string;
  is_admin: boolean;
  authed: boolean;
  auth_on: boolean;
  can_ingest?: boolean; // admin AND this host has the GPU pipeline (not a cloud host)
}

export async function fetchMe(): Promise<Me> {
  const r = await fetch("/api/me");
  if (!r.ok) throw new Error(`me: ${r.status}`);
  return r.json();
}

export async function login(name: string, password: string): Promise<Me> {
  const r = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, password }),
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `login: ${r.status}`);
  return r.json();
}

export async function logout(): Promise<void> {
  await fetch("/api/logout", { method: "POST" }).catch(() => {});
}

export async function fetchSegments(videoId: string, lang = "ko"): Promise<Segment[]> {
  const r = await fetch(`/api/jobs/${videoId}/segments?lang=${lang}`);
  if (!r.ok) throw new Error(`segments: ${r.status}`);
  return r.json();
}

export async function forkTrack(
  videoId: string,
  lang: string,
): Promise<{ video_id: string; lang: string; forked: boolean; created: number }> {
  const r = await fetch(`/api/jobs/${videoId}/fork-track?lang=${lang}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `fork: ${r.status}`);
  return r.json();
}

export async function unforkTrack(
  videoId: string,
  lang: string,
): Promise<{ video_id: string; lang: string; forked: boolean; restored: number }> {
  const r = await fetch(`/api/jobs/${videoId}/unfork-track?lang=${lang}`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `unfork: ${r.status}`);
  return r.json();
}

export async function restoreSegments(
  videoId: string,
  segments: Segment[],
  lang = "ko",
): Promise<Segment[]> {
  const r = await fetch(`/api/jobs/${videoId}/segments/restore?lang=${lang}`, {
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
  lang = "ko",
): Promise<{ matches: number; segments: number; applied: boolean }> {
  const r = await fetch(`/api/jobs/${videoId}/replace?lang=${lang}`, {
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
  lang = "ko",
): Promise<{ video_id: string; lang: string; timing_done: boolean }> {
  const r = await fetch(`/api/jobs/${videoId}/timing-done?lang=${lang}`, {
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

// hybrid timeline-strip edge drag: free in a gap, pushes the neighbour once it
// crosses the shared wall
export async function edgeDrag(
  id: number,
  which: "start" | "end",
  time: number,
): Promise<void> {
  const r = await fetch(`/api/segments/${id}/edge-drag?which=${which}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `edge-drag: ${r.status}`);
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
