"""Meta Model API routes (``https://api.meta.ai`` — no key ever returned)."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.integrations.meta_api import (
    DEFAULT_SEGMENT_PROMPT,
    MetaNotConfiguredError,
    list_models,
    meta_status,
    segment_image,
    segment_video,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/status")
def get_meta_status():
    """Whether the Meta Model API is configured, and with which models."""
    return meta_status()


@router.get("/models")
def get_meta_models():
    """Live model catalog from the Meta Model API (requires a key)."""
    try:
        return {"models": list_models()}
    except MetaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface API errors as 502
        raise HTTPException(
            status_code=502, detail=f"Meta Model API error: {exc}"
        ) from exc


@router.post("/segment")
async def post_meta_segment(
    file: UploadFile = File(...),
    prompt: str = Form(DEFAULT_SEGMENT_PROMPT),
):
    """Segment one image (or short video) with SAM 3.1 → boxes + masks."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    name = file.filename or "upload"
    is_video = (file.content_type or "").startswith("video/") or name.lower().endswith(
        (".mp4", ".mov", ".avi", ".mkv", ".webm")
    )
    try:
        if is_video:
            return segment_video(data, prompt, filename=name)
        return segment_image(data, prompt, filename=name)
    except MetaNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface API errors as 502
        raise HTTPException(
            status_code=502, detail=f"Meta Model API error: {exc}"
        ) from exc
