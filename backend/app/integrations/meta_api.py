"""Meta Model API client (``https://api.meta.ai/v1``).

Endpoints used:
  * ``POST /v1/files``     — upload an image/video, get back a file id
  * ``POST /v1/responses`` — run a model over text + uploaded file refs
  * ``GET  /v1/models``    — live model catalog (powers ``GET /meta/models``)

Auth is a Bearer token from ``MODEL_API_KEY`` (see ``backend/.env.example``).
Only anonymized worker codes (UUIDs / track IDs) are ever sent — never
display names or embeddings.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings


class MetaNotConfiguredError(RuntimeError):
    """Raised when Meta integration is used without an API key."""


def require_key() -> str:
    if not settings.meta_configured:
        raise MetaNotConfiguredError(
            "MODEL_API_KEY is not set. Copy backend/.env.example to "
            "backend/.env and add your Meta Model API key."
        )
    return settings.meta_model_api_key.strip()


def _base() -> str:
    return settings.meta_model_api_base_url.rstrip("/")


def _auth_headers(api_key: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key or require_key()}"}


def meta_status() -> dict[str, Any]:
    """Non-sensitive integration status (never includes the key itself)."""
    return {
        "configured": settings.meta_configured,
        "base_url": settings.meta_model_api_base_url,
        "sam_model": settings.meta_model_api_sam_model,
        "vision_model": settings.meta_model_api_vision_model,
        "text_model": settings.meta_model_api_text_model,
        "vlm_backend": settings.vlm_backend,
        "sam_backend": settings.sam_backend,
    }


def list_models() -> list[str]:
    """Live model catalog. Returns model IDs (needs a key)."""
    url = _base() + "/models"
    with httpx.Client(timeout=settings.meta_model_api_timeout_s) as client:
        resp = client.get(url, headers=_auth_headers())
        resp.raise_for_status()
        data = resp.json()
    items = data.get("data", data if isinstance(data, list) else [])
    return [m["id"] for m in items if isinstance(m, dict) and m.get("id")]


def _sniff_mime(data: bytes) -> tuple[str, str]:
    """(extension, MIME) from magic bytes — the API rejects mismatches."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[:4] == b"GIF8":
        return "gif", "image/gif"
    if len(data) > 12 and data[4:8] == b"ftyp":
        return "mp4", "video/mp4"
    return "bin", "application/octet-stream"


def _aligned_filename(filename: str, ext: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else (filename or "upload")
    return f"{stem}.{ext}"


def _raise_for_status(resp: "httpx.Response", url: str) -> None:
    """Like raise_for_status, but keeps the API's error body in the message."""
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300].replace("\n", " ")
        raise RuntimeError(f"{url} -> {exc.response.status_code}: {body}") from exc


def upload_file(data: bytes, filename: str, purpose: str = "user_data") -> str:
    """POST /files. Returns the file id for use in ``responses()``."""
    ext, mime = _sniff_mime(data)
    url = _base() + "/files"
    with httpx.Client(timeout=settings.meta_model_api_timeout_s) as client:
        resp = client.post(
            url,
            headers=_auth_headers(),
            files={"file": (_aligned_filename(filename, ext), data, mime)},
            data={"purpose": purpose},
        )
        _raise_for_status(resp, url)
        payload = resp.json()
    file_id = payload.get("id") or payload.get("file_id")
    if not file_id:
        raise RuntimeError(f"Unexpected /files response: {payload!r:.200}")
    return file_id


def responses(
    model: str,
    input_items: list[dict[str, Any]],
    *,
    max_output_tokens: int = 1024,
    temperature: float = 0.2,
    reasoning_effort: str | None = "minimal",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /responses (Responses-style call). Returns the raw payload.

    ``reasoning_effort="minimal"`` is the default because muse-spark reasons
    at high effort otherwise and can burn the whole token budget before
    emitting text (status ``incomplete``). ``"none"`` is rejected by the API.
    """
    url = _base() + "/responses"
    payload: dict[str, Any] = {
        "model": model,
        "input": input_items,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if extra:
        payload.update(extra)
    with httpx.Client(timeout=settings.meta_model_api_timeout_s) as client:
        resp = client.post(
            url,
            headers={**_auth_headers(), "Content-Type": "application/json"},
            json=payload,
        )
        _raise_for_status(resp, url)
        data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected /responses payload: {data!r:.200}")
    return data


def _text_item(text: str) -> dict[str, Any]:
    return {"type": "input_text", "text": text}


def _image_file_item(file_id: str) -> dict[str, Any]:
    return {"type": "input_image", "file_id": file_id}


def responses_text(
    model: str,
    user_text: str,
    *,
    system: str | None = None,
    image_file_ids: list[str] | None = None,
    max_output_tokens: int = 1024,
    temperature: float = 0.2,
    reasoning_effort: str | None = "minimal",
) -> str:
    """Text out of ``/responses`` — vision when ``image_file_ids`` given."""
    user_content: list[dict[str, Any]] = [
        _image_file_item(fid) for fid in (image_file_ids or [])
    ]
    user_content.append(_text_item(user_text))
    items: list[dict[str, Any]] = []
    if system:
        items.append(
            {"role": "system", "content": [_text_item(system)]}
        )
    items.append({"role": "user", "content": user_content})
    data = responses(
        model,
        items,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
    return extract_text(data)


def extract_text(data: dict[str, Any]) -> str:
    """Best-effort text extraction across Responses-style payload shapes."""
    if isinstance(data.get("output_text"), str) and data["output_text"]:
        return data["output_text"]
    chunks: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                chunks.append(item["text"])
                continue
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(
                        part.get("text"), str
                    ):
                        chunks.append(part["text"])
    if chunks:
        return "\n".join(chunks)
    # Chat-style fallback (OpenAI-compatible mirrors).
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        pass
    if isinstance(output, list) and any(
        isinstance(i, dict) and i.get("type") == "reasoning" for i in output
    ):
        raise RuntimeError(
            "Model spent its output budget on reasoning and emitted no text "
            "(status: %s). Raise max_output_tokens or lower reasoning effort."
            % data.get("status")
        )
    raise RuntimeError(f"No text in /responses payload: {str(data)[:200]}")


# ---------------------------------------------------------------------------
# SAM 3.1 segmentation (boxes + masks)
# ---------------------------------------------------------------------------

DEFAULT_SEGMENT_PROMPT = (
    "Segment every construction worker and every PPE item "
    "(hard hat, safety vest, gloves, boots) in this image. "
    "Return bounding boxes and segmentation masks."
)


def segment_image(
    image_bytes: bytes,
    prompt: str = DEFAULT_SEGMENT_PROMPT,
    *,
    filename: str = "frame.jpg",
    model: str | None = None,
) -> dict[str, Any]:
    """Run SAM 3.1 over one image. Returns normalized boxes/masks + raw."""
    model = model or settings.meta_model_api_sam_model
    file_id = upload_file(image_bytes, filename, purpose="user_data")
    data = responses(
        model,
        [{"role": "user", "content": [_image_file_item(file_id), _text_item(prompt)]}],
        max_output_tokens=2048,
    )
    normalized = normalize_segmentation(data)
    normalized["model"] = model
    normalized["file_id"] = file_id
    return normalized


def segment_video(
    video_bytes: bytes,
    prompt: str = DEFAULT_SEGMENT_PROMPT,
    *,
    filename: str = "clip.mp4",
    model: str | None = None,
) -> dict[str, Any]:
    """Run SAM 3.1 over one video clip. Same normalized shape as images."""
    model = model or settings.meta_model_api_sam_model
    file_id = upload_file(video_bytes, filename, purpose="user_data")
    data = responses(
        model,
        [{"role": "user", "content": [_image_file_item(file_id), _text_item(prompt)]}],
        max_output_tokens=2048,
    )
    normalized = normalize_segmentation(data)
    normalized["model"] = model
    normalized["file_id"] = file_id
    return normalized


def normalize_segmentation(data: dict[str, Any]) -> dict[str, Any]:
    """Best-effort boxes/masks extraction; always keeps ``raw`` for display."""
    boxes: list[Any] = []
    masks: list[Any] = []

    def _collect(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("boxes", "bboxes", "detections", "regions"):
                val = node.get(key)
                if isinstance(val, list) and val:
                    boxes.extend(val)
            for key in ("masks", "segmentations", "mask_rles"):
                val = node.get(key)
                if isinstance(val, list) and val:
                    masks.extend(val)
            for val in node.values():
                _collect(val)
        elif isinstance(node, list):
            for val in node:
                _collect(val)

    _collect(data.get("output", data))
    return {"boxes": boxes, "masks": masks, "raw": data}
