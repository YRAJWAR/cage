from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.enums import ShiftStatus
from app.models.safety import Device, Shift, Site, Worker
from app.schemas.shifts import ShiftOut
from app.schemas.workers import WorkerCheckin, WorkerOut, WorkerRegister

router = APIRouter(prefix="/workers", tags=["workers"])


@router.post("/register", status_code=201)
def register_worker(payload: WorkerRegister, db: Session = Depends(get_db)):
    site = db.query(Site).filter(Site.id == payload.site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    worker = Worker(
        site_id=payload.site_id,
        display_name=payload.display_name or None,
        appearance_embedding=payload.appearance_embedding or None,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return {"worker_id": worker.id}


@router.post("/checkin", status_code=201, response_model=ShiftOut)
def checkin_worker(payload: WorkerCheckin, db: Session = Depends(get_db)):
    """Bind a worker to a POV device for a day — opens (or reuses) their shift."""
    worker = db.query(Worker).filter(Worker.id == payload.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    device = db.query(Device).filter(Device.id == payload.pov_device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    shift = (
        db.query(Shift)
        .filter(Shift.worker_id == worker.id, Shift.date == payload.date)
        .first()
    )
    if shift:
        shift.pov_device_id = device.id  # re-checkin: update binding
    else:
        shift = Shift(
            worker_id=worker.id,
            site_id=worker.site_id,
            date=payload.date,
            pov_device_id=device.id,
            status=ShiftStatus.IN_PROGRESS,
        )
        db.add(shift)
    worker.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shift)
    return _fmt_shift(shift, events=[])


@router.get("", response_model=list[WorkerOut])
def list_workers(site_id: str, db: Session = Depends(get_db)):
    workers = db.query(Worker).filter(Worker.site_id == site_id).all()
    return [
        WorkerOut(
            worker_id=w.id,
            display_name=w.display_name,
            status=w.status,
            total_violations=w.total_violations or 0,
            total_compliant=w.total_compliant or 0,
            avg_msd_risk=w.avg_msd_risk or 0.0,
            last_seen_at=w.last_seen_at,
        )
        for w in workers
    ]


@router.get("/{worker_id}", response_model=WorkerOut)
def get_worker(worker_id: str, db: Session = Depends(get_db)):
    w = db.query(Worker).filter(Worker.id == worker_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Worker not found")
    return WorkerOut(
        worker_id=w.id,
        display_name=w.display_name,
        site_id=w.site_id,
        status=w.status,
        total_violations=w.total_violations or 0,
        total_compliant=w.total_compliant or 0,
        avg_msd_risk=w.avg_msd_risk or 0.0,
        created_at=w.created_at,
        last_seen_at=w.last_seen_at,
    )


def _fmt_shift(shift: Shift, events: list) -> dict:
    return {
        "shift_id": shift.id,
        "worker_id": shift.worker_id,
        "site_id": shift.site_id,
        "date": shift.date,
        "status": shift.status,
        "pov_device_id": shift.pov_device_id,
        "msd_risk_score": shift.msd_risk_score,
        "violation_count": shift.violation_count or 0,
        "compliant_count": shift.compliant_count or 0,
        "started_at": shift.started_at,
        "ended_at": shift.ended_at,
        "events": events,
    }
