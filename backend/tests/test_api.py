from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_jobs import fetch_synthetic

from app.config import settings
from app.jobs import JobRunner
from app.main import app

# Synthetic cutouts sit at the MOVER test target.
MOVER_QUERY = {"ra": 150.0, "dec": 10.0, "ref_epoch": 2025.0, "pmra": 0.0, "pmdec": 12400.0, "fov": 3.0}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def synthetic_runner(client: TestClient) -> JobRunner:
    runner = JobRunner(fetch_synthetic, settings.processed_dir)
    app.state.runner = runner
    return runner


def poll(client: TestClient, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        body: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish")


def test_health_ok(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "spherex_dr1" in body["collections"]
    assert body["cache"]["raw_mb"] >= 0


def test_unimplemented_endpoints_say_so(client: TestClient) -> None:
    r = client.get("/api/spectrum", params={"ra": 269.45, "dec": 4.69})
    assert r.status_code == 501


@pytest.mark.parametrize(
    "params",
    [
        {"ra": 360, "dec": 0},
        {"ra": 10, "dec": 91},
        {"ra": 10, "dec": 0, "fov": 50},
        {"ra": 10, "dec": 0, "det": "7"},
        {"ra": 10, "dec": 0, "mode": "diff"},
    ],
)
def test_sequence_rejects_out_of_contract_params(client: TestClient, params: dict[str, float | str]) -> None:
    assert client.get("/api/sequence", params=params).status_code == 422


@pytest.mark.usefixtures("synthetic_runner")
def test_sequence_job_then_cached_sequence_with_served_frames(client: TestClient) -> None:
    accepted = client.get("/api/sequence", params=MOVER_QUERY)
    assert accepted.status_code == 202
    status = poll(client, accepted.json()["job_id"])
    assert status["status"] == "done", status["error"]
    cached = client.get("/api/sequence", params=MOVER_QUERY)
    assert cached.status_code == 200
    frame = cached.json()["frames"][0]
    data = client.get(frame["data"])
    assert len(data.content) == frame["shape"][0] * frame["shape"][1] * 4


@pytest.mark.usefixtures("synthetic_runner")
def test_unknown_job_is_404(client: TestClient) -> None:
    assert client.get(f"/api/jobs/{'0' * 32}").status_code == 404


def test_job_id_must_be_hex(client: TestClient) -> None:
    assert client.get("/api/jobs/..%2F..%2Fsecret").status_code in (404, 422)
