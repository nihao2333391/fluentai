import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.repositories.meshing_automations import MeshingAutomationRepository


def _payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Venturi preset",
        "model_family": "Venturi",
        "status": "active",
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
                },
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

    edited = _payload("Venturi A")
    edited["preset"]["items"][1]["value"] = "mm"
    updated = app_client.put(
        f"/api/meshing-automations/{automation_id}", headers=auth_headers, json=edited
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["revision"] == 2
    assert updated.json()["published_revision"] == 1
    published = MeshingAutomationRepository(app_client.app.state.database).preset_revision(
        automation_id, 1
    )
    assert published.items[1].value == "m"

    invalid = _payload("Invalid")
    invalid["preset"]["items"][0]["argument_path"] = ["missing_argument"]
    rejected = app_client.post("/api/meshing-automations", headers=auth_headers, json=invalid)
    assert rejected.status_code == 422


def test_renaming_category_updates_template_model_category(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    category = app_client.post(
        "/api/categories",
        headers=auth_headers,
        json={"name": "Venturi parts", "description": ""},
    )
    assert category.status_code == 201
    category_id = category.json()["id"]

    template_payload = _payload("Venturi category template")
    template_payload["category_id"] = category_id
    created = app_client.post(
        "/api/meshing-automations", headers=auth_headers, json=template_payload
    )
    assert created.status_code == 201
    assert created.json()["model_family"] == "Venturi parts"

    renamed = app_client.patch(
        f"/api/categories/{category_id}",
        headers=auth_headers,
        json={"name": "文丘里管"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["id"] == category_id
    assert renamed.json()["name"] == "文丘里管"
    assert renamed.json()["template_count"] == 1

    listed_templates = app_client.get("/api/meshing-automations", headers=auth_headers)
    matching_template = next(
        item for item in listed_templates.json() if item["id"] == created.json()["id"]
    )
    assert matching_template["category_id"] == category_id
    assert matching_template["model_family"] == "文丘里管"


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
        if current["phase"] in {"surface_ready", "failed", "completed", "stopped"}:
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

    for _ in range(100):
        executed = app_client.post(
            f"/api/meshing/live-sessions/{session_id}/execute",
            headers=auth_headers,
            json={"step_index": 2},
        )
        if executed.status_code != 503:
            break
        time.sleep(0.05)
    assert executed.status_code == 200
    assert executed.json()["snapshot"]["steps"][2]["status"] == "completed"
    assert executed.json()["snapshot"]["phase"] == "volume_ready"
    assert executed.json()["snapshot"]["current_step_index"] == 6
    for _ in range(100):
        executed_volume = app_client.post(
            f"/api/meshing/live-sessions/{session_id}/execute",
            headers=auth_headers,
            json={"step_index": 6},
        )
        if executed_volume.status_code != 503:
            break
        time.sleep(0.05)
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


def test_live_sessions_queue_behind_the_task_waiting_for_mesh_action(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
    fake_meshing_adapter: Any,
) -> None:
    session_ids: list[str] = []
    for index in range(2):
        geometry = tmp_path / f"queued-{index}.dsco"
        geometry.write_bytes(b"fake geometry")
        model = app_client.post(
            "/api/models",
            headers=auth_headers,
            json={
                "name": f"Queued model {index}",
                "file_path": str(geometry),
                "description": "",
                "tags": [],
            },
        )
        automation = app_client.post(
            "/api/meshing-automations",
            headers=auth_headers,
            json=_payload(f"Queued template {index}"),
        )
        started = app_client.post(
            "/api/meshing/live-sessions",
            headers=auth_headers,
            json={"automation_id": automation.json()["id"], "model_ids": [model.json()["id"]]},
        )
        assert started.status_code == 200
        session_ids.append(started.json()["session_id"])
        if index == 0:
            for _ in range(300):
                first = app_client.get(
                    f"/api/meshing/live-sessions/{session_ids[0]}", headers=auth_headers
                ).json()
                if first["status"] == "waiting" and first["phase"] == "surface_ready":
                    break
                time.sleep(0.05)
            assert first["phase"] == "surface_ready", first

    queued = app_client.get("/api/meshing/live-sessions/" + session_ids[1], headers=auth_headers)
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"
    task_rows = app_client.get("/api/meshing/tasks", headers=auth_headers).json()
    assert {task["status"] for task in task_rows[:2]} == {"queued", "waiting_surface"}
    waiting_task = next(task for task in task_rows if task["session_id"] == session_ids[0])
    assert waiting_task["surface_mesh_status"] == "ready"
    assert waiting_task["volume_mesh_status"] == "pending"
    refused = app_client.request(
        "DELETE", f"/api/meshing/tasks/{waiting_task['id']}", headers=auth_headers, json={}
    )
    assert refused.status_code == 409
    assert fake_meshing_adapter.connect_calls == 1

    surface = app_client.post(
        f"/api/meshing/live-sessions/{session_ids[0]}/execute",
        headers=auth_headers,
        json={"step_index": 2},
    )
    assert surface.status_code == 200
    volume = app_client.post(
        f"/api/meshing/live-sessions/{session_ids[0]}/execute",
        headers=auth_headers,
        json={"step_index": 6},
    )
    assert volume.status_code == 200
    for _ in range(100):
        finished = app_client.post(
            f"/api/meshing/live-sessions/{session_ids[0]}/next-model", headers=auth_headers
        )
        if finished.status_code != 503:
            break
        time.sleep(0.05)
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "completed"
    finished_task = next(
        task
        for task in app_client.get("/api/meshing/tasks", headers=auth_headers).json()
        if task["session_id"] == session_ids[0]
    )
    assert finished_task["surface_mesh_status"] == "completed"
    assert finished_task["volume_mesh_status"] == "completed"

    # Completed tasks expose their archived mesh and history through one durable record.
    mesh_file = tmp_path / "finished.msh.h5"
    mesh_file.write_bytes(b"mesh result")
    archived = app_client.post(
        f"/api/meshing/live-sessions/{session_ids[0]}/archive",
        headers=auth_headers,
        json={"mesh_path": str(mesh_file), "modeling_notes": "completed mesh"},
    )
    assert archived.status_code == 200
    assert archived.json()["task_id"] == finished_task["id"]
    history = app_client.get(
        f"/api/meshing/tasks/{finished_task['id']}/history", headers=auth_headers
    )
    assert history.status_code == 200
    assert {artifact["kind"] for artifact in history.json()["artifacts"]} == {
        "mesh",
        "record_json",
        "record_markdown",
        "log",
    }
    assert any(event["event_type"] == "log" for event in history.json()["events"])

    deleted = app_client.request(
        "DELETE", f"/api/meshing/tasks/{finished_task['id']}", headers=auth_headers, json={}
    )
    assert deleted.status_code == 200
    assert deleted.json()["files_retained"] == 4
    assert deleted.json()["files_deleted"] == 0
    assert Path(archived.json()["mesh_path"]).is_file()
    assert (
        app_client.get(
            f"/api/meshing/tasks/{finished_task['id']}/history", headers=auth_headers
        ).status_code
        == 404
    )
    deleted_history = app_client.get(
        f"/api/meshing/tasks/{finished_task['id']}/history?include_deleted=true",
        headers=auth_headers,
    )
    assert deleted_history.status_code == 200
    assert deleted_history.json()["task"]["deleted_at"]

    for _ in range(100):
        second = app_client.get(
            f"/api/meshing/live-sessions/{session_ids[1]}", headers=auth_headers
        ).json()
        if second["status"] == "waiting":
            break
        time.sleep(0.05)
    assert second["phase"] == "surface_ready"
    assert second["status"] == "waiting"
    persisted = app_client.get("/api/meshing/tasks", headers=auth_headers).json()
    assert len(persisted) == 1
    all_tasks = app_client.get(
        "/api/meshing/tasks?include_deleted=true", headers=auth_headers
    ).json()
    assert len({task["id"] for task in all_tasks}) == 2

    second_task = next(task for task in all_tasks if task["session_id"] == session_ids[1])
    for step_index in (2, 6):
        response = app_client.post(
            f"/api/meshing/live-sessions/{session_ids[1]}/execute",
            headers=auth_headers,
            json={"step_index": step_index},
        )
        assert response.status_code == 200
    for _ in range(100):
        finished_second = app_client.post(
            f"/api/meshing/live-sessions/{session_ids[1]}/next-model",
            headers=auth_headers,
        )
        if finished_second.status_code != 503:
            break
        time.sleep(0.05)
    assert finished_second.status_code == 200, finished_second.text
    second_mesh = tmp_path / "finished-second.msh.h5"
    second_mesh.write_bytes(b"second mesh result")
    second_archive = app_client.post(
        f"/api/meshing/live-sessions/{session_ids[1]}/archive",
        headers=auth_headers,
        json={"mesh_path": str(second_mesh), "modeling_notes": "cleanup test"},
    )
    assert second_archive.status_code == 200
    cleaned = app_client.request(
        "DELETE",
        f"/api/meshing/tasks/{second_task['id']}",
        headers=auth_headers,
        json={"cleanup_artifacts": True},
    )
    assert cleaned.status_code == 200
    assert cleaned.json()["files_deleted"] == 4
    assert not Path(second_archive.json()["mesh_path"]).exists()
    cleanup_history = app_client.get(
        f"/api/meshing/tasks/{second_task['id']}/history?include_deleted=true",
        headers=auth_headers,
    ).json()
    assert {artifact["status"] for artifact in cleanup_history["artifacts"]} == {"deleted"}


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
    automation = app_client.post("/api/meshing-automations", headers=auth_headers, json=payload)
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
        if snapshot["phase"] in {"surface_ready", "failed"}:
            break
        time.sleep(0.05)
    assert snapshot["status"] == "failed", snapshot.get("message")
    assert snapshot["phase"] == "failed"
    assert "wall-missing" in snapshot["message"]
    assert all(
        step["task_path"] != ["create_surface_mesh"] or step["status"] != "running"
        for step in snapshot["steps"]
    )
