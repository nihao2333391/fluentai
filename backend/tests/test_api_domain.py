from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _automation_payload(name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": "API automation",
        "status": "draft",
        "preset": {
            "schema_version": 1,
            "fluent_version": "25.2.0",
            "items": [
                {
                    "setting_id": "solver.iterations",
                    "type": "int",
                    "value": 500,
                    "required": True,
                }
            ],
        },
    }


def test_business_api_requires_authentication(tmp_path: Path) -> None:
    client = TestClient(create_app("token", tmp_path / "auth-api.db"))

    assert client.get("/api/automations").status_code == 401


def test_automation_model_settings_job_and_log_api(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    first = app_client.post(
        "/api/automations",
        headers=auth_headers,
        json=_automation_payload("API Baseline"),
    )
    assert first.status_code == 201
    first_automation = first.json()
    assert first_automation["name"] == "API Baseline"

    duplicate = app_client.post(
        "/api/automations",
        headers=auth_headers,
        json=_automation_payload("api baseline"),
    )
    assert duplicate.status_code == 409

    second = app_client.post(
        "/api/automations",
        headers=auth_headers,
        json=_automation_payload("API Alternate"),
    )
    second_automation = second.json()

    listed = app_client.get("/api/automations", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    model_file = tmp_path / "api-case.cas.h5"
    model_file.write_bytes(b"fake case")
    model = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={
            "name": "API case",
            "file_path": str(model_file),
            "description": "API model",
            "tags": ["api"],
        },
    )
    assert model.status_code == 201
    model_id = model.json()["id"]

    model_file.write_bytes(b"updated case from API")
    refreshed = app_client.post(f"/api/models/{model_id}/refresh", headers=auth_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["file_size"] == model_file.stat().st_size

    associated = app_client.post(
        f"/api/models/{model_id}/associate",
        headers=auth_headers,
        json={"automation_id": first_automation["id"], "is_default": True},
    )
    assert associated.status_code == 200
    assert associated.json()["default_automation_id"] == first_automation["id"]

    associated = app_client.post(
        f"/api/models/{model_id}/associate",
        headers=auth_headers,
        json={"automation_id": second_automation["id"], "is_default": True},
    )
    assert associated.json()["default_automation_id"] == second_automation["id"]

    settings = app_client.get("/api/settings", headers=auth_headers)
    assert settings.status_code == 200
    assert settings.json()["values"]["language"] == "zh"

    settings_update = app_client.put(
        "/api/settings",
        headers=auth_headers,
        json={"values": {"language": "en", "ui_theme": "dark"}},
    )
    assert settings_update.status_code == 200
    assert settings_update.json()["values"]["language"] == "en"

    job = app_client.post(
        "/api/jobs",
        headers=auth_headers,
        json={"job_type": "apply-preset", "payload": {"automation_id": 1}},
    )
    assert job.status_code == 201
    job_id = job.json()["id"]
    assert app_client.get(f"/api/jobs/{job_id}", headers=auth_headers).status_code == 200

    log = app_client.post(
        "/api/sync-logs",
        headers=auth_headers,
        json={
            "direction": "apply",
            "target": "Fluent",
            "automation_id": first_automation["id"],
            "model_id": model_id,
            "payload": {"verified": True},
            "status": "success",
            "message": "verified",
        },
    )
    assert log.status_code == 201
    logs = app_client.get("/api/sync-logs", headers=auth_headers)
    assert logs.status_code == 200
    assert logs.json()[0]["status"] == "success"


def test_model_api_validates_extension_and_file_existence(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    wrong_extension = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={"name": "bad", "file_path": str(tmp_path / "bad.txt"), "tags": []},
    )
    assert wrong_extension.status_code == 422

    missing = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={"name": "missing", "file_path": str(tmp_path / "missing.cas"), "tags": []},
    )
    assert missing.status_code == 400
