"""Pytest fixtures — isolated tmp SQLite DB, no model warm-up, no GPU."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="cage-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["JOBS_DIR"] = os.path.join(_tmp, "jobs")
os.environ["PREWARM_MODELS"] = "false"
# Hermetic: process env beats backend/.env in pydantic-settings, so force
# empty keys + local backends regardless of the developer's backend/.env.
os.environ["VLM_BACKEND"] = "local"
os.environ["SAM_BACKEND"] = "local"
os.environ["MODEL_API_KEY"] = ""
os.environ["META_MODEL_API_KEY"] = ""
os.environ["META_LLAMA_API_KEY"] = ""
os.environ["LLAMA_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def site(client):
    return client.post("/sites", json={"name": "Test Site", "location": "Lot 7"}).json()


@pytest.fixture()
def worker(client, site):
    res = client.post(
        "/workers/register",
        json={"site_id": site["id"], "display_name": "W-001"},
    )
    assert res.status_code == 201
    return res.json()


@pytest.fixture()
def device(client, site):
    res = client.post("/devices", json={"label": "Cam-03", "site_id": site["id"]})
    assert res.status_code == 201
    return res.json()


@pytest.fixture()
def shift(client, worker, device):
    res = client.post(
        "/workers/checkin",
        json={
            "worker_id": worker["worker_id"],
            "pov_device_id": device["id"],
            "date": "2026-10-30",
        },
    )
    assert res.status_code == 201
    return res.json()
