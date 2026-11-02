"""Stage-3 VLM + shift summaries over the Meta Model API.

Thin layer over :mod:`app.integrations.meta_api`:

  1. Stage-3 VLM assessment via a vision-capable Meta model
     (``VLM_BACKEND=meta``) — annotated frames are uploaded with
     ``POST /files`` and assessed with ``POST /responses``; out comes the
     same ``VLMAssessment`` JSON the local pipeline produces.
  2. Natural-language shift summaries for ``GET /reports/shifts/{id}/summary``.

Key: ``MODEL_API_KEY`` — paste it into ``backend/.env``; see
``backend/.env.example``. Only anonymized worker codes (UUIDs / track IDs)
are ever sent to the API — never display names or embeddings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.integrations.meta_api import (
    MetaNotConfiguredError,  # noqa: F401 — re-exported for stable imports
    require_key,  # noqa: F401
    responses_text,
)

__all__ = [
    "MetaNotConfiguredError",
    "require_key",
    "chat_completion",
    "meta_status",
    "list_models",
    "assess_chunk_with_meta",
    "assess_all_chunks_meta",
    "summarize_shift",
]


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Backwards-compatible text call, served by ``POST /responses``.

    ``messages`` uses the familiar ``{"role": ..., "content": ...}`` shape;
    plain-string content and ``image_url`` data-URL parts are accepted (the
    latter are uploaded via ``POST /files`` first).
    """
    from app.integrations.meta_api import upload_file

    del response_format  # Responses API: JSON is requested via the prompt.
    system: str | None = None
    user_texts: list[str] = []
    file_ids: list[str] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        parts = content if isinstance(content, list) else [content]
        texts: list[str] = []
        for part in parts:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
                url = (part.get("image_url") or {}).get("url", "")
                if url.startswith("data:") and ";base64," in url:
                    import base64

                    b64 = url.split(";base64,", 1)[1]
                    file_ids.append(
                        upload_file(base64.b64decode(b64), "frame.jpg")
                    )
        if role == "system":
            system = "\n".join(texts)
        else:
            user_texts.extend(texts)
    return responses_text(
        model,
        "\n".join(user_texts),
        system=system,
        image_file_ids=file_ids,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )


def meta_status() -> dict[str, Any]:
    from app.integrations.meta_api import meta_status as _status

    return _status()


def list_models() -> list[str]:
    from app.integrations.meta_api import list_models as _list

    return _list()


# ---------------------------------------------------------------------------
# Stage-3 VLM assessment over the API (single reconciler-style pass)
# ---------------------------------------------------------------------------

META_VLM_USER_TEMPLATE = """\
VIDEO OVERVIEW:
  Duration   : ~{duration:.1f}s  |  Camera: {camera_type}

{camera_guidance}

Assess the attached annotated frames together with the YOLO + SAM
detection data below. Apply the mandatory safety rules and reasoning
stages from your system prompt.

YOLO + SAM DETECTION DATA:
{yolo_sam_data}

{annotated_frame_note}

CONFIDENCE CALIBRATION:
  conf >= 0.70 = strong  |  0.40-0.69 = moderate, verify visually
  0.15-0.39 = weak, must confirm in image  |  < 0.15 = noise, discard

ONE entry per unique (worker, violation_type). No duplicates.

Return a JSON object matching this exact schema:
{schema}

Output ONLY valid JSON. No explanation outside the JSON."""


def assess_chunk_with_meta(
    hazard_frames: list[dict],
    annotated_paths: list[Path],
    summary: dict,
    duration: float,
    cam_key: str,
) -> dict:
    """Run one VLM assessment chunk via the Meta API. Returns VLMAssessment."""
    from app.integrations.meta_api import upload_file
    from app.pipeline.vlm_step import (
        PASS2_ANNOTATED_FRAME_NOTE,
        SYSTEM_PROMPT,
        VLMAssessment,
        _CAMERA_GUIDANCE,
        _extract_json,
        _format_yolo_sam_data,
    )

    annotated_note = (
        PASS2_ANNOTATED_FRAME_NOTE.format(
            n=len(annotated_paths),
            n_minus_1=max(len(annotated_paths) - 1, 0),
        )
        if annotated_paths
        else ""
    )
    user_text = META_VLM_USER_TEMPLATE.format(
        duration=duration,
        camera_type=cam_key,
        camera_guidance=_CAMERA_GUIDANCE[cam_key],
        yolo_sam_data=_format_yolo_sam_data(hazard_frames, summary),
        annotated_frame_note=annotated_note,
        schema=json.dumps(VLMAssessment.model_json_schema(), indent=2),
    )
    file_ids = [
        upload_file(p.read_bytes(), p.name) for p in annotated_paths
    ]
    print(
        f"[vlm:meta] assessing chunk ({len(file_ids)} images, "
        f"{settings.meta_model_api_vision_model}) ..."
    )
    raw_output = responses_text(
        settings.meta_model_api_vision_model,
        user_text,
        system=SYSTEM_PROMPT,
        image_file_ids=file_ids,
        # Vision chunks are heavy: floor the budget so reasoning + the JSON
        # assessment both fit even with 15 annotated frames attached.
        max_output_tokens=max(settings.vlm_max_new_tokens, 2048),
    )
    assessment = VLMAssessment.model_validate(_extract_json(raw_output))
    print(
        f"[vlm:meta] final: {len(assessment.hazards)} hazards, "
        f"confidence={assessment.confidence}"
    )
    return assessment.model_dump()


def assess_all_chunks_meta(
    chunks: list[list[dict]],
    hazard_frames: list[dict],
    job_dir: Path,
    summary: dict,
    camera_source: str,
) -> list[dict]:
    """Assess every time-chunk via the Meta API. Same shape as local VLM."""
    from app.pipeline.vlm_step import _collect_annotated_paths, _resolve_cam_key

    out_file = job_dir / "vlm_assessments.json"
    cam_key = _resolve_cam_key(camera_source)
    results: list[dict] = []
    for idx, chunk in enumerate(chunks):
        print(f"[vlm:meta] chunk {idx + 1}/{len(chunks)} — {len(chunk)} hazard frames")
        annotated_paths = _collect_annotated_paths(chunk, job_dir)
        duration = chunk[-1]["timestamp_seconds"] if chunk else 0.0
        try:
            assessment_dict = assess_chunk_with_meta(
                chunk, annotated_paths, summary, duration, cam_key
            )
        except Exception as exc:  # noqa: BLE001 — per-chunk errors must not kill the job
            print(f"[vlm:meta] error in chunk {idx}: {exc}")
            results.append(
                {"event": None, "vlm": None, "error": str(exc), "chunk_index": idx}
            )
            continue
        for hazard in assessment_dict["hazards"]:
            idx_frame = hazard.get("best_frame_index")
            if idx_frame is not None and 0 <= idx_frame < len(annotated_paths):
                hazard["best_frame_path"] = annotated_paths[idx_frame].name
            else:
                hazard["best_frame_path"] = None
        first, last = chunk[0], chunk[-1]
        results.append(
            {
                "event": {
                    "start_ts": first["timestamp_seconds"],
                    "end_ts": last["timestamp_seconds"],
                    "duration_seconds": round(
                        last["timestamp_seconds"] - first["timestamp_seconds"], 3
                    ),
                    "frame_count": len(chunk),
                    "peak_yolo_severity": "HIGH",
                    "yolo_hazard_types": list(
                        {
                            h["hazard_type"]
                            for f in chunk
                            for h in f.get("hazards", [])
                        }
                    ),
                    "representative_frame_path": first.get("frame_path"),
                    "representative_timestamp": first.get("timestamp_seconds", 0.0),
                    "chunk_index": idx,
                },
                "vlm": assessment_dict,
                "error": None,
            }
        )
    out_file.write_text(json.dumps(results, indent=2))
    total = sum(len(r.get("vlm", {}).get("hazards", [])) for r in results if r.get("vlm"))
    print(f"[vlm:meta] done — {total} hazards across {len(results)} chunk(s)")
    return results


# ---------------------------------------------------------------------------
# Shift summaries (text-only)
# ---------------------------------------------------------------------------

SHIFT_SUMMARY_SYSTEM = """\
You are an experienced construction safety manager writing an end-of-shift \
safety brief. Be concise, specific, and professional. Structure your brief as:

1. OVERVIEW — one or two sentences: shift outcome, total violations vs \
compliant events.
2. KEY VIOLATIONS — bullet list of the most severe violations with worker, \
type, severity, and timestamp. Skip this section if there are none.
3. PATTERNS — any repeat offenders or recurring violation types worth follow-up.
4. RECOMMENDATIONS — concrete next-shift actions (training, PPE checks, zone \
changes)."""


def summarize_shift(brief: str) -> str:
    """Turn a compact shift brief into a safety-manager-style summary."""
    return responses_text(
        settings.meta_model_api_text_model,
        f"Write the end-of-shift safety brief for this shift:\n\n{brief}",
        system=SHIFT_SUMMARY_SYSTEM,
        max_output_tokens=800,
    )
