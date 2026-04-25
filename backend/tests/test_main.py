"""Smoke test del FastAPI app skeleton (Sprint 0.1)."""

from fastapi.testclient import TestClient

from colazione import __version__
from colazione.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_app_metadata() -> None:
    assert app.title == "Colazione API"
    assert app.version == __version__


def test_openapi_schema_exists() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Colazione API"
    assert "/health" in schema["paths"]
