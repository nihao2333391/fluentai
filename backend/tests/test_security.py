from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "test-sidecar-token"


def test_wrong_token_is_rejected(tmp_path: Path) -> None:
    client = TestClient(create_app(TOKEN, tmp_path / "wrong-token.db"))

    response = client.get(
        "/api/system/ready",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_missing_configured_token_returns_service_unavailable(tmp_path: Path) -> None:
    client = TestClient(create_app(None, tmp_path / "no-token.db"))

    response = client.get(
        "/api/system/ready",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 503


def test_shutdown_requires_auth_and_invokes_callback(tmp_path: Path) -> None:
    app = create_app(TOKEN, tmp_path / "shutdown.db")
    called = False

    def request_shutdown() -> None:
        nonlocal called
        called = True

    app.state.request_shutdown = request_shutdown
    client = TestClient(app)

    unauthenticated = client.post("/api/system/shutdown")
    assert unauthenticated.status_code == 401

    response = client.post(
        "/api/system/shutdown",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 202
    assert response.json() == {"status": "shutting-down"}
    assert called is True
