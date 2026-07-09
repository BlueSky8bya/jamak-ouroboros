export interface JobSummary {
  video_id: string;
  title: string;
  duration_seconds: number;
  status: string;
  segments: number;
  reviewed: number;
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
}

export type Filter = "all" | "flagged" | "unreviewed";
