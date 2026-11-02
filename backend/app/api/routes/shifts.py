import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.workers import _fmt_shift
from app.models.enums import ShiftStatus
from app.models.safety import SafetyEvent, Shift
from app.schemas.shifts import ShiftClose, ShiftOut

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.get("/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: str, db: Session = Depends(get_db)):
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    events = db.query(SafetyEvent).filter(SafetyEvent.shift_id == shift_id).all()
    return _fmt_shift(shift, events=[_fmt_event(e) for e in events])


@router.patch("/{shift_id}/close", response_model=ShiftOut)
def close_shift(shift_id: str, payload: ShiftClose, db: Session = Depends(get_db)):
    """Mark a shift completed, optionally setting its MSD risk score."""
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    shift.status = ShiftStatus.COMPLETED
    shift.ended_at = datetime.now(timezone.utc)
    if payload.msd_risk_score is not None:
        shift.msd_risk_score = payload.msd_risk_score
    db.commit()
    if payload.msd_risk_score is not None:
        # avg_msd_risk is a mean across completed shifts, not the latest
        # value — recompute it properly.
        from app.services.jobs import refresh_worker_avg_msd

        refresh_worker_avg_msd(db, shift.worker_id)
    db.refresh(shift)
    events = db.query(SafetyEvent).filter(SafetyEvent.shift_id == shift_id).all()
    return _fmt_shift(shift, events=[_fmt_event(e) for e in events])


def _fmt_event(e: SafetyEvent) -> dict:
    return {
        "event_id": e.id,
        "shift_id": e.shift_id,
        "worker_id": e.worker_id,
        "camera_source": e.camera_source,
        "event_category": e.event_category,
        "violation_type": e.violation_type,
        "severity": e.severity,
        "video_timestamp": e.video_timestamp,
        "clip_path": e.clip_path,
        "metadata": json.loads(e.metadata_json) if e.metadata_json else None,
        "created_at": str(e.created_at),
    }
