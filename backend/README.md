# CAGE backend

FastAPI service: video-processing jobs (YOLO + SAM 3 + VLM), SQLite event
store, and REST API for the dashboard.

## Layout

```
backend/
  app/
    main.py            # app factory, lifespan, middleware, router registration
    core/config.py     # every env var (pydantic-settings, loads backend/.env)
    db/                # engine, session factory, Base
    models/            # enums + SQLAlchemy tables
    schemas/           # pydantic request/response models
    api/
      deps.py          # shared dependencies (get_db)
      router.py        # aggregates all route modules
      routes/          # health, meta, sites, devices, workers, shifts,
                       # events, process, jobs, reports
    services/jobs.py   # background detection-job orchestration + DB writes
    integrations/      # Meta Model API client (VLM backend + shift summaries)
    pipeline/          # ML stages: wall_cam, posture, vlm_step
  tests/               # pytest (no GPU / weights needed)
  .env.example         # copy to .env — ships EMPTY, paste your key there
```

Run from `backend/` so `app.*` imports resolve:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Env

```bash
cp .env.example .env   # then paste MODEL_API_KEY into .env
```

All settings live in `app/core/config.py`. Model paths default to
repo-relative `backend/models/`; override with `YOLO_MODEL_PATH`,
`SAM_MODEL_PATH`, `POSE_MODEL_PATH`.

## Meta Model API

Set `MODEL_API_KEY` in `.env` (get one at
https://api.meta.ai; legacy `MODEL_API_KEY` /
`LLAMA_API_KEY` also work). This enables:

- `VLM_BACKEND=meta` — Stage-3 VLM assessment via a vision Llama model
  instead of local Qwen3-VL weights (no GPU VLM needed).
- `GET /reports/shifts/{id}/summary` — Llama end-of-shift brief.
- `GET /meta/status`, `GET /meta/models` — integration health/catalog.

Only anonymized worker codes are sent to the API. See
[docs/META_INTEGRATIONS.md](../docs/META_INTEGRATIONS.md).

## Schema changes

`devices` and `shifts.pov_device_id` were added after the first DB
version. SQLite files created before that lack them — delete the dev
database and let it recreate:

```bash
rm backend/data/cage.db   # recreates with all tables on next boot
```

## Tests

```bash
pip install -r requirements-dev.txt
PREWARM_MODELS=false pytest -q
```
