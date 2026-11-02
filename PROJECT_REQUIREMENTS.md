# CAGE — Project Requirements

Tracks schema, API contracts, and frontend spec. Update as the ML pipeline matures and violation taxonomy gets finalized.

---

## Status

| Area | Status |
|---|---|
| DB Schema (SQLite) | Done |
| Enums | Done |
| FastAPI Backend | Done (`backend/app/`, routers + services) |
| Next.js Frontend | Done (dashboard, jobs, ingest; workers placeholder) |
| Worker Identification — POV | Done (device check-in → shift binding) |
| Worker Identification — Wall Cam | Partial (BoT-SORT track IDs; embedding re-ID open) |
| Object Permanence (Wall Cam) | Partial (tracker persistence; re-association open) |
| ML Pipeline (POV) | Done (YOLO + SAM 3 + VLM, shared job runner) |
| ML Pipeline (Wall Cam) | Done (YOLO + SAM 3 + VLM) |

---

## Tech Stack

| Layer | Choice |
|---|---|
| Database | SQLite via SQLAlchemy (`backend/data/cage.db`) |
| Backend | FastAPI + Uvicorn (`backend/app/main.py`, `uvicorn app.main:app`) |
| ML Pipeline | `backend/app/pipeline/` (wall_cam, posture, vlm_step) |
| VLM Stage 3 | Local Qwen3-VL weights, or Meta Model API (`VLM_BACKEND=meta`) |
| Segmentation | Local SAM 3 weights, or SAM 3.1 API (`SAM_BACKEND=meta`) |
| Frontend | Next.js + Tailwind (`/frontend`) |
| Frontend → Backend | typed client `frontend/lib/api.ts` → `http://localhost:8000` |

**Local ports:**
```
Next.js frontend   →  http://localhost:3000   (bun dev)
FastAPI backend    →  http://localhost:8000   (uvicorn app.main:app)
```

No cloud credentials required for the local pipeline. Meta integrations
(SAM 3.1 segmentation, Llama VLM backend, shift summaries) need
`MODEL_API_KEY` in `backend/.env` — paste it into the empty slot;
see `docs/META_INTEGRATIONS.md`.

---

## Running

```bash
# Terminal 1
cd backend
bash setup.sh            # first time only (venv + deps + .env)
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2
cp frontend/.env.example frontend/.env.local   # first time only
cd frontend && bun dev
```

---

## Enums

Defined in `backend/app/models/enums.py` as Python enums, stored as strings in SQLite.

### `CameraSource`
```
POV         # body-worn camera → musculoskeletal/posture pipeline
WALL_CAM    # fixed mounted camera → spatial/behavioral pipeline
```

### `EventCategory`
```
VIOLATION   # unsafe behavior or posture detected
COMPLIANT   # confirmed safe behavior
```

### `ViolationType`
Stored as plain string in `safety_events.violation_type`. TBD as ML pipeline is built — starting set:
```
# Wall cam
FALL_PROTECTION_MISSING
PPE_MISSING
ZONE_BREACH
PROXIMITY_HAZARD
SCAFFOLD_VIOLATION
LADDER_MISUSE
BEHAVIORAL_UNSAFE

# POV
IMPROPER_LIFT
AWKWARD_POSTURE
MSD_HIGH_RISK
REPETITIVE_STRAIN

# Either
COMPLIANT_BEHAVIOR
```

### `Severity`
```
LOW | MEDIUM | HIGH | CRITICAL
```

### `WorkerStatus`
```
ACTIVE | INACTIVE
```

### `ShiftStatus`
```
IN_PROGRESS | COMPLETED
```

---

## Database Schema

Defined in `backend/app/models/safety.py` (engine/session in `backend/app/db/`). SQLite file lives at `backend/data/cage.db`.

### `sites`
```
id           TEXT  PK
name         TEXT
location     TEXT
created_at   DATETIME
```

### `devices`
Maps physical POV camera units to a site. The per-shift worker binding is on `shifts.pov_device_id`.
```
id           TEXT  PK
label        TEXT              # e.g. "Cam-03"
site_id      TEXT  FK → sites
created_at   DATETIME
```

### `workers`
Persistent worker identity. Survives across shifts and days.
```
id                    TEXT  PK
site_id               TEXT  FK → sites
display_name          TEXT  nullable   # local label only; never sent externally
appearance_embedding  TEXT  nullable   # base64 — wall-cam re-ID (local only)
face_embedding        TEXT  nullable   # deprecated/unused (face recognition removed)
status                TEXT             # WorkerStatus enum
created_at            DATETIME
last_seen_at          DATETIME  nullable
total_violations      INT  default 0   # denormalized
total_compliant       INT  default 0   # denormalized
avg_msd_risk          FLOAT  default 0.0  # rolling avg from POV shifts
```

### `shifts`
One row per worker per day.
```
id               TEXT  PK
worker_id        TEXT  FK → workers
site_id          TEXT  FK → sites
date             TEXT              # "YYYY-MM-DD"
started_at       DATETIME
ended_at         DATETIME  nullable
status           TEXT              # ShiftStatus enum
pov_device_id    TEXT  FK → devices  nullable  # which POV cam this worker wore today
msd_risk_score   FLOAT  nullable   # set when POV processing completes
violation_count  INT  default 0    # updated on each event write
compliant_count  INT  default 0    # updated on each event write
```

### `safety_events`
Core event log. One row per flagged moment from either pipeline.
```
id               TEXT  PK
shift_id         TEXT  FK → shifts
worker_id        TEXT  FK → workers
camera_source    TEXT              # CameraSource enum
event_category   TEXT              # EventCategory enum
violation_type   TEXT  nullable    # ViolationType string
severity         TEXT  nullable    # Severity enum, null for COMPLIANT
video_timestamp  FLOAT             # seconds into source video
clip_path        TEXT  nullable    # local path to extracted clip
metadata_json    TEXT  nullable    # JSON blob for pipeline-specific extras
created_at       DATETIME
```

---

## Worker Identification & Tagging

### POV — Device-to-Worker Binding

The camera is worn by one worker. Identity problem: which worker is wearing which camera today?

**Flow:**
1. Worker checks in via dashboard → selects their name + POV device label
2. `POST /workers/checkin` creates a shift with `pov_device_id` set
3. POV pipeline receives video labeled with device ID → queries `GET /devices?site_id=` to resolve `device_id → worker_id + shift_id`
4. All events from that video are tagged against that worker

### Wall Cam — Appearance-Based Re-ID + Object Permanence

Multiple workers visible simultaneously, none pre-labeled.

**At video start:**
- `GET /workers?site_id=` fetches all known workers with embeddings → seeds local in-memory registry
- All matching is done in-memory (cosine similarity) — no per-frame DB calls

**Per detection:**
```
Bounding box crop → re-ID encoder → embedding
        │
        ├── similarity > threshold → existing worker_id
        └── no match → temp ID → POST /workers/register at end of video
```

**Object permanence:**
- When a track disappears, hold last known state in memory (worker_id + embedding + position)
- On reappearance: re-ID check against held state → re-assign same worker_id if match
- Time window TBD (~5–10 min before giving up on a lost track)

**DB is read once at video start, written once at video end** — no per-frame Firestore/DB calls.

---

## API Endpoints

FastAPI at `http://localhost:8000`. Routers in `backend/app/api/routes/`,
business logic in `backend/app/services/`, schemas in `backend/app/schemas/`.
All `POST`/`PATCH` payloads are JSON bodies (see schemas).

### Health
```
GET  /health
→ { "status": "ok" }
```

### Sites
```
POST /sites               create a site            {name, location}
GET  /sites               list all sites
```

### Devices
```
POST /devices             register a POV device    {label, site_id}
GET  /devices?site_id=    list devices for a site
```

### Workers
```
POST /workers/register    register new worker (called by wall-cam re-ID)
POST /workers/checkin     link worker to POV device, open shift
GET  /workers?site_id=    list workers (also seeds wall-cam re-ID registry)
GET  /workers/{id}        get single worker with stats
```

### Shifts
```
GET   /shifts/{id}          get shift + all its events
PATCH /shifts/{id}/close    mark completed, set msd_risk_score
```

### Events
```
POST /events/ingest         write a safety event (called by ML pipeline)
GET  /events                list events, filterable by worker_id / shift_id / event_category
```

### Video Processing
```
POST /process/pov           submit POV video → starts processing job
POST /process/wall-cam      submit wall-cam video → starts processing job
```

### Jobs
```
GET  /jobs                  list jobs with shift/event counts
GET  /jobs/{job_id}         poll job status (+ progress/stage)
GET  /jobs/{job_id}/results full summary + VLM + posture outputs
GET  /jobs/{job_id}/vlm     VLM assessments per event window
GET  /jobs/{job_id}/frames/{filename}
                            serve a flagged frame / crop image
```

### Meta Model API (needs MODEL_API_KEY)
```
GET  /meta/status           configured? models in use (no key material)
GET  /meta/models           live model catalog from api.meta.ai
POST /meta/segment          SAM 3.1: image/video + prompt → boxes + masks
```

### Reports (Meta Model API — needs MODEL_API_KEY)
```
GET  /reports/shifts/{id}/summary
                            Llama-generated end-of-shift safety brief
                            (anonymized worker code only — no names)
```

---

## Frontend Pages

Defined in `frontend/app/`. All data via the typed client in
`frontend/lib/api.ts` → `http://localhost:8000`.

### `/` — Site Dashboard
- KPI cards: jobs processed, violations detected, events in DB
- Recent jobs list + processing-status panel
- Backend connection status indicator

### `/jobs` — Job History
- Table of jobs (worker, site, camera, events, violations, status)
- Auto-refresh polling

### `/jobs/[jobId]` — Job Report
- Progress bar while processing; error panel on failure
- Posture analysis, hazard breakdown, PPE compliance
- Safety events table with expandable VLM detail + flagged frames
- AI Shift Brief (Meta Model API, on demand)

### `/ingest` — Video Upload
- Upload form: POV or wall-cam, file picker, worker/device/site fields
- Session jobs list with status polling

### `/workers` — Worker Registry (placeholder)
- Planned: name, status, lifetime violations, last seen, per-worker detail

---

## Open Items

- [x] `POST /events/ingest`, `PATCH /shifts/{id}/close`, `POST /workers/checkin`, `/devices` routes
- [ ] Finalize `ViolationType` values once ML pipeline is scoped
- [ ] Choose re-ID model for wall-cam (OSNet / torchreid / DINOv3) and fix embedding dimensions
- [ ] Tune cosine similarity threshold (~0.75 starting point) in wall-cam pipeline
- [ ] Define object permanence time window for lost tracks
- [ ] Site heatmap data format (zones, coordinate system)
- [ ] `clip_path` — local filesystem path for now, define folder structure
