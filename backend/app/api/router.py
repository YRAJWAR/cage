from fastapi import APIRouter

from app.api.routes import (
    devices,
    events,
    health,
    jobs,
    meta,
    process,
    reports,
    shifts,
    sites,
    workers,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sites.router)
api_router.include_router(devices.router)
api_router.include_router(workers.router)
api_router.include_router(shifts.router)
api_router.include_router(events.router)
api_router.include_router(process.router)
api_router.include_router(jobs.router)
api_router.include_router(reports.router)
api_router.include_router(meta.router)
