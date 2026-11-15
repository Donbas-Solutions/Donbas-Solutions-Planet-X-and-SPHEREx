from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_gaia import BARNARD_FIELD_CSV, BARNARD_ID, CENTER_DEC, CENTER_RA, LAST_VISIT_MJD
from test_jobs import fetch_synthetic
from test_resolve import BARNARD_CSV, HEADER

from app.archive.gaia import GaiaCatalog
from app.archive.http import make_http
from app.archive.resolve import Resolver
from app.config import settings
from app.jobs import JobRunner
from app.main import app
from app.storage import BundleStore

# Synthetic cutouts sit at the MOVER test target.
MOVER_QUERY = {"ra": 150.0, "dec": 10.0, "ref_epoch": 2025.0, "pmra": 0.0, "pmdec": 12400.0, "fov": 3.0}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def synthetic_runner(client: TestClient) -> JobRunner:
    store = BundleStore(settings.processed_dir, url_prefix="/files", ttl_s=3600.0)
    runner = JobRunner(fetch_synthetic, store)
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


def use_simbad(answer: httpx.Response) -> None:
    app.state.http = make_http(transport=httpx.MockTransport(lambda request: answer))
    app.state.resolver = Resolver()


def test_resolve_returns_position_and_motion(client: TestClient) -> None:
    use_simbad(httpx.Response(200, text=BARNARD_CSV))
    body = client.get("/api/resolve", params={"name": "Barnard's star"}).json()
    assert (body["name"], body["pmdec"]) == ("Barnard's star", 10362.394)


def test_resolve_unknown_name_is_404(client: TestClient) -> None:
    use_simbad(httpx.Response(200, text=HEADER))
    assert client.get("/api/resolve", params={"name": "no such object"}).status_code == 404


def test_resolve_without_simbad_is_503(client: TestClient) -> None:
    use_simbad(httpx.Response(404, text="<!doctype html>"))
    assert client.get("/api/resolve", params={"name": "R Dra"}).status_code == 503


def build_mover(client: TestClient) -> None:
    accepted = client.get("/api/sequence", params=MOVER_QUERY)
    if accepted.status_code == 202:
        assert poll(client, accepted.json()["job_id"])["status"] == "done"


MOVER_TARGET = {k: v for k, v in MOVER_QUERY.items() if k != "fov"}


@pytest.mark.usefixtures("synthetic_runner")
@pytest.mark.parametrize("path", ["/api/spectrum", "/api/lightcurve"])
def test_spectrum_and_lightcurve_after_the_sequence(client: TestClient, path: str) -> None:
    build_mover(client)
    r = client.get(path, params=MOVER_TARGET)
    assert r.status_code == 200
    assert len(r.json()["points"]) > 0


@pytest.mark.usefixtures("synthetic_runner")
def test_live_sequence_links_its_spectrum(client: TestClient) -> None:
    build_mover(client)
    link = client.get("/api/sequence", params=MOVER_QUERY).json()["meta"]["spectrum"]
    assert client.get(link).json()["points"]


@pytest.mark.usefixtures("synthetic_runner")
def test_spectrum_before_any_sequence_is_404(client: TestClient) -> None:
    assert client.get("/api/spectrum", params={"ra": 12.0, "dec": -30.0}).status_code == 404


BARNARD_FIELD = {"ra": CENTER_RA, "dec": CENTER_DEC, "fov": 4, "mjd": LAST_VISIT_MJD}


def use_gaia(answer: httpx.Response) -> None:
    app.state.http = make_http(transport=httpx.MockTransport(lambda request: answer))
    app.state.gaia = GaiaCatalog()


def test_overlays_return_gaia_stars_at_the_frame_epoch(client: TestClient) -> None:
    use_gaia(httpx.Response(200, text=BARNARD_FIELD_CSV))
    r = client.get("/api/overlays", params=BARNARD_FIELD)
    assert r.status_code == 200
    star = r.json()["gaia"][0]
    assert star["source_id"] == BARNARD_ID
    assert (star["dec"], star["pmdec"], star["g"]) == pytest.approx((4.770049, 10362.394, 8.194), abs=1e-3)


def test_overlays_with_gaia_list_nothing_as_unavailable(client: TestClient) -> None:
    use_gaia(httpx.Response(200, text=BARNARD_FIELD_CSV))
    body = client.get("/api/overlays", params=BARNARD_FIELD).json()
    assert (sorted(body), body["unavailable"]) == (["gaia", "unavailable"], [])


def test_overlays_without_gaia_list_it_as_unavailable(client: TestClient) -> None:
    use_gaia(httpx.Response(404, text="<!doctype html>"))
    r = client.get("/api/overlays", params=BARNARD_FIELD)
    assert r.status_code == 200
    assert (r.json()["gaia"], r.json()["unavailable"]) == ([], ["gaia"])


@pytest.mark.parametrize(
    "change",
    [{"mjd": 0}, {"mjd": "nan"}, {"fov": 1}, {"fov": 31}, {"ra": 360}, {"dec": -91}],
)
def test_overlays_reject_out_of_contract_params(client: TestClient, change: dict[str, float | str]) -> None:
    assert client.get("/api/overlays", params=BARNARD_FIELD | change).status_code == 422


def test_overlays_need_the_frame_epoch(client: TestClient) -> None:
    params = {k: v for k, v in BARNARD_FIELD.items() if k != "mjd"}
    assert client.get("/api/overlays", params=params).status_code == 422
