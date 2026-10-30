"""Parallel live-session scheduling with per-session adapter factories."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from app.database import Database
from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingAutomationCreate,
    MeshingLiveSessionSnapshot,
    MeshingLiveSessionStart,
    MeshingPresetDocument,
    MeshingPresetItem,
    ModelCreate,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.fake import FakeMeshingAdapter
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.meshing_tasks import MeshingTaskRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository
from app.services.meshing_service import MeshingService


class RecordingFactory:
    """Hands every session its own fake adapter and records lifecycle."""

    def __init__(self, *, max_sessions: int = 3) -> None:
        self._max_sessions = max_sessions
        self.created: list[FakeMeshingAdapter] = []
        self.disposed: list[FakeMeshingAdapter] = []

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    @property
    def reusable(self) -> bool:
        return False

    def create(self, *, session_id: str, run_dir: Path | None = None) -> MeshingWorkflowAdapter:
        adapter = FakeMeshingAdapter()
        adapter.session_label = session_id  # type: ignore[attr-defined]
        self.created.append(adapter)
        return adapter

    def dispose(self, adapter: MeshingWorkflowAdapter) -> None:
        assert isinstance(adapter, FakeMeshingAdapter)
        self.disposed.append(adapter)


def _setup(
    tmp_path: Path,
) -> tuple[Database, MeshingService, RecordingFactory, int, int]:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "part.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Part", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Parallel",
            preset=MeshingPresetDocument(
                schema_version=2,
                workflow_type="watertight",
                items=[
                    MeshingPresetItem(
                        task_path=["create_surface_mesh"],
                        argument_path=["cfd_surface_mesh_controls", "min_size"],
                        value=0.001,
                    ),
                ],
            ),
        )
    )
    factory = RecordingFactory()
    service = MeshingService(database, FakeMeshingAdapter(), session_adapter_factory=factory)
    return database, service, factory, automation.id, model.id


def _start(
    service: MeshingService, automation_id: int, model_id: int, *, processor_count: int = 1
) -> MeshingLiveSessionSnapshot:
    return service.start_live_session(
        MeshingLiveSessionStart(
            automation_id=automation_id,
            model_ids=[model_id],
            connection=FluentConnectionConfig(mode="launch", processor_count=processor_count),
        )
    )


def _wait_for(
    service: MeshingService,
    session_id: str,
    predicate: Callable[[MeshingLiveSessionSnapshot], bool],
    timeout: float = 15,
) -> MeshingLiveSessionSnapshot:
    deadline = time.monotonic() + timeout
    last: MeshingLiveSessionSnapshot | None = None
    while time.monotonic() < deadline:
        last = service.live.get(session_id)
        if predicate(last):
            return last
        time.sleep(0.02)
    raise AssertionError(f"session {session_id} did not reach expected state: {last}")


def _wait_phase(
    service: MeshingService, session_id: str, phase: str, timeout: float = 15
) -> MeshingLiveSessionSnapshot:
    return _wait_for(service, session_id, lambda snap: snap.phase == phase, timeout=timeout)


_ACTIVE = ("starting", "running", "waiting")


def test_default_parallel_one_keeps_legacy_queueing(tmp_path: Path) -> None:
    _, service, _factory, automation_id, model_id = _setup(tmp_path)
    try:
        first = _start(service, automation_id, model_id)
        second = _start(service, automation_id, model_id)
        third = _start(service, automation_id, model_id)

        assert service.live.get(first.session_id).status in _ACTIVE
        assert service.live.get(third.session_id).status == "queued"
        service.stop_live_session(first.session_id)
        _wait_for(service, second.session_id, lambda snap: snap.status in _ACTIVE)
        assert service.live.get(third.session_id).status == "queued"
    finally:
        service.shutdown()


def test_max_parallel_sessions_runs_multiple_fluent_lanes(tmp_path: Path) -> None:
    database, service, factory, automation_id, model_id = _setup(tmp_path)
    SettingsRepository(database).update({"meshing_max_parallel_sessions": "2"})
    try:
        first = _start(service, automation_id, model_id)
        second = _start(service, automation_id, model_id)
        third = _start(service, automation_id, model_id)

        _wait_phase(service, first.session_id, "surface_ready")
        _wait_phase(service, second.session_id, "surface_ready")
        assert service.live.get(third.session_id).status == "queued"

        # Each session imported its model on its own adapter instance.
        assert len(factory.created) == 3
        assert factory.created[0] is not factory.created[1]
        assert factory.created[0].connect_calls == 1
        assert factory.created[1].connect_calls == 1
        assert factory.created[0].workflow_resets == 1
        assert factory.created[1].workflow_resets == 1

        # Stopping one session releases its slot for the queued session.
        service.stop_live_session(first.session_id)
        _wait_phase(service, third.session_id, "surface_ready")
        assert factory.created[2].connect_calls == 1
    finally:
        service.shutdown()


def test_failed_session_releases_slot_and_others_continue(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "iso.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Iso", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Isolation",
            preset=MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[]),
        )
    )
    factory = RecordingFactory()
    service = MeshingService(database, FakeMeshingAdapter(), session_adapter_factory=factory)
    SettingsRepository(database).update({"meshing_max_parallel_sessions": "2"})
    connect_started = threading.Event()
    release_connect = threading.Event()

    class FailConnectAdapter(FakeMeshingAdapter):
        def connect(self, config: FluentConnectionConfig) -> FluentStatus:
            connect_started.set()
            assert release_connect.wait(timeout=10)
            raise RuntimeError("simulated Fluent launch failure")

    def create_fail_first(
        *, session_id: str, run_dir: Path | None = None
    ) -> MeshingWorkflowAdapter:
        adapter: FakeMeshingAdapter = (
            FailConnectAdapter() if not factory.created else FakeMeshingAdapter()
        )
        adapter.session_label = session_id  # type: ignore[attr-defined]
        factory.created.append(adapter)
        return adapter

    factory.create = create_fail_first  # type: ignore[method-assign]
    try:
        failing = _start(service, automation.id, model.id)
        assert connect_started.wait(timeout=10)
        healthy = _start(service, automation.id, model.id)
        _wait_phase(service, healthy.session_id, "surface_ready")

        # While the first connect is still blocked, its session occupies a
        # slot but the healthy session already runs in the second lane.
        assert service.live.get(healthy.session_id).phase == "surface_ready"

        release_connect.set()
        failed = _wait_for(service, failing.session_id, lambda snap: snap.status == "failed")
        assert "simulated Fluent launch failure" in failed.message

        # The healthy session is untouched and keeps its Fluent session.
        snapshot = service.live.get(healthy.session_id)
        assert snapshot.phase == "surface_ready"
        assert snapshot.status == "waiting"
    finally:
        release_connect.set()
        service.shutdown()


def test_attach_sessions_to_same_endpoint_stay_serial(tmp_path: Path) -> None:
    database, service, _, automation_id, model_id = _setup(tmp_path)
    SettingsRepository(database).update({"meshing_max_parallel_sessions": "3"})
    config = FluentConnectionConfig(mode="attach", host="127.0.0.1", port=63001)
    try:
        first = service.start_live_session(
            MeshingLiveSessionStart(
                automation_id=automation_id, model_ids=[model_id], connection=config
            )
        )
        second = service.start_live_session(
            MeshingLiveSessionStart(
                automation_id=automation_id, model_ids=[model_id], connection=config
            )
        )
        _wait_for(service, first.session_id, lambda snap: snap.status in _ACTIVE)
        assert service.live.get(second.session_id).status == "queued"

        # A different endpoint is independent and starts immediately.
        other = service.start_live_session(
            MeshingLiveSessionStart(
                automation_id=automation_id,
                model_ids=[model_id],
                connection=config.model_copy(update={"port": 63002}),
            )
        )
        _wait_for(service, other.session_id, lambda snap: snap.status in _ACTIVE)
    finally:
        service.shutdown()


def test_processor_budget_keeps_sessions_queued(tmp_path: Path) -> None:
    database, service, _, automation_id, model_id = _setup(tmp_path)
    SettingsRepository(database).update(
        {"meshing_max_parallel_sessions": "3", "meshing_processor_budget": "1"}
    )
    try:
        first = _start(service, automation_id, model_id, processor_count=1)
        second = _start(service, automation_id, model_id, processor_count=1)
        _wait_for(service, first.session_id, lambda snap: snap.status in _ACTIVE)
        # A slot is free but the core budget is exhausted.
        assert service.live.get(second.session_id).status == "queued"
        service.stop_live_session(first.session_id)
        _wait_for(service, second.session_id, lambda snap: snap.status in _ACTIVE)
    finally:
        service.shutdown()


def test_task_run_directories_and_model_snapshot(tmp_path: Path) -> None:
    database, service, _, automation_id, model_id = _setup(tmp_path)
    try:
        started = _start(service, automation_id, model_id)
        task_id = started.task_id
        task_dir = database.path.parent / "meshing-results" / task_id
        runs = list(task_dir.iterdir())
        assert len(runs) == 1
        for name in ("input", "fluent-work", "mesh", "logs", "report"):
            assert (runs[0] / name).is_dir(), name

        with database.connect() as connection:
            row = connection.execute(
                "SELECT model_snapshot_json FROM meshing_tasks WHERE id=?", (task_id,)
            ).fetchone()
        models = json.loads(row["model_snapshot_json"])
        assert models[0]["resolved_path"].endswith("part.scdocx")
        assert models[0]["file_size"] == len(b"test geometry")
        assert models[0]["modified_at"] is not None
    finally:
        service.shutdown()


def test_restart_marks_queued_and_started_tasks_differently(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    tasks = MeshingTaskRepository(database)
    tasks.create("queued-task", None, "A", 1, {}, [], "session-queued")
    tasks.create("running-task", None, "B", 1, {}, [], "session-running")
    with database.connect() as connection:
        connection.execute(
            "UPDATE meshing_tasks SET status='waiting_surface', phase='surface_ready' "
            "WHERE id='running-task'"
        )
    # A new service (app restart) marks leftovers as interrupted.
    MeshingService(database, FakeMeshingAdapter())

    with database.connect() as connection:
        rows = {
            row["id"]: row
            for row in connection.execute("SELECT id, message FROM meshing_tasks").fetchall()
        }
    assert "重新提交" in rows["queued-task"]["message"]
    assert "尚未结束" in rows["running-task"]["message"]

    history_queued = tasks.history("queued-task")
    history_running = tasks.history("running-task")
    assert any(e.event_type == "queue_discarded" for e in history_queued.events)
    assert any(e.event_type == "execution_interrupted" for e in history_running.events)
