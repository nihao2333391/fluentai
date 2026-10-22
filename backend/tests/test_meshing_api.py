from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def _payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Venturi preset",
        "model_family": "Venturi",
        "status": "draft",
        "preset": {
            "schema_version": 1,
            "fluent_version": "25.2.0",
            "workflow_type": "watertight",
            "items": [
                {
                    "task_path": ["import_geometry"],
                    "argument_path": ["length_unit"],
                    "value": "m",
                    "required": True,
                }
            ],
        },
    }


def test_meshing_schema_and_automation_api(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    schemas = app_client.get("/api/meshing/schemas", headers=auth_headers)
    assert schemas.status_code == 200
    assert {item["workflow_type"] for item in schemas.json()} == {"watertight", "fault-tolerant"}

    watertight = app_client.get("/api/meshing/schemas/watertight", headers=auth_headers)
    assert watertight.status_code == 200
    local_sizing = next(
        task for task in watertight.json()["tasks"] if task["display_name"] == "Add Local Sizing"
    )
    assert local_sizing["supports_child_template"] is True
    assert local_sizing["child_template"]["arguments"]

    created = app_client.post(
        "/api/meshing-automations", headers=auth_headers, json=_payload("Venturi A")
    )
    assert created.status_code == 201
    automation_id = created.json()["id"]

    listed = app_client.get("/api/meshing-automations", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == automation_id

    invalid = _payload("Invalid")
    invalid["preset"]["items"][0]["argument_path"] = ["missing_argument"]
    rejected = app_client.post("/api/meshing-automations", headers=auth_headers, json=invalid)
    assert rejected.status_code == 422


def test_apply_meshing_automation(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    geometry = tmp_path / "venturi.dsco"
    geometry.write_bytes(b"fake geometry")
    model = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={
            "name": "Venturi geometry",
            "file_path": str(geometry),
            "description": "",
            "tags": ["meshing"],
        },
    )
    assert model.status_code == 201
    model_id = model.json()["id"]

    automation = app_client.post(
        "/api/meshing-automations",
        headers=auth_headers,
        json=_payload("Apply Venturi"),
    )
    assert automation.status_code == 201
    automation_id = automation.json()["id"]

    applied = app_client.post(
        f"/api/meshing-automations/{automation_id}/apply",
        headers=auth_headers,
        json={"model_id": model_id, "import_geometry": True},
    )
    assert applied.status_code == 200
    report = applied.json()
    assert report["status"] == "success"
    assert report["apply_report"]["status"] == "success"
    assert report["apply_report"]["stopped_before"] == [
        "Generate the Surface Mesh",
        "Generate the Volume Mesh",
    ]

    logs = app_client.get("/api/sync-logs", headers=auth_headers)
    assert logs.status_code == 200
    assert logs.json()[0]["meshing_automation_id"] == automation_id
