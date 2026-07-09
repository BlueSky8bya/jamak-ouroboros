export interface JobLang {
  code: string;
  label: string;
  translated: number;
  reviewed: number;
  complete: boolean;
}

export interface JobSummary {
  video_id: string;
  title: string;
  duration_seconds: number;
  status: string;
  segments: number;
  reviewed: number;
  ko_complete: boolean;
  languages: JobLang[];
  created_at: string;
  upload_date: string; // YouTube upload date YYYYMMDD ('' if unknown)
  running: boolean;
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
