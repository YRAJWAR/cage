# CAGE frontend

Next.js safety dashboard. All backend access goes through the typed client in
`lib/api.ts` — pages must not hardcode the API URL.

## Layout

```
frontend/
  app/                 # /, /jobs, /jobs/[jobId], /ingest, /workers
  lib/api.ts           # typed API client (API_BASE_URL + api.*)
  public/              # static assets
```

## Run

```bash
cp .env.example .env.local   # first time only
bun dev                      # http://localhost:3000
```

Backend must be up at `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).
