from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile

from app.models.enums import CameraSource
from app.schemas.jobs import JobSubmitOut
from app.services.jobs import create_job, resolve_worker_code, run_detection_job

router = APIRouter(prefix="/process", tags=["process"])


@router.post("/pov", response_model=JobSubmitOut)
async def process_pov(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    worker_id: str | None = Form(None),
    site_id: str = Form(...),
    date: str = Form(...),
):
    code = resolve_worker_code(worker_id)
    job_id, job_dir, video_path = create_job(video, code, site_id, date)
    background_tasks.add_task(
        run_detection_job,
        job_id,
        job_dir,
        video_path,
        site_id,
        date,
        code,
        CameraSource.POV,
    )
    return {"job_id": job_id, "status": "PROCESSING"}


@router.post("/wall-cam", response_model=JobSubmitOut)
async def process_wall_cam(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    worker_id: str | None = Form(None),
    site_id: str = Form(...),
    date: str = Form(...),
):
    code = resolve_worker_code(worker_id)
    job_id, job_dir, video_path = create_job(video, code, site_id, date)
    background_tasks.add_task(
        run_detection_job,
        job_id,
        job_dir,
        video_path,
        site_id,
        date,
        code,
        CameraSource.WALL_CAM,
    )
    return {"job_id": job_id, "status": "PROCESSING"}
