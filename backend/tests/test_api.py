from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "spherex_dr1" in body["collections"]
    assert body["cache"]["raw_mb"] >= 0


def test_unimplemented_endpoints_say_so():
    r = client.get("/api/sequence", params={"ra": 269.45, "dec": 4.69})
    assert r.status_code == 501
