"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type JobEntry, type MetaStatus } from "@/lib/api";

export default function DashboardPage() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [meta, setMeta] = useState<MetaStatus | null>(null);
  const [jobs, setJobs] = useState<JobEntry[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.health().then(
      () => setConnected(true),
      () => setConnected(false)
    );
    api.meta.status().then(setMeta, () => {});
    api.jobs.list().then(
      (list) => {
        setJobs(list);
        setLoaded(true);
      },
      () => setLoaded(true)
    );
  }, []);

  const completed = jobs.filter((j) => j.status === "COMPLETED");
  const processing = jobs.filter((j) => j.status === "PROCESSING");
  const failed = jobs.filter((j) => j.status === "FAILED");
  const queue = [...completed]
    .sort((a, b) => (b.shift?.violation_count ?? 0) - (a.shift?.violation_count ?? 0))
    .slice(0, 6);
  const maxViol = Math.max(1, ...queue.map((j) => j.shift?.violation_count ?? 0));
  const totalViolations = completed.reduce((s, j) => s + (j.shift?.violation_count ?? 0), 0);
  const totalEvents = completed.reduce((s, j) => s + (j.shift?.event_count ?? 0), 0);
  const dates = completed.map((j) => j.shift?.date).filter((d): d is string => !!d).sort();

  return (
    <div className="animate-in">
      <div className="page-head">
        <div>
          <h1 className="page-title">Shift overview</h1>
          <p className="page-sub">
            {completed.length} reports filed. {totalViolations} violations across {totalEvents} events.
          </p>
        </div>
        <div style={{ display: "flex", gap: "24px", alignItems: "center" }}>
          <BackendStatus connected={connected} />
          <MetaStatusLine meta={meta} />
        </div>
      </div>

      {jobs.length === 0 && loaded && <StartHere />}

      <div className="grid-2" style={{ gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", alignItems: "start" }}>
        <section className="sheet" aria-label="Attention queue">
          <div className="sheet-head">
            <span className="sheet-title">Attention queue</span>
            <span className="sheet-meta">worst shifts first</span>
          </div>
          {!loaded ? (
            <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }} aria-label="Loading reports">
              <span className="skel" style={{ width: "70%" }} />
              <span className="skel" style={{ width: "90%" }} />
              <span className="skel" style={{ width: "55%" }} />
            </div>
          ) : queue.length === 0 ? (
            <div className="empty">
              <p>No reports yet. Upload site footage and the highest risk shifts will surface here.</p>
              <Link href="/ingest" className="btn btn-primary">Open ingest</Link>
            </div>
          ) : (
            <table className="register">
              <thead>
                <tr>
                  <th scope="col">No.</th>
                  <th scope="col">Shift</th>
                  <th scope="col">Load</th>
                  <th scope="col" style={{ textAlign: "right" }}>Violations</th>
                </tr>
              </thead>
              <tbody>
                {queue.map((j, i) => {
                  const viol = j.shift?.violation_count ?? 0;
                  return (
                    <tr key={j.job_id} className="link">
                      <td className="stage-no">{String(i + 1).padStart(2, "0")}</td>
                      <td>
                        <Link href={`/jobs/${j.job_id}`} style={{ textDecoration: "none" }}>
                          <span className="row-title">{j.shift?.site ?? "Unknown site"}</span>
                          <span style={{ color: "var(--color-muted)", fontSize: "14px" }}>
                            {" "}{j.shift?.date} {j.camera_source ?? ""}
                          </span>
                        </Link>
                      </td>
                      <td>
                        <div className="meter critical" role="img" aria-label={`${viol} violations`}>
                          <span style={{ "--fill": viol > 0 ? Math.max(viol / maxViol, 0.04) : 0 } as React.CSSProperties} />
                        </div>
                      </td>
                      <td className="num" style={{ textAlign: "right", fontSize: "20px", color: viol > 0 ? "var(--color-critical)" : "var(--color-muted)" }}>
                        {viol}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <div className="stack">
          <section className="sheet" aria-label="Totals">
            <div className="dim-figure">
              <div className="dim-value">{totalViolations}</div>
              <div className="dim-unit">flagged violations on file</div>
              <div className="dim" aria-hidden />
              <div className="dim-ends">
                <span>{dates[0] ?? "no shifts"}</span>
                <span>{dates.length > 0 ? dates[dates.length - 1] : "no shifts"}</span>
              </div>
            </div>
          </section>

          <section className="sheet" aria-label="Pipeline">
            <div className="sheet-head">
              <span className="sheet-title">Pipeline</span>
              <span className="sheet-meta num">
                {processing.length} active, {failed.length} failed
              </span>
            </div>
            {processing.length === 0 ? (
              <div className="empty" style={{ padding: "24px 16px" }}>
                <p>Idle. New uploads appear here with live progress.</p>
              </div>
            ) : (
              <div>
                {processing.map((j) => (
                  <Link
                    key={j.job_id}
                    href={`/jobs/${j.job_id}`}
                    style={{ display: "block", padding: "12px 16px", borderBottom: "1px solid var(--color-rule-2)", textDecoration: "none" }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "8px" }}>
                      <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                        {j.job_id.slice(0, 8)}
                      </span>
                      <span style={{ fontSize: "14px", color: "var(--color-warn)", fontWeight: 500 }}>
                        {j.stage ?? "processing"}
                      </span>
                    </div>
                    <div className="meter warn">
                      <span style={{ "--fill": j.progress ?? 0 } as React.CSSProperties} />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="sheet" aria-label="System">
            <div className="sheet-head">
              <span className="sheet-title">System</span>
            </div>
            <div className="kv">
              <div className="kv-row">
                <span className="kv-term">Backend</span>
                <span className="kv-val" style={{ color: connected ? "var(--color-ok)" : "var(--color-bad)" }}>
                  {connected === null ? "probing" : connected ? "online" : "offline"}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-term">Meta Model API</span>
                <span className="kv-val" style={{ color: meta?.configured ? "var(--color-info)" : undefined }}>
                  {meta === null ? "probing" : meta.configured ? "key set" : "no key"}
                </span>
              </div>
              <div className="kv-row">
                <span className="kv-term">Segmentation</span>
                <span className="kv-val">{meta ? `${meta.sam_model} on ${meta.sam_backend}` : "probing"}</span>
              </div>
              <div className="kv-row">
                <span className="kv-term">Stage 3 VLM</span>
                <span className="kv-val">{meta ? `${shortId(meta.vision_model)} on ${meta.vlm_backend}` : "probing"}</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function shortId(id: string): string {
  return id.length > 26 ? `${id.slice(0, 24)}…` : id;
}

function MetaStatusLine({ meta }: { meta: MetaStatus | null }) {
  if (meta === null) {
    return <span className="tag">Meta AI probing</span>;
  }
  return (
    <Link href="/meta" style={{ textDecoration: "none" }}>
      <span className={`tag ${meta.configured ? "tag-info" : ""}`}>
        {meta.configured ? `Meta AI, ${meta.sam_model}` : "Meta AI, no key"}
      </span>
    </Link>
  );
}

function BackendStatus({ connected }: { connected: boolean | null }) {
  if (connected === null) {
    return <span className="tag">Connecting</span>;
  }
  if (connected) {
    return <span className="tag tag-ok">Backend online</span>;
  }
  return <span className="tag tag-bad">Backend offline</span>;
}

function StartHere() {
  const [siteId, setSiteId] = useState<string | null>(null);
  const [reused, setReused] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createDemoSite() {
    setCreating(true);
    setError(null);
    try {
      const existing = await api.sites.list();
      const demo = existing.find((s) => s.name === "Demo Site");
      if (demo) {
        setSiteId(demo.id);
        setReused(true);
      } else {
        const site = await api.sites.create({ name: "Demo Site", location: "Lot 7" });
        setSiteId(site.id);
        setReused(false);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not create the site");
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="sheet" aria-label="Getting started" style={{ marginBottom: "16px" }}>
      <div className="sheet-head">
        <span className="sheet-title">Start here: your first safety report in 3 steps</span>
      </div>
      <div className="run">
        <div className="run-step">
          <div className="run-no">01</div>
          <div>
            <div className="run-name">Create a site</div>
            <div className="run-desc">
              A site is one construction location. Workers and shifts hang off it.
              {!siteId ? (
                <span style={{ display: "inline-flex", gap: "8px", alignItems: "center", marginLeft: "8px" }}>
                  <button onClick={createDemoSite} disabled={creating} className="btn" style={{ minHeight: "32px", paddingInline: "12px", fontSize: "14px" }}>
                    {creating ? "Creating" : "Create demo site"}
                  </button>
                  {error && <span style={{ color: "var(--color-bad)" }}>{error}</span>}
                </span>
              ) : (
                <span className="num" style={{ display: "block", marginTop: "8px", fontSize: "14px", color: "var(--color-ok)" }}>
                  {reused ? "Reusing existing" : "Created"}: {siteId} (pick it in the Ingest site list)
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="run-step">
          <div className="run-no">02</div>
          <div>
            <div className="run-name">Upload shift video</div>
            <div className="run-desc">
              Go to <Link href="/ingest" style={{ color: "var(--color-ink)", fontWeight: 500 }}>Ingest</Link>,
              pick your site, drop in wall camera or POV footage, and run the analysis.
            </div>
          </div>
        </div>
        <div className="run-step">
          <div className="run-no">03</div>
          <div>
            <div className="run-name">Read the report</div>
            <div className="run-desc">
              When the job completes it appears here and under{" "}
              <Link href="/jobs" style={{ color: "var(--color-ink)", fontWeight: 500 }}>Jobs</Link>{" "}
              with violations, PPE compliance, and an AI shift brief.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
