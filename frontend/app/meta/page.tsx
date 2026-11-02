"use client";

import { useEffect, useRef, useState } from "react";
import { api, type MetaStatus, type SegmentResult } from "@/lib/api";

type Rect = { x1: number; y1: number; x2: number; y2: number; label?: string };

function toRect(b: unknown): Rect | null {
  const num = (v: unknown) =>
    typeof v === "number" && Number.isFinite(v) ? v : null;
  if (Array.isArray(b) && b.length >= 4) {
    const [a, c, d, e] = [num(b[0]), num(b[1]), num(b[2]), num(b[3])];
    if (a === null || c === null || d === null || e === null) return null;
    return { x1: Math.min(a, d), y1: Math.min(c, e), x2: Math.max(a, d), y2: Math.max(c, e) };
  }
  if (b && typeof b === "object") {
    const o = b as Record<string, unknown>;
    if (o.box) return toRect(o.box);
    const x1 = num(o.x_min ?? o.x1 ?? o.left);
    const y1 = num(o.y_min ?? o.y1 ?? o.top);
    const x2 = num(o.x_max ?? o.x2 ?? o.right);
    const y2 = num(o.y_max ?? o.y2 ?? o.bottom);
    if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
      return { x1: Math.min(x1, x2), y1: Math.min(y1, y2), x2: Math.max(x1, x2), y2: Math.max(y1, y2), label: str(o.label ?? o.class ?? o.class_name) };
    }
    const x = num(o.x), y = num(o.y);
    const w = num(o.width ?? o.w), h = num(o.height ?? o.h);
    if (x !== null && y !== null && w !== null && h !== null) {
      return { x1: x, y1: y, x2: x + w, y2: y + h, label: str(o.label ?? o.class ?? o.class_name) };
    }
  }
  return null;
}

function str(v: unknown): string | undefined {
  return typeof v === "string" && v ? v : undefined;
}

export default function MetaPage() {
  const [status, setStatus] = useState<MetaStatus | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [prompt, setPrompt] = useState(
    "Segment every construction worker and every PPE item (hard hat, safety vest, gloves, boots). Return bounding boxes and masks."
  );
  const [result, setResult] = useState<SegmentResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imgSize, setImgSize] = useState({ w: 0, h: 0 });
  const imgRef = useRef<HTMLImageElement>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    api.meta.status().then(setStatus, () => {});
    api.meta.models().then(
      (r) => setModels(r.models),
      (e: Error) => setModelsError(e.message)
    );
    return () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  function pickFile(f: File | null) {
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = f ? URL.createObjectURL(f) : null;
    setFile(f);
    setPreview(urlRef.current);
  }

  async function run() {
    if (!file) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("prompt", prompt);
      setResult(await api.meta.segment(form));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Segmentation failed");
    } finally {
      setRunning(false);
    }
  }

  const rects = (result?.boxes ?? []).map(toRect).filter((r): r is Rect => r !== null);
  const normalized = rects.length > 0 && rects.every((r) => r.x2 <= 1.01 && r.y2 <= 1.01);
  const W = imgSize.w || 1;
  const H = imgSize.h || 1;

  return (
    <div className="animate-in">
      <div className="page-head">
        <div>
          <h1 className="page-title">Meta AI</h1>
          <p className="page-sub">
            SAM 3.1 segmentation plus muse-spark vision and briefs, served from api.meta.ai.
          </p>
        </div>
        {status && (
          <span className={`tag ${status.configured ? "tag-ok" : "tag-bad"}`}>
            {status.configured ? "Key set" : "No key"}
          </span>
        )}
      </div>

      <div className="stack">
        <div className="grid-2" style={{ alignItems: "start" }}>
          <section className="sheet" aria-label="Integration status">
            <div className="sheet-head">
              <span className="sheet-title">Integration</span>
              <span className="sheet-meta num">{status?.base_url ?? "probing"}</span>
            </div>
            {!status ? (
              <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "12px" }} aria-label="Loading status">
                <span className="skel" style={{ width: "65%" }} />
                <span className="skel" style={{ width: "80%" }} />
              </div>
            ) : (
              <div className="kv">
                <div className="kv-row">
                  <span className="kv-term">Segmentation</span>
                  <span className="kv-val">{status.sam_model} on {status.sam_backend}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-term">Stage 3 VLM</span>
                  <span className="kv-val">{status.vision_model} on {status.vlm_backend}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-term">Briefs model</span>
                  <span className="kv-val">{status.text_model}</span>
                </div>
              </div>
            )}
          </section>

          <section className="sheet" aria-label="Live model catalog">
            <div className="sheet-head">
              <span className="sheet-title">Live model catalog</span>
              <span className="sheet-meta">GET /meta/models</span>
            </div>
            <div className="sheet-body">
              {models ? (
                models.length === 0 ? (
                  <div style={{ fontSize: "16px", color: "var(--color-muted)" }}>Catalog empty.</div>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                    {models.map((m) => (
                      <span key={m} className="tag num">{m}</span>
                    ))}
                  </div>
                )
              ) : (
                <div style={{ fontSize: "16px", color: "var(--color-muted)" }}>
                  {modelsError?.includes("503")
                    ? "Set MODEL_API_KEY on the backend to list models."
                    : modelsError ?? "Loading."}
                </div>
              )}
            </div>
          </section>
        </div>

        <section className="sheet" aria-label="SAM 3.1 playground">
          <div className="sheet-head">
            <span className="sheet-title">SAM 3.1 playground</span>
            <span className="sheet-meta">POST /meta/segment</span>
          </div>
          <div className="sheet-body stack">
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr)", gap: "12px" }}>
              <div>
                <label className="field-label" htmlFor="seg-file">Image</label>
                <label className="dropzone" htmlFor="seg-file" style={{ padding: "20px 12px" }}>
                  <input
                    id="seg-file"
                    type="file"
                    accept="image/*"
                    onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                  />
                  <span style={{ pointerEvents: "none", fontSize: "16px", color: file ? "var(--color-ink)" : "var(--color-muted)", fontWeight: file ? 500 : 400 }}>
                    {file ? file.name : "Drop image or click to browse"}
                  </span>
                </label>
              </div>
              <div>
                <label className="field-label" htmlFor="seg-prompt">Text prompt</label>
                <textarea
                  id="seg-prompt"
                  className="field num"
                  rows={4}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  style={{ fontSize: "14px", lineHeight: 1.6 }}
                />
              </div>
            </div>

            <div>
              <button onClick={run} disabled={running || !file} className="btn btn-primary">
                {running ? (<><span className="spinner" style={{ borderTopColor: "var(--color-accent-ink)" }} /> Segmenting</>) : "Run SAM 3.1"}
              </button>
            </div>

            {error && (
              <div className="alert alert-error" role="alert">
                {error.includes("503")
                  ? "Error: MODEL_API_KEY is not configured on the backend. Add it to backend/.env and retry."
                  : `Error: segmentation failed (${error})`}
              </div>
            )}

            {preview && (
              <figure className="figure" style={{ maxWidth: "100%" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  ref={imgRef}
                  src={preview}
                  alt="Segmentation input"
                  onLoad={() => setImgSize({ w: imgRef.current?.naturalWidth ?? 0, h: imgRef.current?.naturalHeight ?? 0 })}
                />
                {imgSize.w > 0 && rects.length > 0 && (
                  <svg
                    viewBox={`0 0 ${imgSize.w} ${imgSize.h}`}
                    style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
                    role="img"
                    aria-label={`${rects.length} detected regions outlined`}
                  >
                    {rects.map((r, i) => {
                      const x1 = normalized ? r.x1 * W : r.x1;
                      const y1 = normalized ? r.y1 * H : r.y1;
                      const x2 = normalized ? r.x2 * W : r.x2;
                      const y2 = normalized ? r.y2 * H : r.y2;
                      return (
                        <g key={i}>
                          <rect x={x1} y={y1} width={Math.max(x2 - x1, 2)} height={Math.max(y2 - y1, 2)} fill="none" stroke="var(--color-critical)" strokeWidth={Math.max(W / 400, 2)} />
                          {r.label && (
                            <text x={x1 + 4} y={Math.max(y1 - 6, 12)} fill="var(--color-critical)" fontSize={Math.max(W / 50, 12)} fontFamily="monospace">
                              {r.label}
                            </text>
                          )}
                        </g>
                      );
                    })}
                  </svg>
                )}
              </figure>
            )}

            {result && (
              <div className="kv" style={{ border: "1px solid var(--color-rule-2)" }}>
                <div className="kv-row">
                  <span className="kv-term">Model</span>
                  <span className="kv-val">{result.model}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-term">Boxes</span>
                  <span className="kv-val">{result.boxes.length}</span>
                </div>
                <div className="kv-row">
                  <span className="kv-term">Masks</span>
                  <span className="kv-val">{result.masks.length}</span>
                </div>
              </div>
            )}

            {result?.raw !== undefined && (
              <details className="reg">
                <summary>Raw response</summary>
                <pre className="code" style={{ maxHeight: "300px", marginTop: "8px" }}>
                  {JSON.stringify(result.raw, null, 2)}
                </pre>
              </details>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
