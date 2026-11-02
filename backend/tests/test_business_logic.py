"""Regression tests for the business-logic audit fixes.

Each test locks a behavior that was previously wrong:
- posture angles (arm/neck reference vectors),
- wall-cam PPE evidence expiry / first-sighting gate / proximity pairs,
- DB event writing (distinct incidents, compliant log, no double count),
- shift reuse across check-in and upload, MSD score computation,
- worker avg MSD as a true mean, job records surviving restart.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Posture: angle conventions
# ---------------------------------------------------------------------------

from app.pipeline.posture import (  # noqa: E402
    _reba_group_b,
    angles_from_keypoints,
    risk_from_angles,
)


def _kp(points: dict[int, tuple[float, float]], conf: float = 0.95) -> np.ndarray:
    kp = np.zeros((17, 3), dtype=float)
    for idx, (x, y) in points.items():
        kp[idx] = (x, y, conf)
    return kp


# Upright worker facing the camera, arms hanging at their sides.
NEUTRAL = {
    0: (130, 70), 1: (122, 66), 2: (138, 66), 3: (112, 70), 4: (148, 70),
    5: (100, 100), 6: (160, 100), 7: (94, 162), 8: (166, 162),
    9: (92, 218), 10: (168, 218), 11: (106, 200), 12: (154, 200),
    13: (108, 290), 14: (152, 290), 15: (109, 380), 16: (151, 380),
}


def test_neutral_pose_angles_are_zeroed():
    angles = angles_from_keypoints(_kp(NEUTRAL))
    assert angles["trunk_flexion_deg"] < 5
    assert angles["neck_flexion_deg"] < 10  # was ~180 (flipped vector)
    assert angles["arm_raise_deg"] < 20     # was ~90 (wrong reference)


def test_neutral_pose_is_not_overreach():
    risk = risk_from_angles(angles_from_keypoints(_kp(NEUTRAL)))
    assert risk["violation_type"] != "OVERREACH"


def test_overhead_arm_scores_max_group_b():
    # Arm raised past 110° from hanging must not score the minimum.
    assert _reba_group_b({"arm_raise_deg": 170.0}) >= 4


def test_forward_horizontal_arm_is_overreach():
    risk = risk_from_angles(
        {"arm_raise_deg": 90.0, "trunk_flexion_deg": 10.0, "keypoint_confidence": 0.95}
    )
    assert risk["violation_type"] == "OVERREACH"
    assert risk["risk_level"] >= 3


def test_extreme_trunk_flexion_is_a_violation():
    risk = risk_from_angles(
        {"trunk_flexion_deg": 70.0, "keypoint_confidence": 0.95}
    )
    assert not risk["good_posture"]
    assert risk["violation_type"] in ("AWKWARD_POSTURE", "MSD_HIGH_RISK")


# ---------------------------------------------------------------------------
# Wall-cam: PPE evidence window, warm-up gate, proximity identity
# ---------------------------------------------------------------------------

from app.pipeline.wall_cam import _process_frame  # noqa: E402


class _T:
    def __init__(self, arr):
        self._a = np.array(arr, dtype=float)

    def cpu(self):
        return self

    def numpy(self):
        return self._a

    def int(self):
        return self


class _Boxes:
    def __init__(self, dets):
        self.xyxy = _T([d[0] for d in dets] or np.zeros((0, 4)))
        self.conf = _T([d[1] for d in dets])
        self.cls = _T([d[2] for d in dets])
        self.id = _T([d[3] for d in dets]) if dets else None


class _Result:
    def __init__(self, dets):
        self.boxes = _Boxes(dets)

    def plot(self):
        return np.zeros((480, 640, 3), dtype=np.uint8)


class _FakeYOLO:
    names = {0: "person", 1: "helmet", 2: "vest", 3: "gloves", 4: "excavator"}

    def __init__(self):
        self.dets: list = []

    def track(self, frame, **kw):
        return [_Result(self.dets)]


WORKER = ([50, 50, 250, 450], 0.9, 0, 1)
HELMET = ([120, 60, 180, 110], 0.9, 1, 11)
VEST = ([110, 180, 190, 300], 0.9, 2, 12)
GLOVES = ([90, 320, 130, 360], 0.9, 3, 13)
FRAME = np.zeros((480, 640, 3), dtype=np.uint8)


def _run(yolo, log, idx, dets):
    yolo.dets = dets
    _, hazards, _ = _process_frame(FRAME, idx, 25.0, yolo, None, log, 0.15, 0.25)
    return [h["hazard_type"] for h in hazards]


def test_no_missing_ppe_on_first_sighting():
    yolo, log = _FakeYOLO(), {}
    assert not any(t.startswith("missing_") for t in _run(yolo, log, 0, [WORKER]))


def test_removed_ppe_is_reflagged():
    yolo, log = _FakeYOLO(), {}
    _run(yolo, log, 0, [WORKER])
    for i in (3, 6, 9):
        _run(yolo, log, i, [WORKER, HELMET, VEST, GLOVES])
    late: list = []
    for i in range(30, 330, 3):  # helmet gone for a long stretch
        late = _run(yolo, log, i, [WORKER, VEST, GLOVES])
    assert "missing_hardhat" in late


def test_proximity_keeps_distinct_pairs():
    yolo, log = _FakeYOLO(), {}
    w2 = ([350, 50, 550, 450], 0.9, 0, 2)
    equip = ([240, 200, 360, 320], 0.9, 4, 21)  # near both workers
    hazards = _run(yolo, log, 0, [WORKER, w2, equip])
    prox = [t for t in hazards if t == "heavy_equipment_proximity"]
    assert len(prox) == 2  # was collapsed to 1 (dedup key had no identity)


# ---------------------------------------------------------------------------
# DB write path: incidents, compliant log, counters
# ---------------------------------------------------------------------------

from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import CameraSource, EventCategory  # noqa: E402
from app.models.safety import SafetyEvent, Shift, Site, Worker  # noqa: E402
from app.services.jobs import _write_events_to_db  # noqa: E402


def _seed_shift(client):
    db = SessionLocal()
    site = Site(name="Audit Site")
    db.add(site)
    db.commit()
    worker = Worker(site_id=site.id, display_name="W-AUDIT")
    db.add(worker)
    db.commit()
    shift = Shift(worker_id=worker.id, site_id=site.id, date="2026-10-31")
    db.add(shift)
    db.commit()
    ids = (shift.id, worker.id)
    db.close()
    return ids


def _chunk(ts, hazards, ppe):
    return {
        "event": {"start_ts": ts, "end_ts": ts + 5, "duration_seconds": 5,
                  "frame_count": 4, "representative_timestamp": ts,
                  "representative_frame_path": "frame.jpg", "chunk_index": int(ts)},
        "vlm": {"scene_summary": "s", "reasoning": "r", "confidence": "HIGH",
                "hazards": hazards, "ppe_per_worker": ppe, "worker_count": 1,
                "equipment_present": [], "no_hazards": not hazards},
        "error": None,
    }


_HZ = {"violation_type": "PPE_MISSING", "severity": "HIGH",
       "explanation": "e", "recommendation": "r", "best_frame_path": None}
_OK_PPE = [{"helmet": "PRESENT", "vest": "PRESENT", "gloves": "PRESENT"}]


def test_distinct_incidents_and_compliant_events_written(client):
    shift_id, worker_id = _seed_shift(client)
    db = SessionLocal()
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    vlm_results = [
        _chunk(10.0, [dict(_HZ)], []),            # incident at t=10
        _chunk(200.0, [dict(_HZ)], _OK_PPE),      # incident at t=200 + compliant
    ]
    _write_events_to_db(
        db=db, shift=shift, worker=worker, camera_source=CameraSource.WALL_CAM,
        hazard_events=[], vlm_results=vlm_results,
        posture_events=[], posture_vlm_results=[],
    )
    db.commit()
    rows = db.query(SafetyEvent).filter(SafetyEvent.shift_id == shift_id).all()
    viol = [r for r in rows if r.event_category == EventCategory.VIOLATION]
    comp = [r for r in rows if r.event_category == EventCategory.COMPLIANT]
    db.refresh(shift)
    db.refresh(worker)
    assert len(viol) == 2       # was 1 (shift-wide type dedup)
    assert len(comp) == 1       # was 0 (compliant log never written)
    assert shift.violation_count == 2 and shift.compliant_count == 1
    assert worker.total_violations == 2 and worker.total_compliant == 1
    db.close()


def test_posture_vlm_supersedes_raw_posture_events(client):
    shift_id, worker_id = _seed_shift(client)
    db = SessionLocal()
    shift = db.query(Shift).filter(Shift.id == shift_id).first()
    worker = db.query(Worker).filter(Worker.id == worker_id).first()
    raw = [{"violation_type": "AWKWARD_POSTURE", "risk_level": 3,
            "timestamp_seconds": 5.0, "track_id": 1, "frame_path": "f.jpg",
            "confidence": 0.9, "angles": {}, "reason_short": "r", "bbox": None}]
    vlm_chunk = _chunk(5.0, [{"violation_type": "AWKWARD_POSTURE",
                              "severity": "HIGH", "explanation": "e",
                              "recommendation": "r", "best_frame_path": None}], [])
    _write_events_to_db(
        db=db, shift=shift, worker=worker, camera_source=CameraSource.POV,
        hazard_events=[], vlm_results=[], posture_events=raw,
        posture_vlm_results=[vlm_chunk],
    )
    db.commit()
    rows = db.query(SafetyEvent).filter(SafetyEvent.shift_id == shift_id).all()
    assert len(rows) == 1  # was 2 (raw + VLM double-counted the same incident)
    db.close()


# ---------------------------------------------------------------------------
# Shift reuse + MSD score through the real job entry point
# ---------------------------------------------------------------------------

from app.models.enums import ShiftStatus  # noqa: E402
from app.services import jobs as jobs_service  # noqa: E402


def test_job_reuses_checkin_shift_and_sets_msd(client, site, worker, device, tmp_path, monkeypatch):
    import app.pipeline.posture as posture_mod
    import app.pipeline.wall_cam as wall_mod

    monkeypatch.setattr(wall_mod, "_get_yolo", lambda: None)
    monkeypatch.setattr(wall_mod, "_get_sam", lambda: None)
    monkeypatch.setattr(
        wall_mod, "run_wall_cam_pipeline",
        lambda **kw: (
            {"frames_processed": 10, "frames_with_hazards": 0, "workers_tracked": 1},
            [],
            [],
        ),
    )
    monkeypatch.setattr(
        posture_mod, "run_posture_pipeline",
        lambda **kw: (
            {"events": 2},
            [
                {"risk_level": 3, "violation_type": "AWKWARD_POSTURE",
                 "timestamp_seconds": 1.0, "track_id": 1},
                {"risk_level": 2, "violation_type": "AWKWARD_POSTURE",
                 "timestamp_seconds": 2.0, "track_id": 2},
            ],
        ),
    )
    monkeypatch.setattr(posture_mod, "run_posture_vlm", lambda **kw: [])

    # Check-in opens the shift for 2026-10-30.
    res = client.post("/workers/checkin", json={
        "worker_id": worker["worker_id"], "pov_device_id": device["id"],
        "date": "2026-10-30",
    })
    assert res.status_code == 201
    checkin_shift_id = res.json()["shift_id"]

    video = tmp_path / "source.mp4"
    video.write_bytes(b"fake")
    job_dir = tmp_path / "job1"
    job_dir.mkdir()
    jobs_service.run_detection_job(
        "job-test-1", job_dir, video, site["id"], "2026-10-30",
        worker["worker_id"], CameraSource.POV,
    )

    db = SessionLocal()
    shifts = (
        db.query(Shift)
        .filter(Shift.worker_id == worker["worker_id"], Shift.date == "2026-10-30")
        .all()
    )
    assert len(shifts) == 1                 # was 2 (check-in + upload)
    assert shifts[0].id == checkin_shift_id
    assert shifts[0].status == ShiftStatus.COMPLETED
    assert shifts[0].msd_risk_score == pytest.approx(2.5)  # mean of 3 and 2
    w = db.query(Worker).filter(Worker.id == worker["worker_id"]).first()
    assert w.avg_msd_risk == pytest.approx(2.5)
    db.close()
    jobs_service.jobs.pop("job-test-1", None)


def test_worker_avg_msd_is_a_mean_not_latest(client, worker, device):
    for date, score in (("2026-10-28", 2.0), ("2026-10-29", 4.0)):
        res = client.post("/workers/checkin", json={
            "worker_id": worker["worker_id"], "pov_device_id": device["id"],
            "date": date,
        })
        assert res.status_code == 201
        res = client.patch(
            f"/shifts/{res.json()['shift_id']}/close",
            json={"msd_risk_score": score},
        )
        assert res.status_code == 200
    res = client.get(f"/workers/{worker['worker_id']}")
    assert res.json()["avg_msd_risk"] == pytest.approx(3.0)  # was 4.0 (overwrite)


# ---------------------------------------------------------------------------
# Job records survive a restart (hydration)
# ---------------------------------------------------------------------------

from app.core.config import settings  # noqa: E402


def test_hydrate_jobs_restores_completed_and_fails_interrupted(client):
    base = settings.jobs_dir
    for job_id, status in (("hydrate-done", "COMPLETED"), ("hydrate-stuck", "PROCESSING")):
        d = base / job_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "job_meta.json").write_text(json.dumps({
            "status": status, "events_written": 3, "error": None,
            "job_dir": str(d), "shift_id": None, "camera_source": "POV",
            "progress": 1.0, "stage": "completed",
        }))
    try:
        restored = jobs_service.hydrate_jobs()
        assert restored >= 2
        assert jobs_service.jobs["hydrate-done"]["status"] == "COMPLETED"
        stuck = jobs_service.jobs["hydrate-stuck"]
        assert stuck["status"] == "FAILED"  # can never finish after restart
        assert "restart" in stuck["error"]
    finally:
        jobs_service.jobs.pop("hydrate-done", None)
        jobs_service.jobs.pop("hydrate-stuck", None)
