from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    init_db()
    print("ML service started — SQLite ready")
    from app.services.jobs import hydrate_jobs

    hydrate_jobs()
    if settings.prewarm_models:
        # Pre-warm all models so the first job doesn't hit cold-start OOM
        # or CUDA init errors. Skipped when PREWARM_MODELS=false (tests,
        # API-only deployments) or when ML deps are missing.
        import asyncio
        import concurrent.futures

        loop = asyncio.get_event_loop()

        def _warm():
            try:
                from app.pipeline.vlm_step import _get_model
                from app.pipeline.wall_cam import _get_sam, _get_yolo

                print("[startup] warming YOLO ...")
                _get_yolo()
                if settings.sam_backend == "meta":
                    print("[startup] SAM backend=meta — skipping local SAM warm-up")
                else:
                    print("[startup] warming SAM ...")
                    _get_sam()
                if settings.vlm_backend == "local":
                    print("[startup] warming VLM ...")
                    _get_model()
                else:
                    print("[startup] VLM backend=meta — skipping local VLM warm-up")
                print("[startup] all models ready")
            except ImportError as exc:
                print(f"[startup] WARNING: ML deps missing, skipping warm-up ({exc})")
            except Exception as exc:  # noqa: BLE001 — warm-up must never kill the API
                print(
                    "[startup] WARNING: model warm-up failed, API running "
                    f"without preloaded models ({exc})"
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _warm)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
