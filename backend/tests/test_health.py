from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "test-sidecar-token"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def test_health_is_public() -> None:
    client = TestClient(create_app(TOKEN))

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "fluent-ai-sidecar"
    assert payload["version"] == "0.1.0"
    assert payload["timestamp"]


def test_ready_requires_bearer_token() -> None:
    client = TestClient(create_app(TOKEN))

    response = client.get("/api/system/ready")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_ready_returns_authenticated_metadata() -> None:
    client = TestClient(create_app(TOKEN))

    response = client.get("/api/system/ready", headers=AUTH_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["service"] == "fluent-ai-sidecar"
    assert isinstance(payload["pid"], int)
    assert payload["pid"] > 0
