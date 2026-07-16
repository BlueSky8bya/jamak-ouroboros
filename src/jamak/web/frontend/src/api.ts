import type { JobSummary, Segment } from "./types";

export async function fetchJobs(): Promise<JobSummary[]> {
  const r = await fetch("/api/jobs");
  if (!r.ok) throw new Error(`jobs: ${r.status}`);
  return r.json();
}

export interface QueueItem {
  video_id: string;
  status: "processing" | "queued" | "error";
  position?: number;
  note?: string;
  age?: number; // seconds since the last heartbeat (processing only)
}

export async function fetchQueue(): Promise<QueueItem[]> {
  const r = await fetch("/api/queue");
  if (!r.ok) return [];
  return r.json();
}

export async function cancelRequest(videoId: string): Promise<void> {
  await fetch(`/api/queue/${videoId}`, { method: "DELETE" });
}

export interface SrtPreview {
  title: string;
  video_id: string;
  srt_count: number;
  matched: number;
  total: number;
  already_reviewed: number;
  replace?: boolean; // v2: .srt 구조로 통째 교체
  carry?: number; // 이어받을 번역 수 (재번역 비용 절약분)
  sample: { idx: number; old: string; new: string }[];
}

export async function setPractice(
  videoId: string,
  on: boolean,
  course?: string, // bind a tutorial course ('' unbinds); omit to just toggle
): Promise<void> {
  const r = await fetch(`/api/jobs/${videoId}/practice`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(course === undefined ? { on } : { on, course }),
  });
  if (!r.ok) throw new Error(`practice: ${r.status}`);
}

/** stable per-browser id for practice-session clones (PLAN v4 §4.3) */
export function practiceKey(): string {
  let k = localStorage.getItem("jamak.practiceKey");
  if (!k) {
    k = crypto.randomUUID();
    localStorage.setItem("jamak.practiceKey", k);
  }
  return k;
}

export async function practiceSession(
  videoId: string,
  key: string,
  reset = false,
): Promise<{ video_id: string; created: boolean }> {
  const r = await fetch(`/api/jobs/${videoId}/practice-session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, reset }),
  });
  if (!r.ok) {
    let msg = `practice-session: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

export async function setAssignee(videoId: string, name: string): Promise<void> {
  await fetch(`/api/jobs/${videoId}/assignee`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function undoSrt(videoId: string): Promise<{ restored: number }> {
  const r = await fetch(`/api/jobs/${videoId}/undo-srt`, { method: "POST" });
  if (!r.ok) {
    let msg = `undo: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

export async function importSrt(
  videoId: string,
  content: string,
  filename: string,
  dryRun: boolean,
): Promise<SrtPreview & { applied?: number; absorbed?: unknown; carried_translations?: number }> {
  const r = await fetch(`/api/jobs/${videoId}/import-srt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, filename, dry_run: dryRun }),
  });
  if (!r.ok) {
    let msg = `import: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

export async function fetchVersion(): Promise<string> {
  try {
    const r = await fetch("/api/version");
    if (!r.ok) return "";
    return (await r.json()).version ?? "";
  } catch {
    return "";
  }
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

// undo ONE operation: put its before-rows back and delete the rows it created.
// Touches only those rows — a concurrent reviewer's edits elsewhere survive.
export async function restoreRows(
  videoId: string,
  lang: string,
  upsert: Segment[],
  deleteIds: number[],
): Promise<Segment[]> {
  const r = await fetch(`/api/jobs/${videoId}/segments/restore-rows?lang=${lang}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upsert, delete_ids: deleteIds }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `restore: ${r.status}`);
  return r.json();
}

export async function updateSegment(
  id: number,
  body: Partial<Pick<Segment, "text_final" | "start" | "end" | "reviewed" | "review_flag">>,
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

// 파이프라인 없이 영상 등록 + .srt 바로 붙이기 (STT·Claude·GPU 안 씀)
export async function createJobSrtOnly(
  url: string,
  content: string,
  filename: string,
): Promise<{ video_id: string; applied: number }> {
  const r = await fetch("/api/jobs/srt-only", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, content, filename }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `srt-only: ${r.status}`);
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

// mutation endpoints return the rows they changed so the client patches its
// local list instead of refetching the whole track (one RTT, no jank)
export interface ChangedRows {
  segments: Segment[];
  deleted_id?: number;
}

export async function splitSegment(id: number, position: number): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `split: ${r.status}`);
  return r.json();
}

export async function mergeNext(id: number): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/merge-next`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `merge: ${r.status}`);
  return r.json();
}

export async function boundaryNext(id: number, time: number): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/boundary-next`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `boundary: ${r.status}`);
  return r.json();
}

export async function boundaryPrev(id: number, time: number): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/boundary-prev`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `boundary: ${r.status}`);
  return r.json();
}

// hybrid timeline-strip edge drag: free in a gap, pushes the neighbour once it
// crosses the shared wall
export async function edgeDrag(
  id: number,
  which: "start" | "end",
  time: number,
): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/edge-drag?which=${which}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ time }),
  });
  if (!r.ok) throw new Error((await r.json()).detail ?? `edge-drag: ${r.status}`);
  return r.json();
}

export async function redistributeNext(id: number): Promise<ChangedRows> {
  const r = await fetch(`/api/segments/${id}/redistribute-next`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `redistribute: ${r.status}`);
  return r.json();
}

export async function deleteSegment(id: number): Promise<{ deleted_id: number }> {
  const r = await fetch(`/api/segments/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`delete: ${r.status}`);
  return r.json();
}

export async function repairStt(
  videoId: string,
): Promise<{ repaired: number; no_caption: number; filled: number }> {
  const r = await fetch(`/api/jobs/${videoId}/repair-stt`, { method: "POST" });
  if (!r.ok) throw new Error((await r.json()).detail ?? `repair: ${r.status}`);
  return r.json();
}

// one-shot timing cleanup (ADR-0009): snap to speech + split oversized cues +
// extend too-fast cues into silence. `before`/`created_ids` feed one undo step.
export interface AutoTimingResult {
  segments: Segment[];
  created_ids: number[];
  before: Segment[];
  tightened: number;
  split: number;
}

export async function autoTiming(videoId: string, lang = "ko"): Promise<AutoTimingResult> {
  const r = await fetch(`/api/jobs/${videoId}/auto-timing?lang=${lang}`, { method: "POST" });
  if (!r.ok) {
    let msg = `auto-timing: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

// rule-based pre-export quality check (no API cost) — per-category segment ids
export interface QcReport {
  total: number;
  unreviewed: number;
  issues: number;
  empty: number[];
  too_fast: number[];
  too_long_text: number[];
  bad_duration: number[];
  double_space: number[];
  hold: number[];
}

export async function fetchQc(videoId: string, lang = "ko"): Promise<QcReport> {
  const r = await fetch(`/api/jobs/${videoId}/qc?lang=${lang}`);
  if (!r.ok) throw new Error(`qc: ${r.status}`);
  return r.json();
}

// AI 맞춤법: suggestions only — the client applies accepted ones via updateSegment
export interface SpellSuggestion {
  segment_id: number;
  idx: number;
  start: number;
  before: string;
  after: string;
}

// 강조 한자어 병기 채우기 (사전 기반 결정적 치환, API 0원)
// batch>0이면 offset부터 batch행만 처리하고 remaining을 돌려줌 — 진행률 루프용.
// dry=true면 DB는 그대로 두고 before/after 제안만 — 맞춤법처럼 확인 후 선택 적용
export async function fillHanja(
  videoId: string,
  lang = "ko",
  batch = 0,
  offset = 0,
  dry = false,
): Promise<{
  changed: number;
  total: number;
  remaining: number;
  suggestions: SpellSuggestion[];
  before: { id: number; text_final: string; reviewed: boolean }[];
  segments: { id: number; text_final: string; text_llm: string }[];
}> {
  const r = await fetch(
    `/api/jobs/${videoId}/fill-hanja?lang=${lang}&batch=${batch}&offset=${offset}&dry=${dry ? 1 : 0}`,
    { method: "POST" },
  );
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `hanja: ${r.status}`);
  return r.json();
}

export async function runSpellcheck(
  videoId: string,
  lang = "ko",
  batch = 0,
): Promise<{
  suggestions: SpellSuggestion[];
  checked: number;
  cached: number;
  sent: number;
  remaining: number;
}> {
  const r = await fetch(`/api/jobs/${videoId}/spellcheck?lang=${lang}&batch=${batch}`, {
    method: "POST",
  });
  if (!r.ok) {
    let msg = `spellcheck: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
  return r.json();
}

/** 무음 다듬기 v2 — before/segments로 한 번의 undo 지원 (CHG-20260717-094) */
export async function tightenTiming(videoId: string): Promise<{
  tightened: number;
  total: number;
  /** 근거(셀 텍스트 ↔ 들린 말 일치도)가 부족해 건드리지 않은 셀 수 */
  skipped_weak: number;
  /** 되돌리기용 원래 행 전체 (restore-rows가 모든 필드를 덮어쓰므로 부분 행 금지) */
  before: Segment[];
  segments: Segment[];
}> {
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
  edited?: boolean; // human-authored — the batch translator never overwrites it
  has_translation: boolean;
  stale?: boolean; // Korean changed after this translation was made
}

export async function makeTranslations(
  videoId: string,
  lang: string,
  batch = 0, // >0: translate at most this many uncached cues (short request, committed)
): Promise<{ lang: string; translated: number; segments: number; remaining: number; done: boolean }> {
  const r = await fetch(
    `/api/jobs/${videoId}/translate?lang=${lang}${batch > 0 ? `&batch=${batch}` : ""}`,
    { method: "POST" },
  );
  if (!r.ok) {
    // the body may be plain text (e.g. a raw 500) — don't crash parsing it as JSON
    let msg = `translate: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(msg);
  }
  return r.json();
}

// re-translate the clicked cue + the contiguous stale/empty cues around it,
// in one context-aware call (한국어 재분할 뒤 생긴 빈칸·stale 뭉치를 한 번에)
export async function retranslateSegment(
  videoId: string,
  lang: string,
  segmentId: number,
): Promise<{
  updated: { segment_id: number; text: string; reviewed: boolean; stale: boolean }[];
  count: number;
}> {
  const r = await fetch(
    `/api/jobs/${videoId}/retranslate?lang=${lang}&segment_id=${segmentId}`,
    { method: "POST" },
  );
  if (!r.ok) {
    let msg = `retranslate: ${r.status}`;
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* non-JSON */
    }
    throw new Error(msg);
  }
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

export type AbsorbPhase = "all" | "extract" | "repair" | "propagate";

export interface AbsorbResult {
  reviewed_segments: number;
  new_pairs: number;
  bumped: number;
  repaired: number;
  applied: number;
  propagated_segments: number;
  propagated_replacements: number;
  propagation_pairs: number;
  /** 3층(ADR-0011): 사람이 손으로 단 병기를 한자 사전으로 흡수한 결과 */
  hanja_new: number;
  hanja_promoted: number;
  hanja_ambiguous: number;
}

/** phase를 나눠 부르면 UI가 단계별 진행률을 보여줄 수 있다. 전부 더한 결과는
 *  phase="all" 한 번과 같다 (서버가 단계별로 같은 일을 나눠 할 뿐). */
export async function absorbFeedback(
  videoId: string,
  phase: AbsorbPhase = "all",
): Promise<AbsorbResult> {
  const r = await fetch(`/api/jobs/${videoId}/absorb?phase=${phase}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`absorb: ${r.status}`);
  return r.json();
}
