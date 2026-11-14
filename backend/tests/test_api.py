import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "spherex_dr1" in body["collections"]
    assert body["cache"]["raw_mb"] >= 0


def test_unimplemented_endpoints_say_so() -> None:
    r = client.get("/api/sequence", params={"ra": 269.45, "dec": 4.69})
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
def test_sequence_rejects_out_of_contract_params(params: dict[str, float | str]) -> None:
    assert client.get("/api/sequence", params=params).status_code == 422
