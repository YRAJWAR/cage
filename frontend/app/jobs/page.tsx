"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type JobEntry as Job } from "@/lib/api";

type Filter = "ALL" | "PROCESSING" | "COMPLETED" | "FAILED";

const FILTERS: Filter[] = ["ALL", "PROCESSING", "COMPLETED", "FAILED"];
const FILTER_LABEL: Record<Filter, string> = {
  ALL: "All",
  PROCESSING: "Processing",
  COMPLETED: "Completed",
  FAILED: "Failed",
};

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("ALL");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const list = await api.jobs.list();
        if (!cancelled) setJobs(list);
      } catch {
        /* keep previous jobs on poll failure */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    const t = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const counts: Record<Filter, number> = {
    ALL: jobs.length,
    PROCESSING: jobs.filter((j) => j.status === "PROCESSING").length,
    COMPLETED: jobs.filter((j) => j.status === "COMPLETED").length,
    FAILED: jobs.filter((j) => j.status === "FAILED").length,
  };
  const visible = filter === "ALL" ? jobs : jobs.filter((j) => j.status === filter);

  return (
    <div className="animate-in">
      <div className="page-head">
        <div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-sub">Every analysis run, newest activity first. Refreshes automatically.</p>
        </div>
        <div className="tabs" role="group" aria-label="Filter jobs by status">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`tab${filter === f ? " active" : ""}`}
              aria-pressed={filter === f}
            >
              {FILTER_LABEL[f]}
              <span className="count">{counts[f]}</span>
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <section className="sheet" aria-label="Loading jobs">
          <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <span className="skel" style={{ width: "80%" }} />
            <span className="skel" style={{ width: "60%" }} />
            <span className="skel" style={{ width: "75%" }} />
          </div>
        </section>
      )}

      {!loading && visible.length === 0 && (
        <section className="sheet">
          <div className="empty">
            {filter === "ALL" ? (
              <p>No jobs yet. Upload a video from Ingest to start the first analysis.</p>
            ) : (
              <p>No {FILTER_LABEL[filter].toLowerCase()} jobs right now.</p>
            )}
            {filter === "ALL" && <Link href="/ingest" className="btn btn-primary">Open ingest</Link>}
          </div>
        </section>
      )}

      {visible.length > 0 && (
        <section className="sheet" aria-label="Job register">
          <table className="register">
            <thead>
              <tr>
                <th scope="col">No.</th>
                <th scope="col">Shift</th>
                <th scope="col">Camera</th>
                <th scope="col">Events</th>
                <th scope="col">Violations</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((job, i) => (
                <tr key={job.job_id} className="link">
                  <td className="stage-no">{String(i + 1).padStart(2, "0")}</td>
                  <td>
                    <Link href={`/jobs/${job.job_id}`} style={{ textDecoration: "none" }}>
                      <span className="row-title">{job.shift ? `${job.shift.site ?? "Unknown site"}, ${job.shift.date}` : "Unassigned footage"}</span>
                      <span className="num" style={{ display: "block", fontSize: "14px", color: "var(--color-muted)" }}>
                        {job.job_id.slice(0, 12)}{job.shift ? `, ${shortWorker(job.shift.worker_id)}` : ""}
                      </span>
                    </Link>
                  </td>
                  <td>
                    {job.camera_source ? <span className="tag">{job.camera_source}</span> : <span style={{ color: "var(--color-muted)" }}>Not set</span>}
                  </td>
                  <td className="num">{job.shift?.event_count ?? "—"}</td>
                  <td
                    className="num"
                    style={{
                      fontWeight: 500,
                      color: (job.shift?.violation_count ?? 0) > 0 ? "var(--color-critical)" : "var(--color-muted)",
                    }}
                  >
                    {job.shift?.violation_count ?? "—"}
                  </td>
                  <td>
                    {job.status === "PROCESSING" ? (
                      <span>
                        <span className="tag tag-warn" style={{ marginBottom: "8px" }}>
                          {job.stage ?? "Processing"}
                        </span>
                        <span className="meter warn" style={{ display: "block" }}>
                          <span style={{ "--fill": job.progress ?? 0 } as React.CSSProperties} />
                        </span>
                      </span>
                    ) : (
                      <span className={`tag ${job.status === "COMPLETED" ? "tag-ok" : "tag-bad"}`}>
                        {job.status === "COMPLETED" ? "Completed" : "Failed"}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function shortWorker(id: string): string {
  return id.length > 10 ? `${id.slice(0, 8)}` : id;
}
