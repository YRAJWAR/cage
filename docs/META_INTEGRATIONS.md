# Meta product integrations

Built for the [Meta AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon).
One key — `MODEL_API_KEY` in `backend/.env` — powers every hosted-Meta
feature against `https://api.meta.ai/v1`. Verify with
`GET /meta/status` → `GET /meta/models`, or the Meta AI page in the UI.

> "Meta Model API" here means Meta's hosted API at `https://api.meta.ai`.
> Calls used: `POST /v1/files` (upload image/video, purpose `user_data`)
> then `POST /v1/responses` (run a model over text + file refs).
> Verified live with a real key — see "Verified behavior" below.

## Live catalog (verified)

`GET /meta/models` returns 9 models — no Llama IDs; the general
vision+text model is **muse-spark**:

| Model | Verified use in CAGE |
|---|---|
| `muse-spark-1.3` | Stage-3 VLM (`VLM_BACKEND=meta`) + shift briefs — text ✓ and image ✓ |
| `muse-spark-1.2` / `1.1` (+ `-contributor`) | Older sparks — same env knobs work |
| `sam-3.1` | Segmentation endpoint (see caveat below) |
| `muse-image-1.0`, `muse-voice-transcribe-1.0`, `muse-wonder-1.0` | Not used by CAGE |

| Setting | Default | Purpose |
|---|---|---|
| `META_MODEL_API_VISION_MODEL` | `muse-spark-1.3` | Stage-3 VLM: annotated frames + YOLO/SAM data → `VLMAssessment` JSON |
| `META_MODEL_API_TEXT_MODEL` | `muse-spark-1.3` | AI shift briefs (`GET /reports/shifts/{id}/summary`) |

## SAM 3.1 — segmentation

| Use in CAGE | Where |
|---|---|
| **Stage-2 refinement** — flagged frames get API boxes + masks; full payload in `meta_sam.json`, counts in `summary.json` | `SAM_BACKEND=meta`, `backend/app/pipeline/wall_cam.py` (`_refine_with_meta_sam`, capped by `META_SAM_MAX_FRAMES=8`) |
| **Interactive demo** — image/video + text prompt → boxes + masks | `POST /meta/segment`, UI at `/meta` (SAM 3.1 Playground with box overlay) |

Input per the API spec: text prompt + image/video. Output: boxes and masks.
Auth: `Bearer MODEL_API_KEY`. Client: `backend/app/integrations/meta_api.py`
(`segment_image`, `segment_video`, `normalize_segmentation`).

> Caveat: `sam-3.1` accepts the image (`images_processed: 1`) but returned
> empty text across every prompt shape tried — it likely needs a dedicated
> output mode from Meta's docs. The plumbing (upload → responses →
> normalize → overlay UI) is done; the call will light up once the correct
> SAM output parameters are known. Meanwhile `muse-spark-1.3` vision is
> fully working for Stage-3 assessment.

## Verified behavior (live probing notes)

- `/files` needs `purpose=user_data` (not `vision`/`assistants`), and the
  filename MIME must match the actual bytes — the client sniffs magic
  bytes and renames accordingly.
- `muse-spark` reasons at high effort by default and can burn the whole
  budget before emitting text (`status: incomplete`, reasoning-only
  output). The client sends `reasoning: {effort: minimal}` (`"none"` is
  rejected) and floors vision chunks at 2048 output tokens.

Wired endpoints:

- `GET /meta/status` — configured? which models/backends? (never returns the key)
- `GET /meta/models` — live catalog from the API (needs key)
- `POST /meta/segment` — multipart `file` + `prompt` → `{model, boxes, masks, raw}`
- `GET /reports/shifts/{shift_id}/summary` — end-of-shift brief
  (overview, key violations, patterns, recommendations). Sends only the
  opaque worker UUID — never names or embeddings.

Setup:

```bash
# backend/.env
MODEL_API_KEY=<paste key>
SAM_BACKEND=meta
VLM_BACKEND=meta
```

Trade-off: API mode collapses the local 3-pass adversarial CoT
(Observer → Auditor → Reconciler) into a single reconciler-style pass and
uploads frames via `POST /files` first. Downstream
`vlm_assessments.json`, DB writes, and the dashboard are unchanged.

## Meta open models (local, no key)

| Model | Use | Where |
|---|---|---|
| **SAM 3** weights (`SAM_MODEL_PATH`, default `backend/models/sam3.pt`) | Local Stage-2 fallback when `SAM_BACKEND=local` | `backend/app/pipeline/wall_cam.py` |
| Qwen3-VL 8B (non-Meta baseline) | Local Stage-3 fallback when `VLM_BACKEND=local` | `backend/app/pipeline/vlm_step.py` |

## Future hooks (not implemented)

- **DINOv3 embeddings for wall-cam re-ID** — drop-in for
  `workers.appearance_embedding`; new `backend/app/pipeline/reid.py`.
- **Llama toolbox talks** — per-worker weekly summaries from accumulated
  events under `/reports`.
- **SAM 3.1 video mode in-pipeline** — send clips instead of stills once
  video responses are confirmed stable.
