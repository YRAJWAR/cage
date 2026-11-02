import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.shifts import _fmt_event
from app.models.enums import EventCategory
from app.models.safety import SafetyEvent, Shift, Worker
from app.schemas.events import EventIngest, EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest", status_code=201, response_model=EventOut)
def ingest_event(payload: EventIngest, db: Session = Depends(get_db)):
    """Write one safety event (called by ML pipelines)."""
    shift = db.query(Shift).filter(Shift.id == payload.shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    worker = db.query(Worker).filter(Worker.id == payload.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    event = SafetyEvent(
        shift_id=payload.shift_id,
        worker_id=payload.worker_id,
        camera_source=payload.camera_source,
        event_category=payload.event_category,
        violation_type=payload.violation_type,
        severity=payload.severity,
        video_timestamp=payload.video_timestamp,
        clip_path=payload.clip_path,
        metadata_json=json.dumps(payload.metadata) if payload.metadata else None,
    )
    db.add(event)
    if payload.event_category == EventCategory.VIOLATION:
        shift.violation_count = (shift.violation_count or 0) + 1
        worker.total_violations = (worker.total_violations or 0) + 1
    else:
        shift.compliant_count = (shift.compliant_count or 0) + 1
        worker.total_compliant = (worker.total_compliant or 0) + 1
    db.commit()
    db.refresh(event)
    return _fmt_event(event)


@router.get("", response_model=list[EventOut])
def list_events(
    worker_id: str | None = None,
    shift_id: str | None = None,
    event_category: EventCategory | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(SafetyEvent)
    if worker_id:
        q = q.filter(SafetyEvent.worker_id == worker_id)
    if shift_id:
        q = q.filter(SafetyEvent.shift_id == shift_id)
    if event_category:
        q = q.filter(SafetyEvent.event_category == event_category)
    return [_fmt_event(e) for e in q.all()]
