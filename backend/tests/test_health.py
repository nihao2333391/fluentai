from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_sidecar_metadata() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "fluent-ai-sidecar"
    assert payload["version"] == "0.1.0"
    assert payload["timestamp"]
