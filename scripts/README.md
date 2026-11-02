# Scripts

One-off analysis CLIs live here.

Previously referenced CLIs (`analyze_pov_posture_timestamps.py`,
`analyze_pov_ppe_timestamps.py`) were never committed. Their functionality
is covered by the backend job pipeline — submit video via
`POST /process/pov` or `POST /process/wall-cam` and read results from
`GET /jobs/{id}/results` (compliant / non-compliant ranges are in the
returned posture and VLM payloads).

New scripts must import pipeline helpers from `app.pipeline` (run from
`backend/` so `app.*` resolves) rather than duplicating detection logic.
