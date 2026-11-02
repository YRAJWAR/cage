"""
wall_cam.py — YOLO + SAM3 pipeline for CAGE wall camera analysis

Per-frame flow:
  1. YOLO (last.pt) + BoT-SORT tracker  → bounding boxes + persistent track IDs
  2. SAM3 (sam3.pt)                      → pixel-level masks from YOLO boxes
  3. PPE association                     → link gear to workers via center-point containment
  4. Violation detection                 → "no_*" classes + missing required PPE per worker
  5. Save SAM3-annotated frames          → VLM step consumes these

Outputs written to job_dir:
  detections.jsonl     — one record per sampled frame
  hazard_events.json   — frames with violations
  summary.json         — aggregate counts
  frames/              — SAM3-annotated JPEGs of flagged frames
  crops/               — padded person crops for VLM
"""

from __future__ import annotations

import json
import cv2
import torch
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image
from ultralytics import YOLO, SAM

from app.pipeline.vlm_step import assess_all_events

# ---------------------------------------------------------------------------
# GPU optimisations (no-op on CPU)
# ---------------------------------------------------------------------------

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
torch.backends.cudnn.benchmark = True

# ---------------------------------------------------------------------------
# Model paths
# ---------------------------------------------------------------------------

from app.core.config import settings as _settings

YOLO_MODEL_PATH = _settings.yolo_model_path
SAM_MODEL_PATH  = _settings.sam_model_path

# ---------------------------------------------------------------------------
# Class normalisation
# ---------------------------------------------------------------------------

CLASS_MAP: Dict[str, str] = {
    # Person
    "person": "worker", "construction worker": "worker", "worker": "worker",
    # Positive PPE
    "helmet": "hardhat", "hardhat": "hardhat", "hard hat": "hardhat",
    "gloves": "gloves", "glove": "gloves",
    "vest": "safety_vest", "safety vest": "safety_vest", "safety_vest": "safety_vest",
    "high visibility vest": "safety_vest",
    # Negative PPE (direct YOLO violations)
    "no helmet": "no_hardhat", "no hardhat": "no_hardhat", "no_hardhat": "no_hardhat",
    "no gloves": "no_gloves", "no_gloves": "no_gloves",
    "no vest": "no_safety_vest", "no safety vest": "no_safety_vest", "no_safety_vest": "no_safety_vest",
    # Equipment
    "machinery": "excavator", "excavator": "excavator",
    "vehicle": "dump_truck",  "truck": "dump_truck", "dump_truck": "dump_truck",
    "crane": "crane", "forklift": "forklift",
    "ladder": "ladder", "scaffold": "scaffold", "scaffolding": "scaffold",
    "safety cone": "safety_cone", "cone": "safety_cone",
}

REQUIRED_PPE  = {"hardhat", "safety_vest", "gloves"}
POSITIVE_PPE  = {"hardhat", "safety_vest", "gloves"}
EQUIPMENT     = {"excavator", "dump_truck", "crane", "forklift"}

# violation_type per missing PPE item
PPE_VIOLATION_TYPE = {
    "hardhat":    "PPE_MISSING",
    "safety_vest": "PPE_MISSING",
    "gloves":     "PPE_MISSING",
}

# PPE evidence expires: an item only counts as "worn" if it was associated
# with the worker within this many raw frames (~3.6 s at 25 fps). Without
# expiry, one early sighting marked the item worn for the whole shift and
# removed PPE was never re-flagged.
PPE_EVIDENCE_WINDOW = 90
# Sampled frames a track must be observed before missing-PPE hazards fire,
# so first-sighting frames (gear not yet associated) don't false-positive.
MIN_TRACK_OBSERVATIONS = 3


def _worn_items(entry: dict, frame_idx: int) -> set:
    """PPE items with fresh evidence for a worker_safety_log entry."""
    return {
        item
        for item, seen_at in entry["ppe_last_seen"].items()
        if frame_idx - seen_at <= PPE_EVIDENCE_WINDOW
    }

# ---------------------------------------------------------------------------
# Model singletons
# ---------------------------------------------------------------------------

_yolo: Optional[YOLO] = None
_sam:  Optional[SAM]  = None


def _get_yolo() -> YOLO:
    global _yolo
    if _yolo is None:
        print(f"[pipeline] loading YOLO from {YOLO_MODEL_PATH}")
        _yolo = YOLO(str(YOLO_MODEL_PATH))
    return _yolo


def _get_sam() -> SAM:
    global _sam
    if _sam is None:
        print(f"[pipeline] loading SAM3 from {SAM_MODEL_PATH}")
        _sam = SAM(str(SAM_MODEL_PATH))
        _sam.overrides["imgsz"] = 1036   # pre-set to valid stride-14 multiple, silences per-frame warning
    return _sam


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_class(raw: str) -> Optional[str]:
    return CLASS_MAP.get(raw.lower())


def _center(box: list) -> Tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _point_in_box(cx: float, cy: float, box: list) -> bool:
    return box[0] < cx < box[2] and box[1] < cy < box[3]


def _proximity(b1: list, b2: list) -> float:
    cx1, cy1 = _center(b1)
    cx2, cy2 = _center(b2)
    return float(np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2))


def _save_person_crops(
    frame_bgr: np.ndarray,
    detections: List[Dict],
    frame_idx: int,
    crops_dir: Path,
    pad: float = 0.25,
) -> List[Dict]:
    h, w = frame_bgr.shape[:2]
    crops = []
    for i, det in enumerate(d for d in detections if d["class_name"] == "worker"):
        x1, y1, x2, y2 = det["bbox"]
        bw, bh = x2 - x1, y2 - y1
        px1 = max(0, int(x1 - pad * bw))
        py1 = max(0, int(y1 - pad * bh))
        px2 = min(w, int(x2 + pad * bw))
        py2 = min(h, int(y2 + pad * bh))
        crop_bgr = frame_bgr[py1:py2, px1:px2]
        crop_name = f"frame_{frame_idx:06d}_worker_{i}.jpg"
        cv2.imwrite(str(crops_dir / crop_name), crop_bgr)
        crops.append({
            "path": crop_name,
            "worker_index": i,
            "track_id": det.get("track_id"),
            "bbox_original": det["bbox"],
            "bbox_padded": [px1, py1, px2, py2],
            "confidence": det["confidence"],
        })
    return crops


# ---------------------------------------------------------------------------
# Per-frame processing
# ---------------------------------------------------------------------------

def _process_frame(
    frame_bgr: np.ndarray,
    frame_idx: int,
    fps: float,
    yolo: YOLO,
    sam: Optional[SAM],
    worker_safety_log: Dict[int, set],
    conf_threshold: float,
    proximity_threshold: float,
) -> Tuple[List[Dict], List[Dict], np.ndarray]:
    """
    Returns (detections, hazards, annotated_frame_bgr).
    Updates worker_safety_log in-place.
    """
    # --- YOLO track ---
    yolo_results = yolo.track(
        frame_bgr,
        conf=conf_threshold,
        imgsz=640,
        persist=True,
        tracker="botsort.yaml",
        verbose=False,
        half=torch.cuda.is_available(),
    )[0]

    boxes_xyxy = yolo_results.boxes.xyxy.cpu().numpy().tolist()
    confs      = yolo_results.boxes.conf.cpu().numpy().tolist()
    cls_ids    = yolo_results.boxes.cls.cpu().numpy().tolist()
    track_ids  = (
        yolo_results.boxes.id.int().cpu().numpy().tolist()
        if yolo_results.boxes.id is not None
        else [-1] * len(boxes_xyxy)
    )

    # Normalise detections
    detections: List[Dict] = []
    for box, conf, cls_id, tid in zip(boxes_xyxy, confs, cls_ids, track_ids):
        raw   = yolo.names[int(cls_id)]
        mapped = _map_class(raw)
        if mapped is None:
            continue
        detections.append({
            "class_name":    mapped,
            "original_class": raw,
            "bbox":          box,
            "confidence":    round(float(conf), 4),
            "track_id":      int(tid),
        })

    # --- SAM3 masking (only if there are detections and local SAM is on) ---
    # With SAM_BACKEND=meta, sam is None: YOLO boxes are drawn per-frame and
    # SAM 3.1 refines flagged frames over the API afterwards (see
    # _refine_with_meta_sam) — no local weights needed.
    if boxes_xyxy and sam is not None:
        try:
            sam_results     = sam(frame_bgr, bboxes=boxes_xyxy, verbose=False)[0]
            annotated_frame = sam_results.plot()
        except Exception as sam_err:
            print(f"[pipeline] SAM failed on frame {frame_idx}: {sam_err} — using YOLO plot fallback")
            annotated_frame = yolo_results.plot()
    elif boxes_xyxy:
        annotated_frame = yolo_results.plot()
    else:
        annotated_frame = frame_bgr.copy()

    # --- Separate workers and PPE ---
    workers = [d for d in detections if d["class_name"] == "worker"]
    ppes    = [d for d in detections if d["class_name"] in POSITIVE_PPE]

    # Register new track IDs
    for w in workers:
        tid = w["track_id"]
        if tid != -1 and tid not in worker_safety_log:
            worker_safety_log[tid] = {"ppe_last_seen": {}, "observations": 0, "last_seen_frame": frame_idx}

    # Count this sighting per tracked worker
    for w in workers:
        if w["track_id"] != -1:
            entry = worker_safety_log[w["track_id"]]
            entry["observations"] += 1
            entry["last_seen_frame"] = frame_idx

    # Associate PPE with workers (center-point containment)
    for ppe in ppes:
        cx, cy = _center(ppe["bbox"])
        for w in workers:
            if _point_in_box(cx, cy, w["bbox"]) and w["track_id"] != -1:
                worker_safety_log[w["track_id"]]["ppe_last_seen"][ppe["class_name"]] = frame_idx

    # --- Derive hazards ---
    hazards: List[Dict] = []

    # 1. Direct YOLO "no_*" violations
    for det in detections:
        if det["class_name"] in ("no_hardhat", "no_safety_vest", "no_gloves"):
            hazards.append({
                "hazard_type":    det["class_name"],
                "description":    f"Worker without {det['class_name'].replace('no_', '').replace('_', ' ')}",
                "severity":       "HIGH",
                "violation_type": "PPE_MISSING",
                "objects":        [{"class": det["class_name"], "confidence": det["confidence"]}],
                "track_id":       det.get("track_id"),
            })

    # 2. Per-tracked-worker: missing required PPE (fresh evidence only,
    #    and only once the track has a few frames of history — flagging on
    #    first sighting false-positives before gear is associated)
    for w in workers:
        tid = w["track_id"]
        if tid == -1:
            continue
        entry = worker_safety_log[tid]
        if entry["observations"] < MIN_TRACK_OBSERVATIONS:
            continue
        worn    = _worn_items(entry, frame_idx)
        missing = REQUIRED_PPE - worn
        for item in missing:
            hazards.append({
                "hazard_type":    f"missing_{item}",
                "description":    f"Worker #{tid} — {item} not observed",
                "severity":       "HIGH",
                "violation_type": "PPE_MISSING",
                "objects":        [{"class": "worker", "confidence": w["confidence"]}],
                "track_id":       tid,
                "ppe_worn":       list(worn),
                "ppe_missing":    list(missing),
            })

    # 3. Proximity: worker near heavy equipment
    by_class: Dict[str, list] = {}
    for d in detections:
        by_class.setdefault(d["class_name"], []).append(d)

    for equip_class in EQUIPMENT:
        for equip in by_class.get(equip_class, []):
            for w in workers:
                dist = _proximity(equip["bbox"], w["bbox"])
                # Normalise by frame diagonal
                h_frame, w_frame = frame_bgr.shape[:2]
                diag = np.sqrt(h_frame**2 + w_frame**2)
                if dist / diag < proximity_threshold:
                    hazards.append({
                        "hazard_type":    "heavy_equipment_proximity",
                        "description":    f"Worker near {equip_class}",
                        "severity":       "HIGH",
                        "violation_type": "PROXIMITY_HAZARD",
                        "objects": [
                            {"class": equip_class, "confidence": equip["confidence"]},
                            {"class": "worker",    "confidence": w["confidence"]},
                        ],
                        "proximity": round(dist, 2),
                        "track_id": w.get("track_id"),
                        "equipment_class": equip_class,
                    })

    # Each (equipment, worker) pair is visited exactly once above, so no
    # dedup is needed here — a former pass keyed on track_id, which
    # proximity hazards never set, and collapsed every distinct pair in
    # a frame into the first one.
    return detections, hazards, annotated_frame


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_wall_cam_pipeline(
    video_path: Path,
    job_dir: Path,
    site_id: str,
    date: str,
    sample_every_n: int = 3,
    conf_threshold: float = 0.15,
    proximity_threshold: float = 0.25,
    camera_source: str = "WALL_CAM",
) -> tuple:
    """
    Runs YOLO + SAM3 on wall-cam video.

    Writes to job_dir:
      detections.jsonl     — one JSON record per sampled frame
      hazard_events.json   — frames with violations + worker compliance state
      summary.json         — aggregate counts
      vlm_assessments.json — written by vlm_step after this returns

    Returns (summary, hazard_events, vlm_results).
    """
    frames_dir = job_dir / "frames"
    crops_dir  = job_dir / "crops"
    frames_dir.mkdir(exist_ok=True)
    crops_dir.mkdir(exist_ok=True)

    yolo = _get_yolo()
    if _settings.sam_backend == "meta":
        print("[pipeline] SAM backend=meta — skipping local SAM weights (API refinement later)")
        sam = None
    else:
        sam = _get_sam()

    print(f"[pipeline] opening video: {video_path}")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps          = cap.get(cv2.CAP_PROP_FPS) or 24.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[pipeline] fps={fps:.1f}, total_frames={total_frames}")

    worker_safety_log: Dict[int, set] = {}   # track_id → set of PPE seen
    hazard_events: List[dict] = []
    hazard_counts: Dict[str, int] = {}
    all_classes:   set = set()
    frames_processed = 0
    frame_idx = 0

    with open(job_dir / "detections.jsonl", "w") as log:
        while True:
            ret, frame_bgr = cap.read()
            if not ret:
                break

            if frame_idx % sample_every_n != 0:
                frame_idx += 1
                continue

            timestamp = round(frame_idx / fps, 3)

            try:
                detections, hazards, annotated = _process_frame(
                    frame_bgr, frame_idx, fps,
                    yolo, sam,
                    worker_safety_log,
                    conf_threshold, proximity_threshold,
                )
            except Exception as frame_err:
                print(f"[pipeline] frame {frame_idx} error (skipping): {frame_err}")
                frame_idx += 1
                continue

            for d in detections:
                all_classes.add(d["class_name"])

            # Snapshot worker compliance (fresh evidence at last sighting)
            worker_state = {
                str(tid): {
                    "has":     list(_worn_items(entry, entry["last_seen_frame"])),
                    "missing": list(REQUIRED_PPE - _worn_items(entry, entry["last_seen_frame"])),
                }
                for tid, entry in worker_safety_log.items()
            }

            frame_record: Dict = {
                "frame_idx":        frame_idx,
                "timestamp_seconds": timestamp,
                "detections":       detections,
                "worker_ppe_state": worker_state,
                "hazards":          hazards,
            }

            if hazards:
                frame_filename = f"frame_{frame_idx:06d}.jpg"
                ok = cv2.imwrite(str(frames_dir / frame_filename), annotated)
                if not ok:
                    print(f"[pipeline] WARNING: failed to write frame {frame_filename}")
                crops = _save_person_crops(frame_bgr, detections, frame_idx, crops_dir)
                frame_record["frame_path"]   = frame_filename
                frame_record["person_crops"] = crops
                hazard_events.append(frame_record)
                for h in hazards:
                    hazard_counts[h["hazard_type"]] = hazard_counts.get(h["hazard_type"], 0) + 1

            log.write(json.dumps(frame_record) + "\n")
            frames_processed += 1
            frame_idx += 1

            if frames_processed % 50 == 0:
                print(f"[pipeline] {frames_processed} frames processed, {len(hazard_events)} hazard frames")

    cap.release()
    print(f"[pipeline] done — {frames_processed} frames, {len(hazard_events)} hazard frames")

    # Final compliance summary per tracked worker (fresh evidence at
    # each worker's last sighting, not at video end)
    compliance_summary = {
        str(tid): {
            "ppe_confirmed": list(_worn_items(entry, entry["last_seen_frame"])),
            "ppe_missing":   list(REQUIRED_PPE - _worn_items(entry, entry["last_seen_frame"])),
            "compliant":     REQUIRED_PPE.issubset(_worn_items(entry, entry["last_seen_frame"])),
        }
        for tid, entry in worker_safety_log.items()
    }

    summary = {
        "site_id":             site_id,
        "date":                date,
        "video_fps":           fps,
        "total_frames":        total_frames,
        "frames_processed":    frames_processed,
        "frames_with_hazards": len(hazard_events),
        "hazard_counts":       hazard_counts,
        "detected_classes":    sorted(all_classes),
        "worker_compliance":   compliance_summary,
        "workers_tracked":     len(worker_safety_log),
    }

    (job_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print("[pipeline] starting VLM assessment pass")
    vlm_results = assess_all_events(
        hazard_events,
        job_dir,
        video_path=video_path,
        summary=summary,
        camera_source=camera_source,
    )
    summary["vlm_events_assessed"] = len(vlm_results)

    if _settings.sam_backend == "meta":
        summary["meta_sam"] = _refine_with_meta_sam(job_dir, hazard_events)

    return summary, hazard_events, vlm_results


def _refine_with_meta_sam(job_dir: Path, hazard_events: List[dict]) -> dict:
    """Refine flagged frames with SAM 3.1 over the Meta API (capped).

    Full boxes + masks land in ``meta_sam.json``; the summary keeps only
    counts so ``summary.json`` stays small.
    """
    from app.integrations.meta_api import segment_image

    model = _settings.meta_model_api_sam_model
    cap = max(0, _settings.meta_sam_max_frames)
    frames_dir = job_dir / "frames"
    print(f"[pipeline] SAM backend=meta — refining up to {cap} frames via {model} ...")
    full: List[dict] = []
    compact: List[dict] = []
    for record in hazard_events[:cap]:
        frame_file = record.get("frame_path")
        full_path = frames_dir / frame_file if frame_file else None
        if not full_path or not full_path.exists():
            continue
        try:
            seg = segment_image(full_path.read_bytes(), filename=full_path.name)
        except Exception as exc:  # noqa: BLE001 — per-frame errors must not kill the job
            print(f"[pipeline] meta SAM error on {frame_file}: {exc}")
            entry = {"frame": frame_file, "error": str(exc)}
            full.append(entry)
            compact.append(entry)
            continue
        full.append({"frame": frame_file, **seg})
        compact.append(
            {
                "frame": frame_file,
                "timestamp_seconds": record.get("timestamp_seconds"),
                "box_count": len(seg["boxes"]),
                "mask_count": len(seg["masks"]),
                "boxes": seg["boxes"],
            }
        )
    (job_dir / "meta_sam.json").write_text(json.dumps(full, indent=2))
    print(f"[pipeline] meta SAM done — {len(compact)} frame(s) refined")
    return {"model": model, "frames_refined": len(compact), "frames": compact}
