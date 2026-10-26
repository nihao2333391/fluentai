import time
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

    workflow_schema = app_client.get(
        "/api/meshing/workflows/watertight/schema", headers=auth_headers
    )
    assert workflow_schema.status_code == 200
    assert workflow_schema.json()["step_order"] == [
        "import_geometry",
        "add_local_sizing",
        "create_surface_mesh",
        "describe_geometry",
        "update_regions",
        "add_boundary_layer",
        "create_volume_mesh",
    ]

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


def test_meshing_connection_and_direct_read_write_api(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    status = app_client.get("/api/meshing/status", headers=auth_headers)
    assert status.status_code == 200
    assert status.json()["connected"] is False

    connected = app_client.post(
        "/api/meshing/connect",
        headers=auth_headers,
        json={"mode": "launch", "ui_mode": "no_gui"},
    )
    assert connected.status_code == 200
    assert connected.json()["connected"] is True

    reference = {
        "task_path": ["import_geometry"],
        "argument_path": ["length_unit"],
    }
    read = app_client.post(
        "/api/meshing/read",
        headers=auth_headers,
        json={"workflow_type": "watertight", "items": [reference]},
    )
    assert read.status_code == 200
    assert read.json()["status"] == "success"
    assert read.json()["items"][0]["value"] == "mm"

    written = app_client.post(
        "/api/meshing/write",
        headers=auth_headers,
        json={
            "workflow_type": "watertight",
            "verify": True,
            "items": [{**reference, "value": "m", "required": True}],
        },
    )
    assert written.status_code == 200
    assert written.json()["status"] == "success"
    assert written.json()["results"][0]["actual"] == "m"

    read_back = app_client.post(
        "/api/meshing/read",
        headers=auth_headers,
        json={"workflow_type": "watertight", "items": [reference]},
    )
    assert read_back.json()["items"][0]["value"] == "m"

    disconnected = app_client.post("/api/meshing/disconnect", headers=auth_headers)
    assert disconnected.status_code == 200
    assert disconnected.json()["connected"] is False


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


def test_live_meshing_session_advances_steps_and_models(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    fake_meshing_adapter: Any,
) -> None:
    model_ids: list[int] = []
    for index in range(2):
        geometry = tmp_path / f"venturi-{index}.dsco"
        geometry.write_bytes(b"fake geometry")
        model = app_client.post(
            "/api/models",
            headers=auth_headers,
            json={
                "name": f"Venturi {index}",
                "file_path": str(geometry),
                "description": "",
                "tags": ["meshing"],
            },
        )
        assert model.status_code == 201
        model_ids.append(model.json()["id"])

    automation = app_client.post(
        "/api/meshing-automations",
        headers=auth_headers,
        json=_payload("Live Venturi"),
    )
    automation_id = automation.json()["id"]
    connected = app_client.post(
        "/api/meshing/connect",
        headers=auth_headers,
        json={"mode": "launch", "ui_mode": "gui", "processor_count": 1},
    )
    assert connected.status_code == 200
    assert connected.json()["connected"] is True
    started = app_client.post(
        "/api/meshing/live-sessions",
        headers=auth_headers,
        json={"automation_id": automation_id, "model_ids": model_ids},
    )
    assert started.status_code == 200
    snapshot = started.json()
    assert snapshot["status"] in {"starting", "waiting"}
    session_id = snapshot["session_id"]
    for _ in range(100):
        current = app_client.get(
            f"/api/meshing/live-sessions/{session_id}", headers=auth_headers
        ).json()
        if current["status"] in {"waiting", "failed", "completed", "stopped"}:
            snapshot = current
            break
        time.sleep(0.05)
    assert snapshot["status"] == "waiting"
    assert snapshot["current_step_index"] == 0
    assert snapshot["steps"][0]["status"] == "active"
    assert fake_meshing_adapter.last_config is not None
    assert fake_meshing_adapter.last_config.ui_mode == "gui"
    assert fake_meshing_adapter.connect_calls == 1

    entered_import = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/enter",
        headers=auth_headers,
        json={"step_index": 0},
    )
    assert entered_import.status_code == 200
    executed_import = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/execute",
        headers=auth_headers,
        json={"step_index": 0},
    )
    assert executed_import.status_code == 200
    assert executed_import.json()["snapshot"]["steps"][0]["status"] == "completed"
    assert executed_import.json()["snapshot"]["current_step_index"] == 1

    entered = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/enter",
        headers=auth_headers,
        json={"step_index": 2},
    )
    assert entered.status_code == 200
    assert entered.json()["snapshot"]["steps"][2]["status"] == "active"
    assert entered.json()["read_report"]["status"] == "success"

    executed = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/execute",
        headers=auth_headers,
        json={"step_index": 2},
    )
    assert executed.status_code == 200
    assert executed.json()["snapshot"]["steps"][2]["status"] == "completed"
    assert executed.json()["snapshot"]["current_step_index"] == 3

    next_model = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/next-model",
        headers=auth_headers,
    )
    assert next_model.status_code == 200
    assert next_model.json()["current_model_index"] == 1
    assert next_model.json()["current_step_index"] == 0
    assert next_model.json()["steps"][0]["status"] == "active"
    assert fake_meshing_adapter.workflow_resets == 2
