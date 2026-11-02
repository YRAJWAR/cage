"use client";

import { Fragment, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, type Job as JobStatus, type MetaSamFrame } from "@/lib/api";

type EventMetadata = {
  explanation?: string;
  recommendation?: string;
  scene_summary?: string;
  reasoning?: string;
  confidence?: string;
  ppe_per_worker?: unknown[];
  event_start_ts?: number;
  event_end_ts?: number;
  event_duration_s?: number;
  event_frame_count?: number;
  yolo_hazard_types?: string[];
  hazard_type?: string;
  description?: string;
  ppe_worn?: string[];
  ppe_missing?: string[];
  track_id?: number;
};

type Event = {
  event_id: string;
  worker_id: string;
  camera_source: string;
  violation_type: string | null;
  severity: string | null;
  video_timestamp: number;
  clip_path: string | null;
  metadata: EventMetadata | null;
  created_at: string;
};

type Shift = {
  shift_id: string;
  worker_id: string;
  date: string;
  status: string;
  violation_count: number;
  compliant_count: number;
  events: Event[];
};

type VlmHazard = {
  violation_type?: string;
  severity?: string;
  explanation?: string;
  recommendation?: string;
  best_frame_path?: string | null;
};

type VlmChunk = {
  event?: {
    representative_frame_path?: string;
    representative_timestamp?: number;
    start_ts?: number;
  };
  vlm?: { hazards?: VlmHazard[] };
};

type JobResults = {
  summary: JobStatus["summary"];
  vlm_results: unknown[];
  posture_summary?: {
    events?: number;
    frames_sampled?: number;
    total_frames?: number;
  };
  posture_events?: unknown[];
  posture_vlm?: VlmChunk[];
  meta_sam?: MetaSamFrame[];
};

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [shift, setShift] = useState<Shift | null>(null);
  const [results, setResults] = useState<JobResults | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const [aiModel, setAiModel] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadOnce() {
      try {
        const j: JobStatus = await api.jobs.get(jobId);
        if (cancelled) return;
        setJob(j);

        if (j.status === "COMPLETED" && j.shift_id) {
          const [s, r] = await Promise.all([
            api.shifts.get(j.shift_id).catch(() => null),
            api.jobs.results(jobId).catch(() => null),
          ]);
          if (cancelled) return;
          if (s) setShift(s as Shift);
          if (r) setResults(r as JobResults);
        }

        if (j.status === "COMPLETED" || j.status === "FAILED") {
          if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
        }
      } catch {
        if (!cancelled) setLoading(false);
        return;
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadOnce();
    timerRef.current = setInterval(loadOnce, 1500);

    return () => {
      cancelled = true;
      if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    };
  }, [jobId]);

  if (loading) {
    return (
      <div className="animate-in">
        <div className="page-head">
          <div>
            <h1 className="page-title">Shift report</h1>
            <p className="page-sub">Loading the filing.</p>
          </div>
        </div>
        <section className="sheet" aria-label="Loading report">
          <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <span className="skel" style={{ width: "60%" }} />
            <span className="skel" style={{ width: "85%" }} />
            <span className="skel" style={{ width: "45%" }} />
          </div>
        </section>
      </div>
    );
  }
  if (!job) {
    return (
      <div className="alert alert-error" style={{ marginTop: "40px" }} role="alert">
        Error: job not found. It may have belonged to a previous backend session.
      </div>
    );
  }

  const summary = job.summary;
  const resultSummary = results?.summary ?? summary;
  const progress = job.progress ?? (job.status === "COMPLETED" ? 1 : 0);
  const stage = job.stage ?? (job.status === "COMPLETED" ? "completed" : job.status.toLowerCase());
  const shiftId = shift?.shift_id ?? job.shift_id;

  async function loadAiSummary() {
    if (!shiftId || aiLoading) return;
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await api.reports.shiftSummary(shiftId);
      setAiSummary(res.summary);
      setAiModel(res.model);
    } catch (err: unknown) {
      setAiError(err instanceof Error ? err.message : "Summary failed");
    } finally {
      setAiLoading(false);
    }
  }

  const hazardEntries = resultSummary ? Object.entries(resultSummary.hazard_counts) : [];
  const hazardTotal = hazardEntries.reduce((a, [, b]) => a + b, 0);
  const hazardMax = Math.max(1, ...hazardEntries.map(([, b]) => b));
  const postureFindings = (results?.posture_vlm ?? []).flatMap((chunk, idx) =>
    (chunk.vlm?.hazards ?? []).map((hz, i) => ({ chunk, hz, key: `${idx}-${i}` }))
  );

  return (
    <div className="animate-in stack" style={{ gap: "16px" }}>
      <div>
        <div style={{ marginBottom: "16px" }}>
          <Link href="/jobs" style={{ fontSize: "14px", fontWeight: 500 }}>
            Back to Jobs
          </Link>
          <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)", marginLeft: "12px" }}>
            {jobId.slice(0, 20)}
          </span>
        </div>
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div>
            <h1 className="page-title">Shift report</h1>
            <p className="page-sub">
              {shift ? `${shift.date}. ` : ""}{job.camera_source ?? "Unknown camera"}
              {shift ? `. ${shift.violation_count} violations, ${shift.compliant_count} compliant.` : ""}
            </p>
          </div>
          <StatusTag status={job.status} />
        </div>
      </div>

      {job.status === "PROCESSING" && (
        <section className="sheet" aria-label="Processing progress">
          <div className="sheet-body">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "8px" }}>
              <span style={{ fontSize: "16px", fontWeight: 500 }}>{stage}</span>
              <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                {Math.round(progress * 100)} percent
              </span>
            </div>
            <div className="meter warn">
              <span style={{ "--fill": Math.max(progress, 0.03) } as React.CSSProperties} />
            </div>
          </div>
        </section>
      )}

      {job.status === "FAILED" && (
        <div className="alert alert-error" role="alert">
          <strong>Pipeline error.</strong>
          <pre className="code" style={{ marginTop: "8px", whiteSpace: "pre-wrap" }}>{job.error}</pre>
        </div>
      )}

      {resultSummary && (
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="sheet" aria-label="Filing figures">
            <div className="sheet-head">
              <span className="sheet-title">Filing</span>
            </div>
            <div className="kv">
              <div className="kv-row"><span className="kv-term">Frames processed</span><span className="kv-val">{resultSummary.frames_processed}</span></div>
              <div className="kv-row"><span className="kv-term">Hazard frames</span><span className="kv-val">{resultSummary.frames_with_hazards}</span></div>
              <div className="kv-row"><span className="kv-term">Workers tracked</span><span className="kv-val">{resultSummary.workers_tracked}</span></div>
              <div className="kv-row"><span className="kv-term">Events written</span><span className="kv-val">{job.events_written}</span></div>
            </div>
          </section>

          <section className="sheet" aria-label="Hazard breakdown">
            <div className="sheet-head">
              <span className="sheet-title">Hazards</span>
              <span className="sheet-meta num">{hazardTotal} detections</span>
            </div>
            {hazardEntries.length === 0 ? (
              <div className="empty"><p>No hazards detected.</p></div>
            ) : (
              <div style={{ padding: "8px 0" }}>
                {hazardEntries.map(([k, v]) => (
                  <div key={k} style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 96px 48px", gap: "12px", alignItems: "center", padding: "8px 16px" }}>
                    <span style={{ fontSize: "16px", color: "var(--color-muted)" }}>{k.replace(/_/g, " ")}</span>
                    <span className="meter warn" style={{ display: "block" }}>
                      <span style={{ "--fill": v / hazardMax } as React.CSSProperties} />
                    </span>
                    <span className="num" style={{ fontSize: "16px", textAlign: "right" }}>{v}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {results?.posture_summary && (
        <section className="sheet" aria-label="Posture analysis">
          <div className="sheet-head">
            <span className="sheet-title">Posture analysis</span>
            <span className="sheet-meta">REBA inspired ergonomic risk</span>
          </div>
          <div className="kv" style={{ borderBottom: "1px solid var(--color-rule-2)" }}>
            <div className="kv-row">
              <span className="kv-term">Risk frames</span>
              <span className="kv-val" style={{ color: (results.posture_summary.events ?? 0) > 0 ? "var(--color-bad)" : "var(--color-ok)" }}>
                {results.posture_summary.events ?? 0}
              </span>
            </div>
            <div className="kv-row"><span className="kv-term">Frames sampled</span><span className="kv-val">{results.posture_summary.frames_sampled ?? "unknown"}</span></div>
            <div className="kv-row"><span className="kv-term">Total frames</span><span className="kv-val">{results.posture_summary.total_frames ?? "unknown"}</span></div>
          </div>
          {postureFindings.length > 0 && (
            <div>
              {postureFindings.map(({ chunk, hz, key }) => {
                const frame = hz.best_frame_path || chunk.event?.representative_frame_path;
                const ts = chunk.event?.representative_timestamp ?? chunk.event?.start_ts ?? 0;
                return (
                  <div key={key} style={{ display: "grid", gridTemplateColumns: frame ? "minmax(0, 1fr) 176px" : "minmax(0, 1fr)", gap: "16px", padding: "16px", borderBottom: "1px solid var(--color-rule-2)", alignItems: "start" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px", flexWrap: "wrap" }}>
                        <span className="tag">{hz.violation_type?.replace(/_/g, " ") ?? "finding"}</span>
                        {hz.severity && <SeverityTag severity={hz.severity} />}
                        <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>t {ts.toFixed(1)}s</span>
                      </div>
                      {hz.explanation && (
                        <p style={{ fontSize: "16px", color: "var(--color-ink-2)", margin: "0 0 8px", lineHeight: 1.6 }}>{hz.explanation}</p>
                      )}
                      {hz.recommendation && (
                        <p style={{ fontSize: "16px", color: "var(--color-critical)", margin: 0, lineHeight: 1.6 }}>{hz.recommendation}</p>
                      )}
                    </div>
                    {frame && (
                      <figure className="figure" style={{ margin: 0 }}>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={api.jobs.frameUrl(jobId, frame)}
                          alt="Posture frame"
                        />
                      </figure>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {resultSummary && Object.keys(resultSummary.worker_compliance ?? {}).length > 0 && (
        <section className="sheet" aria-label="PPE compliance">
          <div className="sheet-head">
            <span className="sheet-title">PPE compliance</span>
          </div>
          <table className="register">
            <thead>
              <tr>
                <th scope="col">Track</th>
                <th scope="col">Verdict</th>
                <th scope="col">Items</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(resultSummary.worker_compliance).map(([tid, c]) => (
                <tr key={tid}>
                  <td className="stage-no">Track {tid}</td>
                  <td>
                    <span className={`tag ${c.compliant ? "tag-ok" : "tag-bad"}`}>
                      {c.compliant ? "Compliant" : "Violation"}
                    </span>
                  </td>
                  <td>
                    <span style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                      {c.ppe_confirmed.map((p) => (
                        <span key={p} className="tag tag-ok">{p}</span>
                      ))}
                      {c.ppe_missing.map((p) => (
                        <span key={p} className="tag tag-bad">no {p}</span>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {shift && (
        <section className="sheet" aria-label="Safety events">
          <div className="sheet-head">
            <span className="sheet-title">Safety events</span>
            <span className="sheet-meta num">{shift.events.length} recorded</span>
          </div>
          {shift.events.length === 0 ? (
            <div className="empty"><p>No events recorded for this shift.</p></div>
          ) : (
            <table className="register">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Violation</th>
                  <th scope="col">Track</th>
                  <th scope="col">Range</th>
                  <th scope="col"><span className="visually-hidden">Details</span></th>
                </tr>
              </thead>
              <tbody>
                {shift.events.map((e) => (
                  <Fragment key={e.event_id}>
                    <tr className="link" onClick={() => setExpanded(expanded === e.event_id ? null : e.event_id)} aria-expanded={expanded === e.event_id} style={{ cursor: "pointer" }}>
                      <td className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                        {e.video_timestamp.toFixed(2)}s
                      </td>
                      <td><SeverityTag severity={e.severity} /></td>
                      <td className="row-title">
                        {e.violation_type?.replace(/_/g, " ") ?? "Not classified"}
                      </td>
                      <td className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                        {e.metadata?.track_id != null ? `Track ${e.metadata.track_id}` : "Not tracked"}
                      </td>
                      <td className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                        {e.metadata?.event_start_ts != null
                          ? `${e.metadata.event_start_ts.toFixed(1)} to ${e.metadata.event_end_ts?.toFixed(1)}s`
                          : "Not ranged"}
                      </td>
                      <td style={{ fontSize: "14px", color: "var(--color-muted)", textAlign: "right" }}>
                        {expanded === e.event_id ? "Hide" : "Show"}
                      </td>
                    </tr>
                    {expanded === e.event_id && (
                      <tr key={`${e.event_id}-detail`}>
                        <td colSpan={6} style={{ background: "var(--color-paper-2)", padding: "16px" }}>
                          <div className="stack">
                            {e.clip_path && (
                              <div>
                                <h3 className="section-title">Flagged frame</h3>
                                <figure className="figure" style={{ margin: 0, maxWidth: "480px" }}>
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img
                                    src={api.jobs.frameUrl(jobId, e.clip_path)}
                                    alt="Flagged frame"
                                  />
                                </figure>
                              </div>
                            )}

                            {e.metadata?.explanation && (
                              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: "16px" }}>
                                <div>
                                  <h3 className="section-title">Explanation</h3>
                                  <p style={{ fontSize: "16px", lineHeight: 1.6, margin: 0, color: "var(--color-ink-2)" }}>{e.metadata.explanation}</p>
                                </div>
                                {e.metadata.recommendation && (
                                  <div>
                                    <h3 className="section-title">Recommendation</h3>
                                    <p style={{ fontSize: "16px", lineHeight: 1.6, margin: 0, color: "var(--color-critical)" }}>{e.metadata.recommendation}</p>
                                  </div>
                                )}
                              </div>
                            )}

                            {(e.metadata?.ppe_worn?.length || e.metadata?.ppe_missing?.length) ? (
                              <div>
                                <h3 className="section-title">PPE status</h3>
                                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                  {e.metadata?.ppe_worn?.map((p) => (
                                    <span key={p} className="tag tag-ok">{p}</span>
                                  ))}
                                  {e.metadata?.ppe_missing?.map((p) => (
                                    <span key={p} className="tag tag-bad">missing {p}</span>
                                  ))}
                                </div>
                              </div>
                            ) : null}

                            {e.metadata?.yolo_hazard_types && e.metadata.yolo_hazard_types.length > 0 && (
                              <div>
                                <h3 className="section-title">YOLO triggers</h3>
                                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                                  {e.metadata.yolo_hazard_types.map((h) => (
                                    <span key={h} className="tag num">{h}</span>
                                  ))}
                                </div>
                              </div>
                            )}

                            <details className="reg">
                              <summary>Raw metadata</summary>
                              <pre className="code" style={{ marginTop: "8px" }}>
                                {JSON.stringify(e.metadata, null, 2)}
                              </pre>
                            </details>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {results?.meta_sam && results.meta_sam.length > 0 && (
        <section className="sheet" aria-label="Meta SAM refinement">
          <div className="sheet-head">
            <span className="sheet-title">Meta SAM 3.1 refinement</span>
            <span className="sheet-meta num">{results.meta_sam.length} frames</span>
          </div>
          <table className="register">
            <thead>
              <tr>
                <th scope="col">Frame</th>
                <th scope="col">Boxes</th>
                <th scope="col">Masks</th>
              </tr>
            </thead>
            <tbody>
              {results.meta_sam.map((f, i) => (
                <tr key={f.frame ?? i}>
                  <td className="num" style={{ fontSize: "14px" }}>
                    {f.frame ?? `frame ${i}`}
                    {f.timestamp_seconds !== undefined && (
                      <span style={{ color: "var(--color-muted)", marginLeft: "8px" }}>t {f.timestamp_seconds}s</span>
                    )}
                  </td>
                  <td className="num">
                    {f.error ? <span style={{ color: "var(--color-bad)" }}>error</span> : `${f.box_count ?? (f.boxes?.length ?? 0)}`}
                  </td>
                  <td className="num" style={{ color: "var(--color-muted)" }}>
                    {f.error ? "none" : `${f.mask_count ?? (f.masks?.length ?? 0)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {job.status === "COMPLETED" && shiftId && (
        <section className="sheet" aria-label="AI shift brief">
          <div className="sheet-head">
            <span className="sheet-title">AI shift brief</span>
            {aiModel
              ? <span className="sheet-meta num">{aiModel}</span>
              : <button onClick={loadAiSummary} disabled={aiLoading} className="btn">
                  {aiLoading ? "Generating" : "Generate brief"}
                </button>}
          </div>
          <div className="sheet-body">
            {aiLoading && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-muted)", fontSize: "16px" }}>
                <span className="spinner" /> Asking Meta AI
              </div>
            )}
            {aiError && (
              <div className="alert alert-error" role="alert">
                {aiError.includes("503")
                  ? "Error: MODEL_API_KEY is not configured on the backend. Add it to backend/.env and retry."
                  : `Error: brief failed (${aiError})`}
              </div>
            )}
            {!aiLoading && !aiError && !aiSummary && (
              <div style={{ fontSize: "16px", color: "var(--color-muted)" }}>
                Generate a safety manager style brief for this shift. Requires MODEL_API_KEY on the backend.
              </div>
            )}
            {aiSummary && (
              <div style={{ fontSize: "16px", lineHeight: 1.75, whiteSpace: "pre-wrap", maxWidth: "75ch" }}>
                {aiSummary}
              </div>
            )}
          </div>
        </section>
      )}

      {resultSummary && resultSummary.detected_classes.length > 0 && (
        <section className="sheet" aria-label="Detected classes">
          <div className="sheet-head">
            <span className="sheet-title">Detected classes</span>
            <span className="sheet-meta num">{resultSummary.detected_classes.length}</span>
          </div>
          <div className="sheet-body" style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {resultSummary.detected_classes.map((c) => (
              <span key={c} className="tag num">{c}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function StatusTag({ status }: { status: string }) {
  if (status === "COMPLETED") return <span className="tag tag-ok">Completed</span>;
  if (status === "FAILED") return <span className="tag tag-bad">Failed</span>;
  return <span className="tag tag-warn">Processing</span>;
}

function SeverityTag({ severity }: { severity: string | null }) {
  if (severity === "CRITICAL") return <span className="tag tag-critical">Critical</span>;
  if (severity === "HIGH") return <span className="tag tag-bad">High</span>;
  if (severity === "MEDIUM") return <span className="tag tag-warn">Medium</span>;
  return <span className="tag">Low</span>;
}
