"""Config defaults + light VLM helpers (no torch import)."""

import sys


def test_no_torch_import_for_api():
    # Importing the app + VLM schemas must not require torch/transformers.
    # Runs in a subprocess: other test modules legitimately import the
    # torch-backed pipelines, so a shared-process sys.modules check would
    # depend on collection order rather than on what the API imports.
    import subprocess

    code = (
        "import sys\n"
        "import app.main\n"
        "import app.pipeline.vlm_step\n"
        "assert 'torch' not in sys.modules, 'torch leaked into API import'\n"
        "assert 'transformers' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_settings_defaults():
    from app.core.config import settings

    assert settings.vlm_backend == "local"
    assert settings.sam_backend == "local"
    assert settings.meta_configured is False
    assert settings.meta_model_api_base_url == "https://api.meta.ai/v1"
    assert settings.meta_model_api_sam_model == "sam-3.1"
    # Legacy alias mirrors the canonical setting.
    assert settings.meta_llama_base_url == settings.meta_model_api_base_url


def test_meta_require_key_raises_without_key():
    import pytest

    from app.integrations.meta_llama import MetaNotConfiguredError, require_key

    with pytest.raises(MetaNotConfiguredError):
        require_key()


def test_resolve_cam_key():
    from app.pipeline.vlm_step import _resolve_cam_key

    assert _resolve_cam_key("POV") == "POV"
    assert _resolve_cam_key("wall_cam") == "WALL_CAM"
    assert _resolve_cam_key("POSTURE") == "POSTURE"


def test_extract_json():
    from app.pipeline.vlm_step import _extract_json

    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('prefix {"b": 2} suffix') == {"b": 2}


def test_chunk_hazard_frames():
    from app.pipeline.vlm_step import _chunk_hazard_frames

    frames = [{"timestamp_seconds": float(t)} for t in (0, 10, 70, 80)]
    chunks = _chunk_hazard_frames(frames, {"video_fps": 25.0})
    assert len(chunks) == 2
    assert [len(c) for c in chunks] == [2, 2]


def test_sniff_mime_matches_content():
    from app.integrations.meta_api import _sniff_mime

    assert _sniff_mime(b"\xff\xd8\xff\xe1rest") == ("jpg", "image/jpeg")
    assert _sniff_mime(b"\x89PNG\r\n\x1a\nrest") == ("png", "image/png")
    assert _sniff_mime(b"\x00\x00\x00\x18ftypmp42rest") == ("mp4", "video/mp4")
    assert _sniff_mime(b"????") == ("bin", "application/octet-stream")


def test_extract_text_reasoning_cutoff_error():
    import pytest

    from app.integrations.meta_api import extract_text

    with pytest.raises(RuntimeError, match="reasoning"):
        extract_text(
            {
                "status": "incomplete",
                "output": [{"type": "reasoning", "summary": []}],
            }
        )


def test_responses_sends_reasoning_minimal(monkeypatch):
    from app.integrations import meta_api

    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"output": []}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None, **kwargs):
            captured["url"] = url
            captured["json"] = json
            captured.update(kwargs)
            return FakeResp()

    monkeypatch.setattr(meta_api.httpx, "Client", FakeClient)
    monkeypatch.setattr(meta_api, "require_key", lambda: "k")
    meta_api.responses("m", [{"role": "user", "content": []}])
    assert captured["url"].endswith("/responses")
    assert captured["json"]["reasoning"] == {"effort": "minimal"}


def test_upload_uses_user_data_purpose(monkeypatch):
    from app.integrations import meta_api

    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "file-1"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, files=None, data=None):
            captured["url"] = url
            captured["files"] = files
            captured["data"] = data
            return FakeResp()

    monkeypatch.setattr(meta_api.httpx, "Client", FakeClient)
    monkeypatch.setattr(meta_api, "require_key", lambda: "k")
    assert meta_api.upload_file(b"\xff\xd8\xffrest", "frame.jpg") == "file-1"
    assert captured["url"].endswith("/files")
    assert captured["data"] == {"purpose": "user_data"}


def test_api_error_body_surfaces_in_message():
    import httpx
    import pytest

    from app.integrations.meta_api import _raise_for_status

    req = httpx.Request("POST", "https://api.meta.ai/v1/files")
    resp = httpx.Response(400, text='{"error":{"message":"bad purpose"}}', request=req)
    with pytest.raises(RuntimeError, match="bad purpose"):
        _raise_for_status(resp, "https://api.meta.ai/v1/files")


def test_vlm_assessment_schema_roundtrip():
    from app.pipeline.vlm_step import VLMAssessment

    a = VLMAssessment.model_validate(
        {
            "scene_summary": "s",
            "worker_count": 1,
            "equipment_present": [],
            "ppe_per_worker": [{"helmet": "PRESENT", "vest": "PRESENT", "gloves": "ABSENT"}],
            "reasoning": "r",
            "hazards": [
                {
                    "violation_type": "PPE_MISSING",
                    "severity": "HIGH",
                    "explanation": "e",
                    "recommendation": "rec",
                }
            ],
            "no_hazards": False,
            "confidence": "HIGH",
        }
    )
    assert a.hazards[0].violation_type == "PPE_MISSING"
