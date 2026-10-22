from pathlib import Path

from fastapi.testclient import TestClient

from app.database import Database
from app.domain import JobCreate
from app.repositories.jobs import JobRepository


def test_recent_session_api_resolves_saved_records(
    app_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    model_file = tmp_path / "recent.cas.h5"
    model_file.write_bytes(b"case")
    model = app_client.post(
        "/api/models",
        headers=auth_headers,
        json={"name": "Recent model", "file_path": str(model_file), "tags": []},
    ).json()
    automation = app_client.post(
        "/api/automations",
        headers=auth_headers,
        json={
            "name": "Recent automation",
            "description": "",
            "status": "active",
            "preset": {"schema_version": 1, "fluent_version": "25.2.0", "items": []},
        },
    ).json()
    app_client.put(
        "/api/settings",
        headers=auth_headers,
        json={
            "values": {
                "recent_model_id": str(model["id"]),
                "recent_automation_id": str(automation["id"]),
                "recent_session_at": "2026-10-22T00:00:00Z",
            }
        },
    )
    recent = app_client.get("/api/session/recent", headers=auth_headers)
    assert recent.status_code == 200
    payload = recent.json()
    assert payload["model"]["name"] == "Recent model"
    assert payload["automation"]["name"] == "Recent automation"
    assert payload["updated_at"] == "2026-10-22T00:00:00Z"


def test_cancelled_job_cannot_be_overwritten(tmp_path: Path) -> None:
    database = Database(tmp_path / "jobs.db")
    database.initialize()
    jobs = JobRepository(database)
    job = jobs.create(JobCreate(job_type="test", payload={}))
    jobs.update(job.id, status="running", progress=20, message="Working")
    cancelled = jobs.cancel(job.id)
    assert cancelled.status == "cancelled"
    updated = jobs.update(job.id, status="succeeded", progress=100, message="Late completion")
    assert updated.status == "cancelled"
    assert updated.message == "Cancelled by user."


def test_sync_log_filters(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    app_client.post(
        "/api/sync-logs",
        headers=auth_headers,
        json={
            "direction": "apply",
            "target": "Fluent",
            "payload": {"kind": "solver"},
            "status": "success",
            "message": "Solver apply succeeded",
        },
    )
    app_client.post(
        "/api/sync-logs",
        headers=auth_headers,
        json={
            "direction": "apply",
            "target": "Fluent Meshing",
            "payload": {"kind": "meshing"},
            "status": "failed",
            "message": "Meshing apply failed",
        },
    )
    filtered = app_client.get(
        "/api/sync-logs?status_filter=failed&search=Meshing",
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["target"] == "Fluent Meshing"
