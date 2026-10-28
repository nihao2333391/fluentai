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
                    "task_path": ["describe_geometry"],
                    "argument_path": ["setup_type"],
                    "value": "The geometry consists of only fluid regions with no voids",
                    "required": True,
                },
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
        "apply_share_topology",
        "enclose_fluid_regions",
        "update_boundaries",
        "create_regions",
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


def test_meshing_connection_failure_returns_readable_redacted_detail(
    app_client: TestClient,
    auth_headers: dict[str, str],
    fake_meshing_adapter: Any,
    monkeypatch: Any,
    caplog: Any,
) -> None:
    secret = "test-session-password"

    def fail_connect(_config: Any) -> None:
        raise RuntimeError(f"gRPC authentication failed for {secret}")

    monkeypatch.setattr(fake_meshing_adapter, "connect", fail_connect)
    response = app_client.post(
        "/api/meshing/connect",
        headers=auth_headers,
        json={"mode": "attach", "ui_mode": "gui", "port": 61485, "password": secret},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "RuntimeError" in detail
    assert "gRPC authentication failed" in detail
    assert secret not in detail
    assert secret not in caplog.text


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
    assert snapshot["status"] in {"starting", "waiting", "failed"}
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
    assert snapshot["phase"] == "surface_ready"
    assert snapshot["current_step_index"] == 2
    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["steps"][0]["duration_ms"] is not None
    assert fake_meshing_adapter.last_config is not None
    assert fake_meshing_adapter.last_config.ui_mode == "gui"
    assert fake_meshing_adapter.connect_calls == 1

    executed = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/execute",
        headers=auth_headers,
        json={"step_index": 2},
    )
    assert executed.status_code == 200
    assert executed.json()["snapshot"]["steps"][2]["status"] == "completed"
    assert executed.json()["snapshot"]["phase"] == "volume_ready"
    assert executed.json()["snapshot"]["current_step_index"] == 7
    executed_volume = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/execute",
        headers=auth_headers,
        json={"step_index": 10},
    )
    assert executed_volume.status_code == 200
    assert executed_volume.json()["snapshot"]["phase"] == "completed"

    next_model = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/next-model",
        headers=auth_headers,
    )
    assert next_model.status_code == 200
    assert next_model.json()["current_model_index"] == 1
    assert next_model.json()["phase"] == "surface_ready"
    assert next_model.json()["current_step_index"] == 2
    assert next_model.json()["steps"][0]["status"] == "completed"
    assert fake_meshing_adapter.workflow_resets == 2


def test_live_step_rejects_labels_missing_from_the_imported_geometry(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    fake_meshing_adapter: Any,
) -> None:
    geometry = tmp_path / "labels.dsco"
    geometry.write_bytes(b"fake geometry")
    model = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={"name": "Labels", "file_path": str(geometry), "description": "", "tags": []},
    )
    assert model.status_code == 201

    payload = _payload("Label check")
    payload["preset"]["items"].append(
        {
            "task_path": ["add_local_sizing"],
            "argument_path": ["boi_face_label_list"],
            "value": ["wall-missing"],
            "required": True,
            "compound_child_name": "missing-wall-size",
        }
    )
    automation = app_client.post(
        "/api/meshing-automations", headers=auth_headers, json=payload
    )
    assert automation.status_code == 201
    connected = app_client.post(
        "/api/meshing/connect",
        headers=auth_headers,
        json={"mode": "launch", "ui_mode": "gui", "processor_count": 1},
    )
    assert connected.status_code == 200
    started = app_client.post(
        "/api/meshing/live-sessions",
        headers=auth_headers,
        json={"automation_id": automation.json()["id"], "model_ids": [model.json()["id"]]},
    )
    session_id = started.json()["session_id"]
    for _ in range(100):
        snapshot = app_client.get(
            f"/api/meshing/live-sessions/{session_id}", headers=auth_headers
        ).json()
        if snapshot["status"] in {"waiting", "failed"}:
            break
        time.sleep(0.05)
    assert snapshot["status"] == "waiting"

    entered = app_client.post(
        f"/api/meshing/live-sessions/{session_id}/enter",
        headers=auth_headers,
        json={"step_index": 1},
    )
    assert entered.status_code == 200
    body = entered.json()
    assert body["status"] == "failed"
    assert body["write_report"]["missing_names"] == ["wall-missing"]
    assert "wall-missing" in body["message"]
