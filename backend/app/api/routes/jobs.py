import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.safety import SafetyEvent, Shift, Site, Worker
from app.services.jobs import JOBS_DIR, jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
def list_jobs(db: Session = Depends(get_db)):
    """List all jobs with their SQLite shift + event counts."""
    result = []
    for job_id, job in jobs.items():
        entry = {
            "job_id": job_id,
            "status": job["status"],
            "events_written": job["events_written"],
            "error": job.get("error"),
            "camera_source": job.get("camera_source"),
            "progress": job.get("progress"),
            "stage": job.get("stage"),
        }
        shift_id = job.get("shift_id")
        if shift_id:
            shift = db.query(Shift).filter(Shift.id == shift_id).first()
            if shift:
                worker = db.query(Worker).filter(Worker.id == shift.worker_id).first()
                site = db.query(Site).filter(Site.id == shift.site_id).first()
                event_count = (
                    db.query(SafetyEvent).filter(SafetyEvent.shift_id == shift.id).count()
                )
                entry["shift"] = {
                    "shift_id": shift.id,
                    "date": shift.date,
                    "worker_id": shift.worker_id,
                    # Opaque code only — display names stay in the DB.
                    "worker": worker.id if worker else shift.worker_id,
                    "site": site.name if site else shift.site_id,
                    "violation_count": shift.violation_count,
                    "event_count": event_count,
                    "status": shift.status,
                    "started_at": str(shift.started_at),
                    "ended_at": str(shift.ended_at) if shift.ended_at else None,
                }
        result.append(entry)
    return result


@router.get("/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **job}


@router.get("/{job_id}/results")
def get_job_results(job_id: str):
    """Full structured output from the pipeline: summary + all hazard events."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")

    job_dir = Path(job["job_dir"])

    summary_file = job_dir / "summary.json"
    vlm_file = job_dir / "vlm_assessments.json"
    posture_file = job_dir / "posture_events.json"
    posture_summary_file = job_dir / "posture_summary.json"
    posture_vlm_file = job_dir / "posture_vlm.json"
    meta_sam_file = job_dir / "meta_sam.json"

    if not summary_file.exists():
        raise HTTPException(status_code=404, detail="Results not found on disk")

    summary = json.loads(summary_file.read_text())
    vlm_results = json.loads(vlm_file.read_text()) if vlm_file.exists() else []
    posture_events = json.loads(posture_file.read_text()) if posture_file.exists() else []
    posture_summary = (
        json.loads(posture_summary_file.read_text()) if posture_summary_file.exists() else {}
    )
    posture_vlm = json.loads(posture_vlm_file.read_text()) if posture_vlm_file.exists() else []
    meta_sam = json.loads(meta_sam_file.read_text()) if meta_sam_file.exists() else []

    return {
        "job_id": job_id,
        "summary": summary,
        "vlm_results": vlm_results,
        "posture_summary": posture_summary,
        "posture_events": posture_events,
        "posture_vlm": posture_vlm,
        "meta_sam": meta_sam,
    }


@router.get("/{job_id}/vlm")
def get_job_vlm(job_id: str):
    """Full VLM assessment for each temporal event window in this job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(status_code=409, detail=f"Job status is {job['status']}")

    vlm_file = Path(job["job_dir"]) / "vlm_assessments.json"
    if not vlm_file.exists():
        raise HTTPException(status_code=404, detail="VLM assessments not found")

    return json.loads(vlm_file.read_text())


@router.get("/{job_id}/frames/{filename}")
def get_job_frame(job_id: str, filename: str):
    """Serve a flagged frame or person crop image by filename."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dir = Path(job.get("job_dir", str(JOBS_DIR / job_id)))

    for subdir in ("frames", "crops", "posture_frames"):
        img_path = job_dir / subdir / filename
        if img_path.exists():
            return FileResponse(str(img_path), media_type="image/jpeg")

    raise HTTPException(status_code=404, detail="Frame not found")
