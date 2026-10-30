from pathlib import Path

from app.database import Database
from app.domain import (
    AutomationCreate,
    AutomationUpdate,
    FluentConnectionConfig,
    JobCreate,
    ModelAutomationAssociate,
    ModelCreate,
    PresetDocument,
    PresetItem,
    SyncLogCreate,
)
from app.fluent.fake import FakeFluentAdapter
from app.repositories.automations import AutomationRepository
from app.repositories.errors import RepositoryConflictError
from app.repositories.jobs import JobRepository
from app.repositories.meshing_tasks import MeshingTaskRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository
from app.repositories.sync_logs import SyncLogRepository


def _automation(name: str) -> AutomationCreate:
    return AutomationCreate(
        name=name,
        description="test automation",
        preset=PresetDocument(
            fluent_version="25.2.0",
            items=[PresetItem(setting_id="solver.iterations", type="int", value=500)],
        ),
    )


def test_automation_crud_and_case_insensitive_unique_name(tmp_path: Path) -> None:
    database = Database(tmp_path / "automations.db")
    database.initialize()
    repository = AutomationRepository(database)

    created = repository.create(_automation("Baseline"))
    assert created.id > 0
    assert created.preset.items[0].value == 500

    updated = repository.update(
        created.id,
        AutomationUpdate(
            name="Baseline Updated",
            description="changed",
            preset=created.preset,
            status="active",
        ),
    )
    assert updated.name == "Baseline Updated"
    assert updated.status == "active"

    try:
        repository.create(_automation("baseline updated"))
    except RepositoryConflictError:
        pass
    else:
        raise AssertionError("Case-insensitive duplicate automation name was accepted")

    repository.delete(created.id)
    assert repository.list() == []


def test_models_support_many_to_many_associations_and_one_default(tmp_path: Path) -> None:
    database = Database(tmp_path / "models.db")
    database.initialize()
    automations = AutomationRepository(database)
    models = ModelRepository(database)

    first = automations.create(_automation("First"))
    second = automations.create(_automation("Second"))
    model_file = tmp_path / "case.cas.h5"
    model_file.write_bytes(b"fake fluent case")

    model = models.create(
        ModelCreate(
            name="Test case",
            file_path=str(model_file),
            description="model description",
            tags=["smoke", "test"],
        )
    )
    assert model.file_size > 0
    assert model.automation_ids == []

    associated = models.associate(model.id, ModelAutomationAssociate(automation_id=first.id))
    assert associated.default_automation_id == first.id
    assert associated.automation_ids == [first.id]

    associated = models.associate(
        model.id,
        ModelAutomationAssociate(automation_id=second.id, is_default=True),
    )
    assert associated.default_automation_id == second.id
    assert set(associated.automation_ids) == {first.id, second.id}

    model_file.write_bytes(b"updated fake fluent case with more bytes")
    refreshed = models.refresh(model.id)
    assert refreshed.file_size == model_file.stat().st_size
    assert refreshed.file_size > model.file_size

    with database.connect() as connection:
        default_count = connection.execute(
            "SELECT COUNT(*) FROM model_automations WHERE model_id = ? AND is_default = 1",
            (model.id,),
        ).fetchone()[0]
    assert default_count == 1


def test_settings_jobs_and_sync_logs(tmp_path: Path) -> None:
    database = Database(tmp_path / "supporting.db")
    database.initialize()

    settings = SettingsRepository(database)
    assert settings.get_all()["ui_theme"] == "system"
    updated = settings.update({"ui_theme": "dark", "language": "en"})
    assert updated["ui_theme"] == "dark"
    assert updated["language"] == "en"

    jobs = JobRepository(database)
    job = jobs.create(JobCreate(job_type="apply-preset", payload={"automation_id": 1}))
    assert job.status == "queued"
    running = jobs.update(job.id, status="running", progress=25, message="Connecting")
    assert running.started_at is not None
    completed = jobs.update(
        job.id,
        status="succeeded",
        progress=100,
        message="Done",
        result={"applied": 1},
    )
    assert completed.status == "succeeded"
    assert completed.result == {"applied": 1}

    logs = SyncLogRepository(database)
    log = logs.create(
        SyncLogCreate(
            direction="apply",
            target="Fluent",
            payload={"automation_id": 1},
            status="success",
            message="verified",
        )
    )
    assert log.direction == "apply"
    assert logs.list()[0].id == log.id


def test_meshing_tasks_keep_snapshots_and_mark_interrupted_on_restart(tmp_path: Path) -> None:
    database = Database(tmp_path / "meshing-tasks.db")
    database.initialize()
    tasks = MeshingTaskRepository(database)
    tasks.create(
        "task-1",
        None,
        "Venturi template",
        3,
        {"workflow_type": "watertight"},
        [{"name": "Venturi.scdoc"}],
        "session-1",
    )
    with database.connect() as connection:
        connection.execute("UPDATE meshing_tasks SET status='waiting_surface' WHERE id='task-1'")

    tasks.mark_running_interrupted()

    task = tasks.list()[0]
    assert task.id == "task-1"
    assert task.template_revision == 3
    assert task.model_names == ["Venturi.scdoc"]
    assert task.status == "interrupted"
    assert "应用重启" in task.message


def test_legacy_archives_are_backfilled_into_task_history_idempotently(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy-meshing.db")
    database.initialize()
    mesh = tmp_path / "old-result.msh.h5"
    record_json = tmp_path / "old-record.json"
    record_markdown = tmp_path / "old-record.md"
    mesh.write_bytes(b"mesh")
    record_json.write_text(
        '{"model_name":"Legacy model","model_path":"/models/legacy.scdoc"}',
        encoding="utf-8",
    )
    # Missing report files remain visible in the index as missing entries.
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO meshing_result_archives(
                id, session_id, automation_id, model_id, mesh_path,
                record_json_path, record_markdown_path, created_at
            ) VALUES ('archive-old', 'session-old', NULL, NULL, ?, ?, ?, '2026-01-01T00:00:00Z')""",
            (str(mesh), str(record_json), str(record_markdown)),
        )

    tasks = MeshingTaskRepository(database)
    tasks.backfill_legacy_archives()
    tasks.backfill_legacy_archives()

    history = tasks.history("legacy-session-old")
    assert history.task.status == "completed"
    assert history.task.model_names == ["Legacy model"]
    assert {artifact.kind: artifact.status for artifact in history.artifacts} == {
        "mesh": "retained",
        "record_json": "retained",
        "record_markdown": "missing",
    }
    indexed = [event for event in history.events if event.event_type == "legacy_archive_indexed"]
    assert len(indexed) == 1


def test_fake_fluent_adapter_reads_and_writes_settings() -> None:
    adapter = FakeFluentAdapter({"solver.iterations": 200})
    session = adapter.connect(FluentConnectionConfig(mode="launch"))
    assert session.connected is True

    results = adapter.apply_preset(
        PresetDocument(
            items=[
                PresetItem(setting_id="solver.iterations", type="int", value=500),
                PresetItem(setting_id="missing.setting", type="bool", value=True),
            ]
        )
    )

    assert results.results[0].success is True
    assert adapter.read_settings(["solver.iterations"]) == {"solver.iterations": 200}
    assert results.status == "failed"
    assert results.rollback_attempted is True
    assert results.results[1].success is False
