"""Smoke tests for every router — runs without torch, weights, or API keys."""


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cors_allows_dashboard_posts_from_any_local_origin(client):
    res = client.options(
        "/sites",
        headers={
            "Origin": "http://192.168.1.5:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "*"


def test_startup_skips_local_sam_when_meta(monkeypatch):
    """SAM_BACKEND=meta must never touch local SAM weights at boot."""
    import sys
    import types

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    calls: list[str] = []
    monkeypatch.setattr(settings, "prewarm_models", True)
    monkeypatch.setattr(settings, "vlm_backend", "meta")
    monkeypatch.setattr(settings, "sam_backend", "meta")
    fake = types.ModuleType("app.pipeline.wall_cam")
    fake._get_yolo = lambda: calls.append("yolo")  # noqa: E731
    fake._get_sam = lambda: calls.append("sam")  # noqa: E731
    monkeypatch.setitem(sys.modules, "app.pipeline.wall_cam", fake)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}
    assert calls == ["yolo"]


def test_startup_survives_missing_weights(monkeypatch):
    """Warm-up must never kill the API when weight files are absent."""
    import sys
    import types

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "prewarm_models", True)
    monkeypatch.setattr(settings, "vlm_backend", "meta")
    fake = types.ModuleType("app.pipeline.wall_cam")

    def _boom():
        raise FileNotFoundError("backend/models/last.pt")

    fake._get_yolo = _boom
    fake._get_sam = lambda: None  # noqa: E731
    monkeypatch.setitem(sys.modules, "app.pipeline.wall_cam", fake)
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "ok"}


def test_sites_crud(client, site):
    assert site["name"] == "Test Site"
    ids = [s["id"] for s in client.get("/sites").json()]
    assert site["id"] in ids


def test_devices_list(client, site, device):
    res = client.get("/devices", params={"site_id": site["id"]})
    assert res.status_code == 200
    assert res.json()[0]["label"] == "Cam-03"


def test_devices_reject_unknown_site(client):
    res = client.post("/devices", json={"label": "X", "site_id": "nope"})
    assert res.status_code == 404


def test_workers_list_get(client, site, worker):
    listed = client.get("/workers", params={"site_id": site["id"]}).json()
    assert listed[0]["worker_id"] == worker["worker_id"]
    one = client.get(f"/workers/{worker['worker_id']}").json()
    assert one["display_name"] == "W-001"


def test_checkin_binds_device(client, shift, device):
    assert shift["pov_device_id"] == device["id"]
    assert shift["status"] == "IN_PROGRESS"
    # re-checkin same day reuses the shift
    res = client.post(
        "/workers/checkin",
        json={
            "worker_id": shift["worker_id"],
            "pov_device_id": device["id"],
            "date": shift["date"],
        },
    )
    assert res.json()["shift_id"] == shift["shift_id"]


def test_shift_get_and_close(client, shift):
    got = client.get(f"/shifts/{shift['shift_id']}").json()
    assert got["events"] == []
    closed = client.patch(
        f"/shifts/{shift['shift_id']}/close", json={"msd_risk_score": 2.5}
    ).json()
    assert closed["status"] == "COMPLETED"
    assert closed["msd_risk_score"] == 2.5


def test_shift_404(client):
    assert client.get("/shifts/does-not-exist").status_code == 404


def test_events_ingest_and_list(client, shift):
    payload = {
        "shift_id": shift["shift_id"],
        "worker_id": shift["worker_id"],
        "camera_source": "POV",
        "event_category": "VIOLATION",
        "violation_type": "PPE_MISSING",
        "severity": "HIGH",
        "video_timestamp": 12.5,
        "metadata": {"track_id": 3},
    }
    res = client.post("/events/ingest", json=payload)
    assert res.status_code == 201
    assert res.json()["metadata"] == {"track_id": 3}

    listed = client.get("/events", params={"shift_id": shift["shift_id"]}).json()
    assert len(listed) == 1

    # counters incremented on shift + worker
    got = client.get(f"/shifts/{shift['shift_id']}").json()
    assert got["violation_count"] == 1
    worker = client.get(f"/workers/{shift['worker_id']}").json()
    assert worker["total_violations"] == 1


def test_events_ingest_rejects_unknown_shift(client, shift):
    payload = {
        "shift_id": "nope",
        "worker_id": shift["worker_id"],
        "camera_source": "POV",
        "event_category": "VIOLATION",
    }
    assert client.post("/events/ingest", json=payload).status_code == 404


def test_jobs_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404
    assert client.get("/jobs").json() == []


def test_process_accepts_missing_worker_id(client, site, monkeypatch):
    from app.api.routes import process as process_routes

    monkeypatch.setattr(process_routes, "run_detection_job", lambda *a, **k: None)
    res = client.post(
        "/process/wall-cam",
        files={"video": ("t.mp4", b"not-a-video")},
        data={"site_id": site["id"], "date": "2026-10-30"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "PROCESSING"


def test_resolve_worker_code():
    from app.services.jobs import resolve_worker_code

    assert resolve_worker_code("W-001") == "W-001"
    assert resolve_worker_code("  padded  ") == "padded"
    assert resolve_worker_code(None).startswith("W-")
    assert resolve_worker_code("   ").startswith("W-")


def test_meta_status_no_key_leak(client):
    res = client.get("/meta/status")
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is False
    assert body["base_url"] == "https://api.meta.ai/v1"
    assert body["sam_model"] == "sam-3.1"
    assert "key" not in str(body).lower().replace("api_key", "")


def test_meta_models_needs_key(client):
    assert client.get("/meta/models").status_code == 503


def test_meta_segment_needs_key(client):
    res = client.post("/meta/segment", files={"file": ("f.jpg", b"xx")})
    assert res.status_code == 503


def test_meta_segment_with_mock(client, monkeypatch):
    from app.api.routes import meta as meta_routes

    monkeypatch.setattr(
        meta_routes,
        "segment_image",
        lambda *a, **k: {"model": "sam-3.1", "boxes": [[1, 2, 3, 4]], "masks": []},
    )
    res = client.post("/meta/segment", files={"file": ("f.jpg", b"xx")})
    assert res.status_code == 200
    assert res.json()["boxes"] == [[1, 2, 3, 4]]


def test_reports_needs_key(client, shift):
    res = client.get(f"/reports/shifts/{shift['shift_id']}/summary")
    assert res.status_code == 503


def test_reports_summary_with_mocked_llama(client, shift, monkeypatch):
    from app.core.config import settings
    from app.integrations import meta_llama

    monkeypatch.setattr(settings, "meta_llama_api_key", "test-key")
    monkeypatch.setattr(
        meta_llama, "responses_text", lambda *a, **k: "Shift was safe. No issues."
    )
    res = client.get(f"/reports/shifts/{shift['shift_id']}/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["shift_id"] == shift["shift_id"]
    assert "safe" in body["summary"]
