"""Background video-processing jobs.

Heavy pipeline imports stay inside functions so the API can boot (and be
tested) on machines without torch / model weights installed.
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.enums import CameraSource, EventCategory, Severity, ShiftStatus
from app.models.safety import SafetyEvent, Shift, Worker

JOBS_DIR = settings.jobs_dir
JOBS_DIR.mkdir(parents=True, exist_ok=True)

# Job store (single-process). Entries are mirrored to job_meta.json in
# each job dir so completed reports survive a backend restart; see
# hydrate_jobs(). A persistent queue is future work.
jobs: dict[str, dict] = {}


def refresh_worker_avg_msd(db, worker_id: str) -> None:
    """Recompute a worker's avg MSD risk as the mean of their completed
    shifts' scores. (A plain overwrite with the latest score is not an
    average and made the figure jump per shift.)"""
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    if not worker:
        return
    scores = [
        s.msd_risk_score
        for s in db.query(Shift)
        .filter(
            Shift.worker_id == worker_id,
            Shift.status == ShiftStatus.COMPLETED,
            Shift.msd_risk_score.isnot(None),
        )
        .all()
    ]
    worker.avg_msd_risk = round(sum(scores) / len(scores), 2) if scores else 0.0
    db.commit()


def _persist_job_meta(job_id: str) -> None:
    job = jobs.get(job_id)
    if not job or not job.get("job_dir"):
        return
    meta_path = Path(job["job_dir"]) / "job_meta.json"
    try:
        meta_path.write_text(json.dumps(job, indent=2, default=str))
    except OSError as exc:
        print(f"[job] WARNING: could not persist meta for {job_id}: {exc}")


def hydrate_jobs() -> int:
    """Rebuild the in-memory job store from job_meta.json files on disk.

    Jobs left PROCESSING by a restart are marked FAILED — their worker
    thread is gone, so they can never complete.
    """
    restored = 0
    if not JOBS_DIR.exists():
        return 0
    for meta_path in sorted(JOBS_DIR.glob("*/job_meta.json")):
        try:
            job = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        job_id = meta_path.parent.name
        if job_id in jobs:
            continue
        job.setdefault("job_dir", str(meta_path.parent))
        if job.get("status") == "PROCESSING":
            job["status"] = "FAILED"
            job["error"] = "interrupted by server restart"
            job["progress"] = 1.0
            job["stage"] = "failed"
        jobs[job_id] = job
        restored += 1
    if restored:
        print(f"[job] restored {restored} job record(s) from disk")
    return restored


def set_progress(job_id: str, progress: float, stage: str) -> None:
    if job_id in jobs:
        jobs[job_id]["progress"] = max(0.0, min(1.0, progress))
        jobs[job_id]["stage"] = stage


def resolve_worker_code(worker_id: str | None) -> str:
    """Worker ID is optional on upload — mint an opaque code when absent."""
    if worker_id and worker_id.strip():
        return worker_id.strip()
    return f"W-{uuid.uuid4().hex[:8].upper()}"


def create_job(
    video: UploadFile, worker_id: str, site_id: str, date: str
) -> tuple[str, Path, Path]:
    """Persist the upload and register a PROCESSING job. Returns (job_id, job_dir, video_path)."""
    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / "source.mp4"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)
    jobs[job_id] = {
        "status": "PROCESSING",
        "events_written": 0,
        "error": None,
        "job_dir": str(job_dir),
        "camera_source": None,
    }
    set_progress(job_id, 0.02, "queued")
    _persist_job_meta(job_id)
    print(f"[job] submit job={job_id} worker={worker_id} site={site_id} date={date}")
    return job_id, job_dir, video_path


def run_detection_job(
    job_id: str,
    job_dir: Path,
    video_path: Path,
    site_id: str,
    date: str,
    worker_id: str,
    camera_source: CameraSource,
):
    import traceback

    print(
        f"[{camera_source}] {job_id} — start, video={video_path}, "
        f"size={video_path.stat().st_size if video_path.exists() else 0}"
    )
    db = SessionLocal()
    try:
        # Find or create worker
        worker = db.query(Worker).filter(Worker.id == worker_id).first()
        if not worker:
            # Try by display_name for convenience
            worker = db.query(Worker).filter(Worker.display_name == worker_id).first()
        if not worker:
            worker = Worker(site_id=site_id, display_name=worker_id)
            db.add(worker)
            db.commit()
            db.refresh(worker)
            print(f"[{camera_source}] {job_id} — auto-created worker {worker.id} ({worker_id})")

        # Reuse the worker's open shift for this date when one exists
        # (e.g. opened by POV check-in) — an upload is footage FOR that
        # shift, not a new one. Otherwise create it. Uses the resolved
        # worker.id, not the raw form string.
        shift = (
            db.query(Shift)
            .filter(
                Shift.worker_id == worker.id,
                Shift.date == date,
                Shift.status == ShiftStatus.IN_PROGRESS,
            )
            .first()
        )
        if shift is None:
            shift = Shift(worker_id=worker.id, site_id=site_id, date=date)
            db.add(shift)
            db.commit()
            db.refresh(shift)
            print(f"[{camera_source}] {job_id} — shift created: {shift.id}")
        else:
            print(f"[{camera_source}] {job_id} — reusing open shift: {shift.id}")

        # Step 1 — model warm-up
        print(f"[{camera_source}] {job_id} — [1/5] loading YOLO + SAM")
        set_progress(job_id, 0.10, "warming models")
        from app.pipeline.wall_cam import _get_sam, _get_yolo

        _get_yolo()
        if settings.sam_backend == "meta":
            print(f"[{camera_source}] {job_id} — SAM backend=meta, skipping local SAM")
        else:
            _get_sam()
        print(f"[{camera_source}] {job_id} — [1/5] models ready")
        set_progress(job_id, 0.18, "models ready")

        # Step 2 — YOLO + SAM pipeline
        print(f"[{camera_source}] {job_id} — [2/5] running YOLO+SAM pipeline")
        set_progress(job_id, 0.25, "running yolo+sam")
        from app.pipeline.wall_cam import run_wall_cam_pipeline

        summary, hazard_events, vlm_results = run_wall_cam_pipeline(
            video_path=video_path,
            job_dir=job_dir,
            site_id=site_id,
            date=date,
            camera_source=camera_source.value,
        )
        print(
            f"[{camera_source}] {job_id} — [2/5] pipeline done: "
            f"{summary['frames_processed']} frames, "
            f"{summary['frames_with_hazards']} hazard frames, "
            f"{summary['workers_tracked']} workers"
        )
        set_progress(job_id, 0.45, "pipeline done")

        # Step 3 — Posture pipeline (ergonomic) kicked async to overlap with VLM prep
        from app.pipeline.posture import run_posture_pipeline, run_posture_vlm

        posture_summary = {}
        posture_events = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _posture_pool:
            posture_future = _posture_pool.submit(
                run_posture_pipeline,
                video_path=video_path,
                job_dir=job_dir,
            )

            # Step 4 — VLM (may have errored; fallback to YOLO results)
            valid_vlm = [r for r in vlm_results if r.get("vlm") and not r.get("error")]
            errored_vlm = [r for r in vlm_results if r.get("error")]
            print(
                f"[{camera_source}] {job_id} — [4/6] VLM: "
                f"{len(valid_vlm)} valid, {len(errored_vlm)} errored of {len(vlm_results)} events"
            )
            if errored_vlm:
                print(f"[{camera_source}] {job_id} — VLM errors: {[r['error'] for r in errored_vlm[:3]]}")
            set_progress(job_id, 0.55, "vlm")

            # Wait for posture to finish
            try:
                posture_summary, posture_events = posture_future.result()
                print(f"[{camera_source}] {job_id} — posture: {posture_summary.get('events', 0)} risk frames")
                set_progress(job_id, 0.65, "posture done")
            except Exception as pe_err:
                print(f"[{camera_source}] {job_id} — posture pipeline failed: {pe_err}")
                posture_summary, posture_events = {}, []

        # Step 5 — Posture VLM (reuse VLM structure for posture hazards)
        print(f"[{camera_source}] {job_id} — [5/6] running posture VLM")
        posture_vlm_results = run_posture_vlm(
            video_path=video_path,
            job_dir=job_dir,
            posture_events=posture_events,
            posture_summary=posture_summary,
            camera_source="POSTURE",
        )
        print(f"[{camera_source}] {job_id} — posture VLM chunks: {len(posture_vlm_results)}")
        set_progress(job_id, 0.8, "posture vlm")

        # Step 6 — DB write
        print(f"[{camera_source}] {job_id} — [6/6] writing events to DB")
        events_written = _write_events_to_db(
            db=db,
            shift=shift,
            worker=worker,
            camera_source=camera_source,
            hazard_events=hazard_events,
            vlm_results=vlm_results,
            posture_events=posture_events,
            posture_vlm_results=posture_vlm_results,
            summary=summary,
        )

        # Ergonomic score for the shift: mean posture risk level (1–4)
        # across flagged frames. Previously computed by the pipeline and
        # then discarded, leaving every MSD figure at 0.
        if posture_events:
            shift.msd_risk_score = round(
                sum(pe.get("risk_level", 1) for pe in posture_events) / len(posture_events),
                2,
            )

        shift.status = ShiftStatus.COMPLETED
        shift.ended_at = datetime.now(timezone.utc)
        worker.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        refresh_worker_avg_msd(db, worker.id)
        print(f"[{camera_source}] {job_id} — {events_written} events written to SQLite")
        set_progress(job_id, 0.98, "db written")

        jobs[job_id] = {
            "status": "COMPLETED",
            "events_written": events_written,
            "error": None,
            "summary": summary,
            "posture_summary": posture_summary,
            "job_dir": str(job_dir),
            "shift_id": shift.id,
            "camera_source": camera_source.value,
            "progress": 1.0,
            "stage": "completed",
        }
        _persist_job_meta(job_id)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{camera_source}] {job_id} — FAILED: {e}\n{tb}")
        db.rollback()
        jobs[job_id] = {
            "status": "FAILED",
            "events_written": 0,
            "error": str(e),
            "progress": 1.0,
            "stage": "failed",
            "job_dir": str(job_dir),
            "camera_source": camera_source.value,
        }
        _persist_job_meta(job_id)
    finally:
        db.close()
        video_path.unlink(missing_ok=True)
        print(f"[{camera_source}] {job_id} — source video cleaned up")


def _write_events_to_db(
    *,
    db,
    shift: Shift,
    worker: Worker,
    camera_source: CameraSource,
    hazard_events: list,
    vlm_results: list,
    posture_events: list,
    posture_vlm_results: list,
    summary: dict | None = None,
) -> int:
    """Persist pipeline outputs as SafetyEvents. Returns events written."""
    # If VLM ran: use VLM-confirmed hazards (higher quality).
    # If VLM produced nothing: fall back to raw YOLO hazard frames.
    events_written = 0
    seen_violations: set = set()

    if any(r.get("vlm") and not r.get("error") for r in vlm_results):
        for result in vlm_results:
            if result["error"] or not result["vlm"]:
                continue
            ev = result["event"]
            vlm = result["vlm"]
            # Every confirmed hazard is a distinct incident (its own time
            # window, often a different worker). A former shift-wide dedup
            # on violation_type alone silently dropped all but the first.
            for hazard in vlm["hazards"]:
                vtype = hazard.get("violation_type")
                sev_str = hazard.get("severity", "MEDIUM")
                severity = Severity[sev_str] if sev_str in Severity.__members__ else Severity.MEDIUM
                event = SafetyEvent(
                    shift_id=shift.id,
                    worker_id=worker.id,
                    camera_source=camera_source,
                    event_category=EventCategory.VIOLATION,
                    violation_type=vtype,
                    severity=severity,
                    video_timestamp=ev["representative_timestamp"],
                    clip_path=hazard.get("best_frame_path") or ev.get("representative_frame_path"),
                    metadata_json=json.dumps(
                        {
                            "explanation": hazard.get("explanation"),
                            "recommendation": hazard.get("recommendation"),
                            "scene_summary": vlm.get("scene_summary"),
                            "reasoning": vlm.get("reasoning"),
                            "confidence": vlm.get("confidence"),
                            "ppe_per_worker": vlm.get("ppe_per_worker"),
                            "event_start_ts": ev["start_ts"],
                            "event_end_ts": ev["end_ts"],
                            "event_duration_s": ev["duration_seconds"],
                            "event_frame_count": ev["frame_count"],
                            "yolo_hazard_types": ev.get("yolo_hazard_types"),
                        }
                    ),
                )
                db.add(event)
                shift.violation_count += 1
                worker.total_violations += 1
                events_written += 1
            # Compliant-behavior log: one COMPLIANT event per worker the
            # VLM confirmed fully geared (helmet + vest + gloves PRESENT).
            for ppe in vlm.get("ppe_per_worker") or []:
                status = ppe if isinstance(ppe, dict) else {}
                if all(status.get(k) == "PRESENT" for k in ("helmet", "vest", "gloves")):
                    db.add(SafetyEvent(
                        shift_id=shift.id,
                        worker_id=worker.id,
                        camera_source=camera_source,
                        event_category=EventCategory.COMPLIANT,
                        violation_type=None,
                        severity=None,
                        video_timestamp=ev["representative_timestamp"],
                        clip_path=ev.get("representative_frame_path"),
                        metadata_json=json.dumps(
                            {"source": "VLM", "ppe_status": status,
                             "scene_summary": vlm.get("scene_summary")}
                        ),
                    ))
                    shift.compliant_count += 1
                    worker.total_compliant += 1
                    events_written += 1
    else:
        # VLM produced nothing — write one SafetyEvent per unique
        # (track_id, violation_type) pair from YOLO.
        for frame in hazard_events:
            for hazard in frame.get("hazards", []):
                dedup_key = (hazard.get("track_id"), hazard.get("violation_type", "PPE_MISSING"))
                if dedup_key in seen_violations:
                    continue
                seen_violations.add(dedup_key)
                sev_str = hazard.get("severity", "MEDIUM")
                severity = Severity[sev_str] if sev_str in Severity.__members__ else Severity.MEDIUM
                event = SafetyEvent(
                    shift_id=shift.id,
                    worker_id=worker.id,
                    camera_source=camera_source,
                    event_category=EventCategory.VIOLATION,
                    violation_type=hazard.get("violation_type", "PPE_MISSING"),
                    severity=severity,
                    video_timestamp=frame["timestamp_seconds"],
                    clip_path=frame.get("frame_path"),
                    metadata_json=json.dumps(
                        {
                            "hazard_type": hazard.get("hazard_type"),
                            "description": hazard.get("description"),
                            "track_id": hazard.get("track_id"),
                            "ppe_worn": hazard.get("ppe_worn"),
                            "ppe_missing": hazard.get("ppe_missing"),
                            "yolo_hazard_types": [hazard.get("hazard_type")],
                        }
                    ),
                )
                db.add(event)
                shift.violation_count += 1
                worker.total_violations += 1
                events_written += 1
        # Compliant-behavior log (fallback): one COMPLIANT event per
        # tracked worker whose final PPE state is complete.
        last_ts = hazard_events[-1]["timestamp_seconds"] if hazard_events else 0.0
        for tid, state in (summary or {}).get("worker_compliance", {}).items():
            if not state.get("compliant"):
                continue
            db.add(SafetyEvent(
                shift_id=shift.id,
                worker_id=worker.id,
                camera_source=camera_source,
                event_category=EventCategory.COMPLIANT,
                violation_type=None,
                severity=None,
                video_timestamp=last_ts,
                clip_path=None,
                metadata_json=json.dumps(
                    {"source": "YOLO", "track_id": tid,
                     "ppe_confirmed": state.get("ppe_confirmed")}
                ),
            ))
            shift.compliant_count += 1
            worker.total_compliant += 1
            events_written += 1

    # Raw posture events are skipped when the posture VLM produced a valid
    # assessment — the VLM pass covers the same incidents, and writing both
    # double-counted them (mirrors the PPE VLM/fallback split above).
    posture_vlm_valid = any(
        chunk.get("vlm") and not chunk.get("error") for chunk in posture_vlm_results
    )

    # Posture events → DB (non-compliant only)
    for pe in [] if posture_vlm_valid else posture_events:
        if pe.get("violation_type") == "COMPLIANT_BEHAVIOR":
            continue
        severity = Severity.HIGH if pe.get("risk_level", 1) >= 3 else Severity.MEDIUM
        dedup_key = (pe.get("track_id"), pe.get("violation_type"), "POSTURE_RAW")
        if dedup_key in seen_violations:
            continue
        seen_violations.add(dedup_key)
        event = SafetyEvent(
            shift_id=shift.id,
            worker_id=worker.id,
            camera_source=camera_source,
            event_category=EventCategory.VIOLATION,
            violation_type=pe.get("violation_type"),
            severity=severity,
            video_timestamp=pe.get("timestamp_seconds"),
            clip_path=pe.get("frame_path"),
            metadata_json=json.dumps(
                {
                    "risk_level": pe.get("risk_level"),
                    "confidence": pe.get("confidence"),
                    "angles": pe.get("angles"),
                    "reason_short": pe.get("reason_short"),
                    "track_id": pe.get("track_id"),
                    "bbox": pe.get("bbox"),
                }
            ),
        )
        db.add(event)
        shift.violation_count += 1
        worker.total_violations += 1
        events_written += 1

    # Posture VLM events → DB (VLM-confirmed posture hazards)
    for chunk in posture_vlm_results:
        if chunk.get("error") or not chunk.get("vlm"):
            continue
        ev = chunk["event"]
        vlm = chunk["vlm"]
        for hazard in vlm.get("hazards", []):
            vtype = hazard.get("violation_type")
            sev_str = hazard.get("severity", "MEDIUM")
            severity = Severity[sev_str] if sev_str in Severity.__members__ else Severity.MEDIUM
            event = SafetyEvent(
                shift_id=shift.id,
                worker_id=worker.id,
                camera_source=camera_source,
                event_category=EventCategory.VIOLATION,
                violation_type=vtype,
                severity=severity,
                video_timestamp=ev.get("representative_timestamp", ev.get("start_ts")),
                clip_path=hazard.get("best_frame_path") or ev.get("representative_frame_path"),
                metadata_json=json.dumps(
                    {
                        "source": "POSTURE_VLM",
                        "scene_summary": vlm.get("scene_summary"),
                        "reasoning": vlm.get("reasoning"),
                        "confidence": vlm.get("confidence"),
                        "risk_level": hazard.get("severity"),
                        "best_frame_path": hazard.get("best_frame_path"),
                        "chunk_index": ev.get("chunk_index"),
                    }
                ),
            )
            db.add(event)
            shift.violation_count += 1
            worker.total_violations += 1
            events_written += 1

    return events_written
