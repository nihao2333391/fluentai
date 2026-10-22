from fastapi.testclient import TestClient

from app.main import create_app

TOKEN = "test-sidecar-token"


def test_wrong_token_is_rejected() -> None:
    client = TestClient(create_app(TOKEN))

    response = client.get(
        "/api/system/ready",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401


def test_missing_configured_token_returns_service_unavailable() -> None:
    client = TestClient(create_app(None))

    response = client.get(
        "/api/system/ready",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert response.status_code == 503


def test_shutdown_requires_auth_and_invokes_callback() -> None:
    app = create_app(TOKEN)
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
