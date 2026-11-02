export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

function postForm<T>(path: string, form: FormData): Promise<T> {
  return fetch(`${API_BASE_URL}${path}`, { method: "POST", body: form }).then(
    async (res) => {
      if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
      return res.json();
    }
  );
}

export const api = {
  health: () => apiFetch<{ status: string }>("/health"),

  sites: {
    list: () => apiFetch<Site[]>("/sites"),
    create: (payload: { name: string; location?: string }) =>
      apiFetch<Site>("/sites", { method: "POST", body: JSON.stringify(payload) }),
  },

  devices: {
    list: (siteId: string) => apiFetch<Device[]>(`/devices?site_id=${siteId}`),
    register: (payload: { label: string; site_id: string }) =>
      apiFetch<Device>("/devices", { method: "POST", body: JSON.stringify(payload) }),
  },

  workers: {
    list: (siteId: string) => apiFetch<Worker[]>(`/workers?site_id=${siteId}`),
    get: (workerId: string) => apiFetch<Worker>(`/workers/${workerId}`),
    register: (payload: {
      site_id: string;
      display_name?: string;
      appearance_embedding?: string;
    }) =>
      apiFetch<{ worker_id: string }>("/workers/register", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    checkin: (payload: { worker_id: string; pov_device_id: string; date: string }) =>
      apiFetch<Shift>("/workers/checkin", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },

  shifts: {
    get: (shiftId: string) => apiFetch<Shift>(`/shifts/${shiftId}`),
    close: (shiftId: string, payload: { msd_risk_score?: number } = {}) =>
      apiFetch<Shift>(`/shifts/${shiftId}/close`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      }),
  },

  events: {
    list: (params: { workerId?: string; shiftId?: string; eventCategory?: string }) => {
      const q = new URLSearchParams();
      if (params.workerId) q.set("worker_id", params.workerId);
      if (params.shiftId) q.set("shift_id", params.shiftId);
      if (params.eventCategory) q.set("event_category", params.eventCategory);
      return apiFetch<SafetyEvent[]>(`/events?${q}`);
    },
    ingest: (payload: {
      shift_id: string;
      worker_id: string;
      camera_source: "POV" | "WALL_CAM";
      event_category: "VIOLATION" | "COMPLIANT";
      violation_type?: string;
      severity?: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
      video_timestamp?: number;
      clip_path?: string;
      metadata?: Record<string, unknown>;
    }) =>
      apiFetch<SafetyEvent>("/events/ingest", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },

  process: {
    submit: (mode: "pov" | "wall-cam", form: FormData) =>
      postForm<{ job_id: string; status: string }>(`/process/${mode}`, form),
  },

  jobs: {
    list: () => apiFetch<JobEntry[]>("/jobs"),
    get: (jobId: string) => apiFetch<Job>(`/jobs/${jobId}`),
    results: (jobId: string) => apiFetch<JobResults>(`/jobs/${jobId}/results`),
    vlm: (jobId: string) => apiFetch<unknown[]>(`/jobs/${jobId}/vlm`),
    frameUrl: (jobId: string, filename: string) =>
      `${API_BASE_URL}/jobs/${jobId}/frames/${filename}`,
  },

  reports: {
    shiftSummary: (shiftId: string) =>
      apiFetch<ShiftSummary>(`/reports/shifts/${shiftId}/summary`),
  },

  meta: {
    status: () => apiFetch<MetaStatus>("/meta/status"),
    models: () => apiFetch<{ models: string[] }>("/meta/models"),
    segment: (form: FormData) => postForm<SegmentResult>("/meta/segment", form),
  },
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Site {
  id: string;
  name: string;
  location: string | null;
  created_at: string | null;
}

export interface Device {
  id: string;
  label: string;
  site_id: string;
  created_at: string | null;
}

export interface Worker {
  worker_id: string;
  display_name: string | null;
  site_id?: string | null;
  status: "ACTIVE" | "INACTIVE";
  total_violations: number;
  total_compliant: number;
  avg_msd_risk: number;
  created_at?: string | null;
  last_seen_at: string | null;
}

export interface Shift {
  shift_id: string;
  worker_id: string;
  site_id?: string | null;
  date: string;
  status: "IN_PROGRESS" | "COMPLETED";
  pov_device_id?: string | null;
  msd_risk_score: number | null;
  violation_count: number;
  compliant_count: number;
  started_at?: string | null;
  ended_at?: string | null;
  events: SafetyEvent[];
}

export interface SafetyEvent {
  event_id: string;
  shift_id: string;
  worker_id: string;
  camera_source: "POV" | "WALL_CAM";
  event_category: "VIOLATION" | "COMPLIANT";
  violation_type: string | null;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
  video_timestamp: number;
  clip_path: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface Job {
  job_id: string;
  status: "PROCESSING" | "COMPLETED" | "FAILED";
  events_written: number;
  error: string | null;
  camera_source: string | null;
  progress?: number | null;
  stage?: string | null;
  shift_id?: string;
  summary?: {
    frames_processed: number;
    frames_with_hazards: number;
    workers_tracked: number;
    hazard_counts: Record<string, number>;
    detected_classes: string[];
    worker_compliance: Record<
      string,
      { ppe_confirmed: string[]; ppe_missing: string[]; compliant: boolean }
    >;
  };
}

export interface JobEntry {
  job_id: string;
  status: "PROCESSING" | "COMPLETED" | "FAILED";
  events_written: number;
  error: string | null;
  camera_source: string | null;
  progress?: number | null;
  stage?: string | null;
  shift?: {
    shift_id: string;
    date: string;
    worker_id: string;
    worker: string | null;
    site: string | null;
    violation_count: number;
    event_count: number;
    status: string;
    started_at: string;
    ended_at: string | null;
  };
}

export interface JobResults {
  job_id: string;
  summary: Job["summary"];
  vlm_results: unknown[];
  posture_summary: Record<string, unknown> & {
    events?: number;
    frames_sampled?: number;
    total_frames?: number;
  };
  posture_events: unknown[];
  posture_vlm: unknown[];
  meta_sam: MetaSamFrame[];
}

export interface MetaSamFrame {
  frame?: string;
  timestamp_seconds?: number;
  box_count?: number;
  mask_count?: number;
  boxes?: unknown[];
  masks?: unknown[];
  error?: string;
}

export interface MetaStatus {
  configured: boolean;
  base_url: string;
  sam_model: string;
  vision_model: string;
  text_model: string;
  vlm_backend: "local" | "meta";
  sam_backend: "local" | "meta";
}

export interface SegmentResult {
  model: string;
  boxes: unknown[];
  masks: unknown[];
  raw?: unknown;
}

export interface ShiftSummary {
  shift_id: string;
  model: string;
  summary: string;
}
