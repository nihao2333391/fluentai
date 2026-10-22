from pathlib import Path

from fastapi.testclient import TestClient


def _preset(setting_id: str, value: float) -> dict[str, object]:
    return {
        "schema_version": 1,
        "fluent_version": "25.2.0",
        "items": [
            {
                "setting_id": setting_id,
                "type": "float",
                "value": value,
                "required": True,
            }
        ],
    }


def test_fluent_connection_catalog_and_settings_api(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    status_response = app_client.get("/api/fluent/status", headers=auth_headers)
    assert status_response.status_code == 200
    assert status_response.json()["connected"] is False

    catalog = app_client.get("/api/fluent/catalog", headers=auth_headers)
    assert catalog.status_code == 200
    assert len(catalog.json()) == 20

    connected = app_client.post(
        "/api/fluent/connect",
        headers=auth_headers,
        json={"mode": "launch", "ui_mode": "no_gui"},
    )
    assert connected.status_code == 200
    assert connected.json()["connected"] is True

    read_response = app_client.post(
        "/api/fluent/settings/read",
        headers=auth_headers,
        json={"setting_ids": ["reference.area", "residual.continuity"]},
    )
    assert read_response.status_code == 200
    assert read_response.json()["reference.area"] == 1.0

    write_response = app_client.post(
        "/api/fluent/settings/write",
        headers=auth_headers,
        json={
            "items": [
                {
                    "setting_id": "reference.area",
                    "type": "float",
                    "value": 1.2,
                    "required": True,
                }
            ]
        },
    )
    assert write_response.status_code == 200
    assert write_response.json()["status"] == "success"

    read_back = app_client.post(
        "/api/fluent/settings/read",
        headers=auth_headers,
        json={"setting_ids": ["reference.area"]},
    )
    assert read_back.json()["reference.area"] == 1.2


def test_preset_validation_and_direct_apply(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    invalid = app_client.post(
        "/api/fluent/presets/validate",
        headers=auth_headers,
        json=_preset("residual.continuity", -0.1),
    )
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False

    valid = app_client.post(
        "/api/fluent/presets/validate",
        headers=auth_headers,
        json=_preset("reference.area", 1.3),
    )
    assert valid.json()["valid"] is True

    app_client.post(
        "/api/fluent/connect",
        headers=auth_headers,
        json={"mode": "launch", "ui_mode": "no_gui"},
    )
    applied = app_client.post(
        "/api/fluent/presets/apply",
        headers=auth_headers,
        json=_preset("reference.area", 1.3),
    )
    assert applied.status_code == 200
    assert applied.json()["status"] == "success"


def test_apply_automation_vertical_slice(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    automation = app_client.post(
        "/api/automations",
        headers=auth_headers,
        json={
            "name": "Vertical slice",
            "description": "Apply one setting",
            "status": "active",
            "preset": _preset("reference.area", 1.4),
        },
    )
    assert automation.status_code == 201
    automation_id = automation.json()["id"]

    model_file = tmp_path / "vertical-slice.cas.h5"
    model_file.write_bytes(b"fake Fluent case")
    model = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={
            "name": "Vertical slice model",
            "file_path": str(model_file),
            "description": "",
            "tags": ["e2e"],
        },
    )
    assert model.status_code == 201
    model_id = model.json()["id"]

    opened = app_client.post(
        f"/api/models/{model_id}/open",
        headers=auth_headers,
        json={"load_case": True},
    )
    assert opened.status_code == 200
    assert opened.json()["status"] == "success"

    workflow = app_client.post(
        f"/api/automations/{automation_id}/apply",
        headers=auth_headers,
        json={
            "model_id": model_id,
            "load_case": True,
            "connection": {"mode": "launch", "ui_mode": "no_gui"},
        },
    )
    assert workflow.status_code == 200
    payload = workflow.json()
    assert payload["status"] == "success"
    assert payload["apply_report"]["status"] == "success"
    assert payload["sync_log_id"] is not None

    value = app_client.post(
        "/api/fluent/settings/read",
        headers=auth_headers,
        json={"setting_ids": ["reference.area"]},
    )
    assert value.json()["reference.area"] == 1.4

    jobs = app_client.get("/api/jobs", headers=auth_headers)
    assert jobs.json()[0]["status"] == "succeeded"
    assert jobs.json()[0]["progress"] == 100

    logs = app_client.get("/api/sync-logs", headers=auth_headers)
    assert logs.json()[0]["direction"] == "apply"
    assert logs.json()[0]["status"] == "success"
    assert logs.json()[0]["automation_id"] == automation_id
    assert logs.json()[0]["model_id"] == model_id
