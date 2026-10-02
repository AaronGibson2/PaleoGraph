from fastapi.testclient import TestClient

from app.main import app


def test_health_works_without_database() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


def test_cors_allows_configured_origin_only() -> None:
    with TestClient(app) as client:
        allowed = client.get("/api/v1/health", headers={"Origin": "http://localhost:3000"})
        denied = client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers
