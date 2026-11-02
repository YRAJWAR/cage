"use client";

import { useEffect, useState } from "react";
import { api, type Site, type Worker } from "@/lib/api";

export default function WorkersPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteId] = useState<string>("");
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.sites
      .list()
      .then((list) => {
        if (cancelled) return;
        setSites(list);
        if (list.length === 0) setLoading(false);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const activeSiteId = siteId || sites[0]?.id || "";

  useEffect(() => {
    if (!activeSiteId) return;
    let cancelled = false;
    api.workers
      .list(activeSiteId)
      .then((list) => {
        if (!cancelled) {
          setWorkers([...list].sort((a, b) => b.total_violations - a.total_violations));
          setLoading(false);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [activeSiteId]);

  return (
    <div className="animate-in">
      <div className="page-head">
        <div>
          <h1 className="page-title">Workers</h1>
          <p className="page-sub">
            Persistent safety identity per worker. Violations, compliant behavior, and MSD risk accumulate across shifts.
          </p>
        </div>
        {sites.length > 0 && (
          <div>
            <label className="field-label" htmlFor="worker-site">Site</label>
            <select
              id="worker-site"
              className="field"
              value={activeSiteId}
              onChange={(e) => {
                setLoading(true);
                setSiteId(e.target.value);
              }}
              style={{ width: "auto", minWidth: "220px" }}
            >
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id.slice(0, 8)})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="alert alert-error" role="alert" style={{ marginBottom: "16px" }}>
          Error: could not load workers ({error}). Check that the backend is running.
        </div>
      )}

      {loading ? (
        <section className="sheet" aria-label="Loading workers">
          <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <span className="skel" style={{ width: "75%" }} />
            <span className="skel" style={{ width: "55%" }} />
            <span className="skel" style={{ width: "85%" }} />
          </div>
        </section>
      ) : sites.length === 0 ? (
        <section className="sheet">
          <div className="empty">
            <p>No sites yet. Register a site and check workers in, then this registry fills in.</p>
          </div>
        </section>
      ) : workers.length === 0 ? (
        <section className="sheet">
          <div className="empty">
            <p>No workers registered at this site yet.</p>
          </div>
        </section>
      ) : (
        <section className="sheet" aria-label="Worker register">
          <table className="register">
            <thead>
              <tr>
                <th scope="col">No.</th>
                <th scope="col">Worker</th>
                <th scope="col">Status</th>
                <th scope="col">Violations</th>
                <th scope="col">Compliant</th>
                <th scope="col">MSD risk</th>
              </tr>
            </thead>
            <tbody>
              {workers.map((w, i) => (
                <tr key={w.worker_id}>
                  <td className="stage-no">{String(i + 1).padStart(2, "0")}</td>
                  <td>
                    <span className="row-title">{w.display_name || "Unnamed worker"}</span>
                    <span className="num" style={{ display: "block", fontSize: "14px", color: "var(--color-muted)" }}>
                      {w.worker_id.slice(0, 12)}
                      {w.last_seen_at ? `, seen ${w.last_seen_at.slice(0, 10)}` : ""}
                    </span>
                  </td>
                  <td>
                    <span className={`tag ${w.status === "ACTIVE" ? "tag-ok" : ""}`}>
                      {w.status === "ACTIVE" ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="num" style={{ fontSize: "18px", color: w.total_violations > 0 ? "var(--color-critical)" : "var(--color-muted)" }}>
                    {w.total_violations}
                  </td>
                  <td className="num" style={{ fontSize: "18px", color: "var(--color-ok)" }}>
                    {w.total_compliant}
                  </td>
                  <td>
                    <span className="meter warn" style={{ display: "block", maxWidth: "120px" }}>
                      <span style={{ "--fill": Math.min(Math.max(w.avg_msd_risk, 0), 5) / 5 } as React.CSSProperties} />
                    </span>
                    <span className="num" style={{ fontSize: "14px", color: "var(--color-muted)" }}>
                      {w.avg_msd_risk.toFixed(1)} of 5
                    </span>
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
