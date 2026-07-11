export interface JobLang {
  code: string;
  label: string;
  translated: number;
  reviewed: number;
  complete: boolean;
  forked: boolean; // has its own Segment rows (independent structure/timing)
  timing_done: boolean; // per-track timing pass (forked tracks only)
}

export interface JobSummary {
  video_id: string;
  title: string;
  duration_seconds: number;
  status: string;
  segments: number;
  reviewed: number;
  ko_complete: boolean;
  timing_done: boolean; // human-confirmed timing pass (separate from text review)
  languages: JobLang[];
  created_at: string;
  upload_date: string; // YouTube upload date YYYYMMDD ('' if unknown)
  running: boolean;
  srt_undo?: boolean; // an applied .srt import can be reverted
}

export interface Segment {
  id: number;
  job_id: number;
  idx: number;
  start: number;
  end: number;
  text_whisper: string;
  text_youtube: string;
  text_llm: string;
  text_final: string;
  flagged: boolean;
  llm_uncertain: boolean;
  reviewed: boolean;
  safe?: boolean; // low-risk: both engines agree, no domain term, comfortable speed
  low_conf?: string; // whisper's least-confident words (fallback when no YouTube)
  suspect?: string; // words to double-check: whisper↔YouTube disagreement (2-engine)
  too_fast?: boolean; // reading speed above the comfortable CPS limit
}
