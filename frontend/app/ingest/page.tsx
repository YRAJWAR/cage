"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type MetaStatus, type Site } from "@/lib/api";

type JobStatus = {
  job_id: string;
  status: "PROCESSING" | "COMPLETED" | "FAILED";
  events_written: number;
  error: string | null;
  progress?: number | null;
  stage?: string | null;
  summary?: {
    frames_processed: number;
    frames_with_hazards: number;
    hazard_counts: Record<string, number>;
    detected_classes: string[];
    video_fps: number;
  };
};

export default function IngestPage() {
  const [mode, setMode] = useState<"wall-cam" | "pov">("wall-cam");
  const [siteId, setSiteId] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [meta, setMeta] = useState<MetaStatus | null>(null);
  const [sites, setSites] = useState<Site[]>([]);
  const [newSiteName, setNewSiteName] = useState("");
  const [creatingSite, setCreatingSite] = useState(false);
  const pollRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  useEffect(() => {
    api.meta.status().then(setMeta, () => {});
    api.sites.list().then(
      (list) => {
        const sorted = [...list].sort((a, b) =>
          (b.created_at ?? "").localeCompare(a.created_at ?? "")
        );
        setSites(sorted);
        setSiteId((prev) => prev || sorted[0]?.id || "");
      },
      () => {}
    );
    const timers = pollRef.current;
    return () => Object.values(timers).forEach(clearInterval);
  }, []);

  async function createSite() {
    if (!newSiteName.trim()) return;
    setCreatingSite(true);
    try {
      const site = await api.sites.create({ name: newSiteName.trim() });
      setSites((prev) => [site, ...prev]);
      setSiteId(site.id);
      setNewSiteName("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create site");
    } finally {
      setCreatingSite(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !siteId || !date) return;
    setSubmitting(true);
    setError(null);

    try {
      const form = new FormData();
      form.append("video", file);
      form.append("site_id", siteId);
      form.append("date", date);
      if (workerId.trim()) form.append("worker_id", workerId.trim());

      const { job_id } = await api.process.submit(mode, form);

      const newJob: JobStatus = { job_id, status: "PROCESSING", events_written: 0, error: null };
      setJobs((prev) => [newJob, ...prev]);
      startPolling(job_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  function startPolling(job_id: string) {
    const interval = setInterval(async () => {
      try {
        const data = await api.jobs.get(job_id);
        setJobs((prev) =>
          prev.map((j) =>
            j.job_id === job_id ? { ...j, ...data, summary: data.summary as JobStatus["summary"] } : j
          )
        );
        if (data.status !== "PROCESSING") {
          clearInterval(interval);
          delete pollRef.current[job_id];
        }
      } catch {
        /* keep polling through transient failures */
      }
    }, 2000);
    pollRef.current[job_id] = interval;
  }

  return (
    <div className="animate-in">
      <div className="page-head">
        <div>
          <h1 className="page-title">Ingest footage</h1>
          <p className="page-sub">
            Upload shift video. Detection runs in the background and the report lands in Jobs.
          </p>
        </div>
        <div className="tabs" role="group" aria-label="Camera mode">
          {(["wall-cam", "pov"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              className={`tab${mode === m ? " active" : ""}`}
              aria-pressed={mode === m}
            >
              {m === "wall-cam" ? "Wall camera" : "POV"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid-2" style={{ gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)", alignItems: "start", marginBottom: "16px" }}>
        <form onSubmit={submit} aria-label="New analysis job">
          <div className="sheet">
            <div className="sheet-head">
              <span className="sheet-title">New analysis job</span>
              <span className="sheet-meta">{mode === "wall-cam" ? "fixed camera" : "body worn camera"}</span>
            </div>
            <div className="title-block" style={{ border: "none" }}>
              <div className="title-cell">
                <label className="field-label" htmlFor="ingest-site">Site</label>
                {sites.length === 0 ? (
                  <div style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                    No sites yet. Create one below, then pick it here.
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: "8px" }}>
                    <select
                      id="ingest-site"
                      className="field"
                      value={siteId}
                      onChange={(e) => setSiteId(e.target.value)}
                      style={{ flex: 1 }}
                      aria-required="true"
                    >
                      {sites.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}{s.location ? `, ${s.location}` : ""} ({s.id.slice(0, 8)})
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn"
                      title="Refresh site list"
                      onClick={() => {
                        api.sites.list().then(
                          (list) => {
                            const sorted = [...list].sort((a, b) =>
                              (b.created_at ?? "").localeCompare(a.created_at ?? "")
                            );
                            setSites(sorted);
                            setSiteId((prev) => prev || sorted[0]?.id || "");
                          },
                          () => {}
                        );
                      }}
                      aria-label="Refresh site list"
                    >
                      Refresh
                    </button>
                  </div>
                )}
                <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                  <input
                    className="field"
                    type="text"
                    value={newSiteName}
                    onChange={(e) => setNewSiteName(e.target.value)}
                    placeholder="Format: Riverside site"
                    aria-label="New site name"
                    autoComplete="off"
                  />
                  <button
                    type="button"
                    onClick={createSite}
                    disabled={creatingSite || !newSiteName.trim()}
                    className="btn"
                    style={{ flexShrink: 0 }}
                  >
                    {creatingSite ? "Adding" : "Add site"}
                  </button>
                </div>
              </div>
              <div className="title-cell">
                <label className="field-label" htmlFor="ingest-date">Shift date</label>
                <input
                  id="ingest-date"
                  className="field"
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  aria-required="true"
                />
                <div style={{ marginTop: "16px" }}>
                  <label className="field-label" htmlFor="ingest-worker">
                    Worker ID <span style={{ fontWeight: 400, color: "var(--color-muted)" }}>(optional, resolved or created)</span>
                  </label>
                  <input
                    id="ingest-worker"
                    className="field num"
                    type="text"
                    value={workerId}
                    onChange={(e) => setWorkerId(e.target.value)}
                    placeholder="Format: worker UUID or W-001"
                    autoComplete="off"
                  />
                </div>
              </div>
              <div className="title-cell wide">
                <span className="field-label" id="video-label">Video file</span>
                <label className="dropzone" htmlFor="ingest-video">
                  <input
                    id="ingest-video"
                    type="file"
                    accept="video/*,.mp4,.mov,.avi"
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    aria-labelledby="video-label"
                    aria-required="true"
                  />
                  <span style={{ pointerEvents: "none", display: "block" }}>
                    {file ? (
                      <span>
                        <span style={{ fontSize: "16px", color: "var(--color-ink)", fontWeight: 500, display: "block" }}>{file.name}</span>
                        <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                          {(file.size / 1e6).toFixed(1)} MB
                        </span>
                      </span>
                    ) : (
                      <span>
                        <span style={{ fontSize: "16px", display: "block" }}>Drop video or click to browse</span>
                        <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                          MP4, MOV, AVI
                        </span>
                      </span>
                    )}
                  </span>
                </label>
              </div>
            </div>
            <div style={{ padding: "16px", borderTop: "1px solid var(--color-rule-2)" }}>
              {error && (
                <div className="alert alert-error" role="alert" style={{ marginBottom: "12px" }}>
                  Upload failed: {error}. Check that the backend is running and the site exists.
                </div>
              )}
              <button type="submit" disabled={submitting || !file || !siteId} className="btn btn-primary">
                {submitting ? (
                  <>
                    <span className="spinner" style={{ borderTopColor: "var(--color-accent-ink)" }} />
                    Uploading
                  </>
                ) : "Run safety analysis"}
              </button>
            </div>
          </div>
        </form>

        <section className="sheet" aria-label="Pipeline stages">
          <div className="sheet-head">
            <span className="sheet-title">What runs on upload</span>
            <span className="sheet-meta">live backend config</span>
          </div>
          <div className="run">
            <div className="run-step">
              <div className="run-no">01</div>
              <div>
                <div className="run-name">YOLO detection and tracking</div>
                <div className="run-desc">Workers, PPE items and violation candidates, tracked across frames. Always local.</div>
              </div>
            </div>
            <div className="run-step">
              <div className="run-no">02</div>
              <div>
                <div className="run-name">SAM 3.1 segmentation</div>
                <div className="run-desc">
                  {meta === null
                    ? "Checking backend."
                    : meta.sam_backend === "meta"
                      ? `Refines flagged frames with ${meta.sam_model} on api.meta.ai.`
                      : "Local SAM weights refine masks and boxes. Set SAM_BACKEND to meta to use the API."}
                </div>
              </div>
            </div>
            <div className="run-step">
              <div className="run-no">03</div>
              <div>
                <div className="run-name">VLM verification</div>
                <div className="run-desc">
                  {meta === null
                    ? "Checking backend."
                    : meta.vlm_backend === "meta"
                      ? `Assesses each hazard window with ${meta.vision_model} on api.meta.ai.`
                      : "Local Qwen3-VL verifies each hazard window. Set VLM_BACKEND to meta to use the API."}
                </div>
              </div>
            </div>
            <div className="run-step">
              <div className="run-no">04</div>
              <div>
                <div className="run-name">Report</div>
                <div className="run-desc">Events land in the database and a per-shift report is ready in Jobs.</div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {jobs.length > 0 && (
        <div>
          <h2 className="section-title" style={{ marginBottom: "8px" }}>Session jobs</h2>
          <div className="stack">
            {jobs.map((job) => (
              <JobCard key={job.job_id} job={job} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function JobCard({ job }: { job: JobStatus }) {
  const inner = (
    <>
      <div style={{ padding: "12px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px" }}>
        <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
          {job.job_id.slice(0, 18)}
        </span>
        {job.status === "PROCESSING" ? (
          <span className="tag tag-warn">{job.stage ?? "Processing"}</span>
        ) : (
          <span className={`tag ${job.status === "COMPLETED" ? "tag-ok" : "tag-bad"}`}>{job.status === "COMPLETED" ? "Completed" : "Failed"}</span>
        )}
      </div>

      {job.status === "PROCESSING" && (
        <div style={{ padding: "0 16px 12px" }}>
          <div className="meter warn">
            <span style={{ "--fill": job.progress ?? 0 } as React.CSSProperties} />
          </div>
        </div>
      )}

      {job.status === "FAILED" && (
        <div className="num" style={{ padding: "0 16px 12px", fontSize: "14px", color: "var(--color-bad)" }}>
          {job.error ?? "Processing failed."}
        </div>
      )}

      {job.status === "COMPLETED" && job.summary && (
        <div className="num" style={{ borderTop: "1px solid var(--color-rule-2)", padding: "12px 16px", display: "flex", gap: "24px", fontSize: "14px", color: "var(--color-muted)" }}>
          <span><strong style={{ color: "var(--color-ink)" }}>{job.summary.frames_processed}</strong> frames</span>
          <span><strong style={{ color: "var(--color-warn)" }}>{job.summary.frames_with_hazards}</strong> hazard</span>
          <span><strong style={{ color: "var(--color-ink)" }}>{job.summary.detected_classes.length}</strong> classes</span>
        </div>
      )}

      {job.status === "COMPLETED" && (
        <div style={{ borderTop: "1px solid var(--color-rule-2)", padding: "12px 16px", fontSize: "14px", color: "var(--color-ink)", fontWeight: 500 }}>
          Open full report
        </div>
      )}
    </>
  );

  if (job.status === "COMPLETED") {
    return (
      <Link href={`/jobs/${job.job_id}`} style={{ textDecoration: "none" }} className="sheet">
        {inner}
      </Link>
    );
  }
  return <div className="sheet">{inner}</div>;
}
