"""Direct checks for reusable Meshing rules, native steps, and result archiving."""

import json
from concurrent.futures import Future
from threading import Event
from pathlib import Path
from time import monotonic

import pytest

from app.database import Database
from app.domain import (
    FluentConnectionConfig,
    MeshingArchiveCreate,
    MeshingAutomationCreate,
    MeshingLiveSessionStart,
    MeshingLiveStepRequest,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingTaskExecutionReport,
    ModelCreate,
)
from app.meshing.fake import FakeMeshingAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_plan import watertight_steps
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository
from app.services.meshing_live import MeshingLiveManager
from app.services.meshing_service import MeshingAdapterBusyError, MeshingService


def test_new_template_rejects_geometry_path_and_old_template_remains_readable() -> None:
    old = MeshingPresetDocument(
        schema_version=1,
        workflow_type="watertight",
        items=[MeshingPresetItem(task_path=["import_geometry"], argument_path=["file_name"], value="A.scdocx")],
    )
    assert old.items[0].value_mode == "fixed"
    with pytest.raises(ValueError, match="Geometry file paths"):
        MeshingPresetDocument.model_validate(old.model_dump() | {"schema_version": 2})


def test_boundary_mapping_pairs_survive_schema_validation_and_database_reload(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    items = [
        MeshingPresetItem(
            task_path=["update_boundaries"],
            argument_path=["selection_type"],
            value="label",
        ),
        MeshingPresetItem(
            task_path=["update_boundaries"],
            argument_path=["boundary_label_list"],
            value=["inlet-cold", "inlet-hot", "outlet", "wall-big", "wall-small"],
        ),
        MeshingPresetItem(
            task_path=["update_boundaries"],
            argument_path=["boundary_label_type_list"],
            value=["velocity-inlet", "velocity-inlet", "pressure-outlet", "wall", "wall"],
        ),
    ]
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=items,
    )
    validation = MESHING_SCHEMA_INDEX.validate(preset)
    assert validation.valid, validation.errors

    repository = MeshingAutomationRepository(database)
    saved = repository.create(MeshingAutomationCreate(name="Boundary mapping roundtrip", preset=preset))
    reopened = repository.get(saved.id)
    assert reopened.preset.items == items


def test_live_step_write_exception_marks_session_failed_instead_of_running(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "write-error.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Write Error", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Live write failure",
            preset=MeshingPresetDocument(
                schema_version=2,
                workflow_type="watertight",
                items=[MeshingPresetItem(
                    task_path=["describe_geometry"], argument_path=["setup_type"],
                    value="The geometry consists of only fluid regions with no voids",
                )],
            ),
        )
    )
    adapter = FakeMeshingAdapter()
    live = MeshingLiveManager(database, adapter)
    started = live.start(
        automation.id, [model.id], FluentConnectionConfig(mode="launch"), False
    )
    step_index = next(
        index for index, step in enumerate(started.steps)
        if step.task_path == ["update_boundaries"]
    )
    adapter.write_arguments = lambda _request: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("Fluent write channel closed")
    )

    report = live.write_step(
        started.session_id,
        step_index,
        [MeshingPresetItem(
            task_path=["update_boundaries"],
            argument_path=["selection_type"],
            value="label",
        )],
    )

    assert report.status == "failed"
    assert report.snapshot.status == "failed"
    assert report.snapshot.steps[step_index].status == "failed"
    assert "Fluent write channel closed" in report.message


def test_enter_live_step_timeout_marks_session_failed(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "enter-timeout.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Enter Timeout", file_path=str(target)))
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["describe_geometry"], argument_path=["setup_type"],
                value="The geometry consists of only fluid regions with no voids",
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "min_size"], value=0.001,
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "max_size"], value=0.02,
            ),
        ],
    )
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Live enter timeout", preset=preset)
    )
    adapter = FakeMeshingAdapter()
    service = MeshingService(database, adapter, live_phase_timeout_seconds=60)
    started = service.live.start(
        automation.id, [model.id], FluentConnectionConfig(mode="launch"), False
    )
    service.live.begin(started.session_id)
    assert service.live.get(started.session_id).phase == "surface_ready"
    boundary_index = next(
        index for index, step in enumerate(started.steps)
        if step.task_path == ["update_boundaries"]
    )
    call_entered = Event()
    release_call = Event()

    def block_read(_request: object) -> object:
        call_entered.set()
        release_call.wait(timeout=5)
        raise RuntimeError("test read resumed after timeout")

    adapter.read_arguments = block_read  # type: ignore[method-assign]
    run = service._run

    def short_timeout(operation: object, **kwargs: object) -> object:
        return run(operation, timeout_seconds=0.1, **kwargs)  # type: ignore[arg-type]

    service._run = short_timeout  # type: ignore[method-assign]
    try:
        with pytest.raises(MeshingAdapterBusyError, match="0.1 秒没有返回"):
            service.enter_live_step(
                started.session_id,
                MeshingLiveStepRequest(step_index=boundary_index),
            )
        assert call_entered.is_set()
        snapshot = service.live.get(started.session_id)
        assert snapshot.status == "failed"
        assert snapshot.steps[boundary_index].status == "failed"
        assert "连续 0.1 秒没有返回" in snapshot.message
    finally:
        release_call.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


@pytest.mark.parametrize(
    ("operation", "model_count"),
    [("retry_prepare", 1), ("next_model", 2), ("retry_model", 1)],
)
def test_live_retry_timeouts_mark_the_session_failed(
    tmp_path: Path,
    operation: str,
    model_count: int,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    models = []
    for index in range(model_count):
        target = tmp_path / f"retry-timeout-{index}.scdocx"
        target.write_bytes(b"test geometry")
        models.append(
            ModelRepository(database).create(
                ModelCreate(name=f"Retry Timeout {index}", file_path=str(target))
            )
        )
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["describe_geometry"], argument_path=["setup_type"],
                value="The geometry consists of only fluid regions with no voids",
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "min_size"], value=0.001,
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "max_size"], value=0.02,
            ),
        ],
    )
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name=f"Live {operation} timeout", preset=preset)
    )
    adapter = FakeMeshingAdapter()
    service = MeshingService(database, adapter, live_phase_timeout_seconds=60)
    started = service.live.start(
        automation.id,
        [model.id for model in models],
        FluentConnectionConfig(mode="launch"),
        False,
    )
    service.live.begin(started.session_id)
    assert service.live.get(started.session_id).phase == "surface_ready"
    call_entered = Event()
    release_call = Event()

    def block_adapter_call(*_args: object, **_kwargs: object) -> object:
        call_entered.set()
        release_call.wait(timeout=5)
        raise RuntimeError("test adapter resumed after timeout")

    if operation == "retry_prepare":
        service.live.retry_prepare = block_adapter_call  # type: ignore[method-assign]
        retry = service.retry_live_preparation
    else:
        adapter.reset_workflow = block_adapter_call  # type: ignore[method-assign]
        retry = service.next_live_model if operation == "next_model" else service.retry_live_model
    run = service._run

    def short_timeout(operation_call: object, **kwargs: object) -> object:
        return run(operation_call, timeout_seconds=0.1, **kwargs)  # type: ignore[arg-type]

    service._run = short_timeout  # type: ignore[method-assign]
    try:
        with pytest.raises(MeshingAdapterBusyError, match="0.1 秒没有返回"):
            retry(started.session_id)
        assert call_entered.is_set()
        snapshot = service.live.get(started.session_id)
        assert snapshot.status == "failed"
        assert snapshot.phase == "failed"
        assert "连续 0.1 秒没有返回" in snapshot.message
    finally:
        release_call.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_two_checkpoints_generate_only_after_confirmation_and_archive_mesh(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "b-middle.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="B", file_path=str(target)))
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["describe_geometry"],
                argument_path=["setup_type"],
                value="The geometry consists of only fluid regions with no voids",
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "min_size"],
                value=None,
                value_mode="at_use",
            ),
            MeshingPresetItem(
                task_path=["create_surface_mesh"],
                argument_path=["cfd_surface_mesh_controls", "max_size"],
                value=0.02,
            ),
        ],
    )
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Venturi", preset=preset)
    )
    adapter = FakeMeshingAdapter()
    live = MeshingLiveManager(database, adapter)
    started = live.start(
        automation.id, [model.id], FluentConnectionConfig(mode="launch"), False
    )
    live.begin(started.session_id)
    assert adapter.applied_presets[0][1] == str(target)
    assert live.get(started.session_id).models[0].status == "ready"
    assert live.get(started.session_id).phase == "failed"

    # A legacy at-use field must be supplied before the surface checkpoint can pass.
    surface_index = next(
        index for index, step in enumerate(live.get(started.session_id).steps)
        if step.task_path == ["create_surface_mesh"]
    )
    live.write_step(started.session_id, surface_index, [MeshingPresetItem(
        task_path=["create_surface_mesh"],
        argument_path=["cfd_surface_mesh_controls", "min_size"],
        value=0.001,
    )])
    assert live.retry_prepare(started.session_id).phase == "surface_ready"
    assert adapter.executed_tasks == []

    key_min = (("create_surface_mesh",), ("cfd_surface_mesh_controls", "min_size"), None)
    key_max = (("create_surface_mesh",), ("cfd_surface_mesh_controls", "max_size"), None)
    assert adapter.values[key_min] == 0.001
    assert adapter.values[key_max] == 0.02
    assert live.get(started.session_id).steps[surface_index].preset_status == "applied"

    adapter.values[key_max] = 0.04
    live.native_task_changed(started.session_id, "Add Local Sizing")
    live.native_task_changed(started.session_id, "Generate the Surface Mesh")
    assert adapter.values[key_max] == 0.04
    assert adapter.executed_tasks == []
    live.execute_step(started.session_id, surface_index)
    assert adapter.executed_tasks[0][1] == ("create_surface_mesh",)
    assert live.get(started.session_id).phase == "volume_ready"
    volume_index = next(
        index for index, step in enumerate(live.get(started.session_id).steps)
        if step.task_path == ["create_volume_mesh"]
    )
    live.execute_step(started.session_id, volume_index)
    assert adapter.executed_tasks[-1][1] == ("create_volume_mesh",)

    mesh = tmp_path / "b-middle.msh.h5"
    mesh.write_bytes(b"test mesh")
    archived = live.archive_result(
        started.session_id,
        MeshingArchiveCreate(mesh_path=str(mesh), modeling_notes="收缩段尺寸手工调整。"),
    )
    assert Path(archived.mesh_path).read_bytes() == b"test mesh"
    document = json.loads(Path(archived.record_json_path).read_text(encoding="utf-8"))
    assert document["model_path"] == str(target)
    assert document["modeling_notes"] == "收缩段尺寸手工调整。"
    assert any(row["final_value"] == 0.04 for row in document["differences"])
    assert Path(archived.record_markdown_path).is_file()


def test_native_surface_mesh_completion_resumes_downstream_preparation_once(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "A-compact.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="A-compact", file_path=str(target)))
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["describe_geometry"],
                argument_path=["setup_type"],
                value="The geometry consists of only fluid regions with no voids",
            ),
            MeshingPresetItem(
                task_path=["update_boundaries"],
                argument_path=["selection_type"],
                value="label",
            ),
            MeshingPresetItem(
                task_path=["create_volume_mesh"],
                argument_path=["volume_fill"],
                value="poly-hexcore",
            ),
        ],
    )
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Native surface continuation", preset=preset)
    )
    adapter = FakeMeshingAdapter()
    live = MeshingLiveManager(database, adapter)
    started = live.start(
        automation.id, [model.id], FluentConnectionConfig(mode="launch"), False
    )
    live.begin(started.session_id)
    surface_index = next(
        index for index, step in enumerate(live.get(started.session_id).steps)
        if step.task_path == ["create_surface_mesh"]
    )
    describe_index = next(
        index for index, step in enumerate(live.get(started.session_id).steps)
        if step.task_path == ["describe_geometry"]
    )

    live.native_task_changed(started.session_id, "Generate the Surface Mesh")
    assert live.get(started.session_id).phase == "surface_ready"
    assert adapter.executed_tasks == []

    session = live._require(started.session_id)
    live._ingest_transcript(
        session,
        "Surface Meshing of A-compact complete in 0.03 minutes, "
        "with a maximum skewness of 0.43.",
    )
    assert live.get(started.session_id).phase == "surface_ready"
    assert adapter.executed_tasks == []

    live.native_task_changed(started.session_id, "Describe Geometry")
    snapshot = live.get(started.session_id)
    assert snapshot.phase == "volume_ready"
    assert snapshot.current_step_index == len(snapshot.steps) - 1
    assert snapshot.steps[surface_index].status == "completed"
    assert snapshot.steps[describe_index].status == "completed"
    assert adapter.executed_tasks == [
        ("watertight", ("describe_geometry",)),
        ("watertight", ("update_boundaries",)),
    ]

    live.native_task_changed(started.session_id, "Describe Geometry")
    assert adapter.executed_tasks == [
        ("watertight", ("describe_geometry",)),
        ("watertight", ("update_boundaries",)),
    ]


def test_reference_inspection_uses_isolated_adapter(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    reference = tmp_path / "A-compact.scdocx"
    reference.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="A", file_path=str(reference)))
    running_adapter = FakeMeshingAdapter()
    service = MeshingService(database, running_adapter)
    report = service.inspect_reference_model(model.id)
    assert "inlet" in report.labels
    assert running_adapter.connect_calls == 0


def test_geometry_type_controls_middle_tasks() -> None:
    def steps(geometry: str) -> list[str]:
        return watertight_steps([MeshingPresetItem(
            task_path=["describe_geometry"], argument_path=["setup_type"], value=geometry,
        )])

    solid = steps("The geometry consists of only solid regions")
    fluid = steps("The geometry consists of only fluid regions with no voids")
    mixed = steps("The geometry consists of both fluid and solid regions and/or voids")
    assert "enclose_fluid_regions" in solid and "create_regions" in solid
    assert "update_boundaries" in fluid and "create_regions" not in fluid
    assert {"enclose_fluid_regions", "update_boundaries", "create_regions"}.issubset(mixed)


def test_import_applies_local_sizing_before_surface_generation(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[
        MeshingPresetItem(task_path=["add_local_sizing"], argument_path=["boi_size"],
                          value=0.01, compound_child_name="wall-size"),
    ])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Local sizing", preset=preset)
    )
    adapter = FakeMeshingAdapter()
    live = MeshingLiveManager(database, adapter)
    started = live.start(automation.id, [model.id], FluentConnectionConfig(mode="launch"), False)
    live.begin(started.session_id)
    snapshot = live.get(started.session_id)
    assert snapshot.phase == "surface_ready"
    assert snapshot.status == "waiting"
    assert snapshot.phase_elapsed_ms is None
    assert snapshot.current_step_index == 2
    assert snapshot.steps[0].duration_ms is not None
    assert snapshot.steps[1].status == "completed"
    assert snapshot.steps[1].preset_status == "applied"
    assert snapshot.steps[2].status == "active"
    assert snapshot.steps[2].preset_status == "applied"
    assert adapter.executed_tasks == [("watertight", ("add_local_sizing",))]
    assert adapter.values[(("add_local_sizing",), ("boi_size",), "wall-size")] == 0.01


def test_local_sizing_failure_is_visible_and_stops_before_surface_generation(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[
        MeshingPresetItem(task_path=["add_local_sizing"], argument_path=["boi_size"],
                          value=0.01, compound_child_name="wall-size"),
    ])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Local sizing", preset=preset)
    )

    class FailingLocalSizingAdapter(FakeMeshingAdapter):
        def execute_task(
            self, workflow_type: str, task_path: list[str]
        ) -> MeshingTaskExecutionReport:
            if task_path == ["add_local_sizing"]:
                raise RuntimeError("zone not found")
            return super().execute_task(workflow_type, task_path)

    adapter = FailingLocalSizingAdapter()
    live = MeshingLiveManager(database, adapter)
    started = live.start(automation.id, [model.id], FluentConnectionConfig(mode="launch"), False)
    live.begin(started.session_id)

    snapshot = live.get(started.session_id)
    assert snapshot.status == "failed"
    assert snapshot.phase == "failed"
    assert snapshot.models[0].status == "ready"
    assert "zone not found" in (snapshot.models[0].error or "")
    local_sizing = next(step for step in snapshot.steps if step.task_path == ["add_local_sizing"])
    assert local_sizing.status == "failed"
    assert adapter.executed_tasks == []
    assert not any("局部尺寸已执行，面网格参数已写入并回读" in log.message for log in snapshot.logs)


def test_unhandled_background_start_failure_updates_live_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Background failure", preset=preset)
    )
    service = MeshingService(database, FakeMeshingAdapter())
    entered = Event()
    release = Event()

    def fail_begin(*_args, **_kwargs) -> None:
        entered.set()
        release.wait(timeout=3)
        raise RuntimeError("background worker failed")

    service.live.begin = fail_begin  # type: ignore[method-assign]
    started = service.start_live_session(MeshingLiveSessionStart(
        automation_id=automation.id,
        model_ids=[model.id],
        connection=FluentConnectionConfig(mode="launch"),
    ))
    try:
        assert entered.wait(timeout=2)
        future = service._live_start_futures[started.session_id]
        release.set()
        with pytest.raises(RuntimeError, match="background worker failed"):
            future.result(timeout=3)
        snapshot = service.live.get(started.session_id)
        assert snapshot.status == "failed"
        assert snapshot.phase == "failed"
        assert snapshot.models[0].status == "failed"
        assert "background worker failed" in (snapshot.models[0].error or "")
    finally:
        release.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_slow_local_sizing_warns_and_stop_does_not_wait_for_fluent(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[
        MeshingPresetItem(task_path=["add_local_sizing"], argument_path=["boi_size"],
                          value=0.01, compound_child_name="wall-size"),
    ])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Timeout", preset=preset)
    )

    entered = Event()
    release = Event()

    class BlockingSizingAdapter(FakeMeshingAdapter):
        def execute_task(
            self, workflow_type: str, task_path: list[str]
        ) -> MeshingTaskExecutionReport:
            if task_path == ["add_local_sizing"]:
                entered.set()
                release.wait(timeout=5)
            return super().execute_task(workflow_type, task_path)

    adapter = BlockingSizingAdapter()
    service = MeshingService(database, adapter, live_phase_timeout_seconds=0.5)
    started = service.start_live_session(MeshingLiveSessionStart(
        automation_id=automation.id,
        model_ids=[model.id],
        connection=FluentConnectionConfig(mode="launch"),
    ))
    start_future = service._live_start_futures[started.session_id]
    try:
        assert entered.wait(timeout=2)
        deadline = monotonic() + 2
        snapshot = service.get_live_session(started.session_id)
        while "继续等待当前请求" not in snapshot.message and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.get_live_session(started.session_id)

        assert snapshot.status == "running"
        assert snapshot.phase == "executing_local_sizing"
        assert snapshot.models[0].status == "ready"
        assert "局部尺寸" in snapshot.message
        assert "没有返回" in snapshot.message
        assert "继续等待当前请求" in snapshot.message
        assert adapter.executed_tasks == []

        stopped_at = monotonic()
        stopped = service.stop_live_session(started.session_id)
        assert monotonic() - stopped_at < 0.3
        assert stopped.status == "stopped"
        assert adapter.connected
    finally:
        release.set()
        start_future.result(timeout=3)
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_slow_local_sizing_continues_automatically_after_fluent_returns(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[
        MeshingPresetItem(task_path=["add_local_sizing"], argument_path=["boi_size"],
                          value=0.01, compound_child_name="wall-size"),
    ])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Slow local sizing", preset=preset)
    )

    entered = Event()
    release = Event()

    class SlowSizingAdapter(FakeMeshingAdapter):
        def execute_task(
            self, workflow_type: str, task_path: list[str]
        ) -> MeshingTaskExecutionReport:
            if task_path == ["add_local_sizing"]:
                entered.set()
                release.wait(timeout=5)
            return super().execute_task(workflow_type, task_path)

    adapter = SlowSizingAdapter()
    service = MeshingService(database, adapter, live_phase_timeout_seconds=0.5)
    started = service.start_live_session(MeshingLiveSessionStart(
        automation_id=automation.id,
        model_ids=[model.id],
        connection=FluentConnectionConfig(mode="launch"),
    ))
    start_future = service._live_start_futures[started.session_id]
    try:
        assert entered.wait(timeout=2)
        deadline = monotonic() + 2
        snapshot = service.get_live_session(started.session_id)
        while "继续等待当前请求" not in snapshot.message and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.get_live_session(started.session_id)

        assert snapshot.status == "running"
        assert snapshot.phase == "executing_local_sizing"
        assert "继续等待当前请求" in snapshot.message
        assert adapter.executed_tasks == []

        release.set()
        start_future.result(timeout=3)
        snapshot = service.live.get(started.session_id)
        assert snapshot.status == "waiting"
        assert snapshot.phase == "surface_ready"
        assert snapshot.models[0].status == "ready"
        local_sizing = next(
            step for step in snapshot.steps if step.task_path == ["add_local_sizing"]
        )
        surface_mesh = next(
            step for step in snapshot.steps if step.task_path == ["create_surface_mesh"]
        )
        assert local_sizing.status == "completed"
        assert surface_mesh.status == "active"
        assert adapter.executed_tasks == [("watertight", ("add_local_sizing",))]
    finally:
        release.set()
        service.stop_live_session(started.session_id)
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_hard_timeout_stops_live_preparation_and_shows_recoverable_state(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "local.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Local", file_path=str(target)))
    preset = MeshingPresetDocument(schema_version=2, workflow_type="watertight", items=[
        MeshingPresetItem(task_path=["add_local_sizing"], argument_path=["boi_size"],
                          value=0.01, compound_child_name="wall-size"),
    ])
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(name="Hard timeout", preset=preset)
    )
    entered = Event()
    release = Event()

    class BlockingSizingAdapter(FakeMeshingAdapter):
        def execute_task(
            self, workflow_type: str, task_path: list[str]
        ) -> MeshingTaskExecutionReport:
            if task_path == ["add_local_sizing"]:
                entered.set()
                release.wait(timeout=5)
            return super().execute_task(workflow_type, task_path)

    adapter = BlockingSizingAdapter()
    service = MeshingService(
        database,
        adapter,
        live_phase_timeout_seconds=0.05,
        live_hard_timeout_seconds=0.15,
    )
    started = service.start_live_session(MeshingLiveSessionStart(
        automation_id=automation.id,
        model_ids=[model.id],
        connection=FluentConnectionConfig(mode="launch"),
    ))
    start_future = service._live_start_futures[started.session_id]
    try:
        assert entered.wait(timeout=2)
        deadline = monotonic() + 2
        snapshot = service.get_live_session(started.session_id)
        while snapshot.phase != "failed" and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.get_live_session(started.session_id)

        assert snapshot.status == "failed"
        assert snapshot.phase == "failed"
        assert "平台已停止后续自动步骤" in snapshot.message
        assert adapter.executed_tasks == []
    finally:
        release.set()
        start_future.result(timeout=3)
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_unbounded_operation_uses_hard_timeout_and_recovers_after_return(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    service = MeshingService(
        database,
        FakeMeshingAdapter(),
        live_phase_timeout_seconds=0.05,
        live_hard_timeout_seconds=0.15,
    )
    entered = Event()
    release = Event()

    def blocked_operation() -> None:
        entered.set()
        release.wait(timeout=5)

    try:
        with pytest.raises(MeshingAdapterBusyError, match="0.15 秒没有返回"):
            service._run(
                blocked_operation,
                timeout_seconds=None,
                operation_name="测试工作流步骤",
            )
        assert entered.is_set()
        assert service._adapter_unresponsive

        release.set()
        deadline = monotonic() + 2
        while service._adapter_unresponsive and monotonic() < deadline:
            Event().wait(0.02)

        assert not service._adapter_unresponsive
        assert service._run(lambda: "可重试") == "可重试"
    finally:
        release.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


def _start_callback_test_session(tmp_path: Path) -> tuple[MeshingService, FakeMeshingAdapter, str]:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "callback.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Callback", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Native task callback",
            preset=MeshingPresetDocument(
                schema_version=2,
                workflow_type="watertight",
                items=[
                    MeshingPresetItem(
                        task_path=["describe_geometry"], argument_path=["setup_type"],
                        value="The geometry consists of only fluid regions with no voids",
                    ),
                    MeshingPresetItem(
                        task_path=["create_surface_mesh"],
                        argument_path=["cfd_surface_mesh_controls", "min_size"], value=0.001,
                    ),
                    MeshingPresetItem(
                        task_path=["create_surface_mesh"],
                        argument_path=["cfd_surface_mesh_controls", "max_size"], value=0.02,
                    ),
                ],
            ),
        )
    )
    adapter = FakeMeshingAdapter()
    service = MeshingService(database, adapter)
    started = service.start_live_session(
        MeshingLiveSessionStart(
            automation_id=automation.id,
            model_ids=[model.id],
            connection=FluentConnectionConfig(mode="launch"),
        )
    )
    service._live_start_futures[started.session_id].result(timeout=3)
    assert service.live.get(started.session_id).phase == "surface_ready"
    return service, adapter, started.session_id


def test_native_task_callback_exceptions_are_observed_and_reported(tmp_path: Path) -> None:
    service, adapter, session_id = _start_callback_test_session(tmp_path)
    callback = adapter.current_task_callback
    assert callback is not None

    def fail_native_change(_session_id: str, _task_name: str) -> None:
        raise RuntimeError("native task transition failed")

    service.live.native_task_changed = fail_native_change  # type: ignore[method-assign]
    try:
        callback("Generate the Surface Mesh")
        deadline = monotonic() + 3
        snapshot = service.live.get(session_id)
        while snapshot.status != "failed" and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.live.get(session_id)

        assert snapshot.status == "failed"
        assert snapshot.phase == "failed"
        assert "native task transition failed" in snapshot.message
        assert any(log.level == "error" for log in snapshot.logs)
    finally:
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_pending_native_task_callback_keeps_stop_responsive(tmp_path: Path) -> None:
    service, adapter, session_id = _start_callback_test_session(tmp_path)
    callback = adapter.current_task_callback
    assert callback is not None
    callback_entered = Event()
    release_callback = Event()

    def block_native_change(_session_id: str, _task_name: str) -> None:
        callback_entered.set()
        release_callback.wait(timeout=5)

    service.live.native_task_changed = block_native_change  # type: ignore[method-assign]
    try:
        callback("Generate the Surface Mesh")
        assert callback_entered.wait(timeout=2)
        stopped_at = monotonic()
        stopped = service.stop_live_session(session_id)
        assert monotonic() - stopped_at < 0.3
        assert stopped.status == "stopped"
    finally:
        release_callback.set()
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_native_task_poll_errors_are_visible_and_clear_after_recovery(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "poll.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Poll", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Native poll recovery",
            preset=MeshingPresetDocument(
                schema_version=2, workflow_type="watertight", items=[]
            ),
        )
    )
    adapter = FakeMeshingAdapter()
    service = MeshingService(database, adapter)
    started = service.start_live_session(
        MeshingLiveSessionStart(
            automation_id=automation.id,
            model_ids=[model.id],
            connection=FluentConnectionConfig(mode="launch"),
        )
    )
    start_future = service._live_start_futures[started.session_id]
    start_future.result(timeout=3)
    failure_entered = Event()

    def fail_native_poll() -> str | None:
        failure_entered.set()
        raise RuntimeError("task tree is unavailable")

    adapter.read_current_task = fail_native_poll  # type: ignore[method-assign]
    try:
        deadline = monotonic() + 3
        while not failure_entered.is_set() and monotonic() < deadline:
            service.get_live_session(started.session_id)
            Event().wait(0.02)
        assert failure_entered.is_set()

        deadline = monotonic() + 3
        snapshot = service.live.get(started.session_id)
        while snapshot.native_task_poll_error is None and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.live.get(started.session_id)
        assert snapshot.status == "waiting"
        assert "task tree is unavailable" in (snapshot.native_task_poll_error or "")
        assert any(log.level == "warning" for log in snapshot.logs)

        adapter.read_current_task = lambda: None  # type: ignore[method-assign]
        service.get_live_session(started.session_id)
        deadline = monotonic() + 3
        snapshot = service.live.get(started.session_id)
        while snapshot.native_task_poll_error is not None and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.live.get(started.session_id)
        assert snapshot.native_task_poll_error is None
        assert any("自动检测已恢复" in log.message for log in snapshot.logs)
    finally:
        service._executor.shutdown(wait=True, cancel_futures=True)


def test_hung_native_task_poll_is_reported_and_stop_remains_responsive(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "app.db")
    database.initialize()
    target = tmp_path / "poll.scdocx"
    target.write_bytes(b"test geometry")
    model = ModelRepository(database).create(ModelCreate(name="Poll", file_path=str(target)))
    automation = MeshingAutomationRepository(database).create(
        MeshingAutomationCreate(
            name="Native poll timeout",
            preset=MeshingPresetDocument(
                schema_version=2, workflow_type="watertight", items=[]
            ),
        )
    )
    adapter = FakeMeshingAdapter()
    entered = Event()
    release = Event()

    def block_native_poll() -> str | None:
        entered.set()
        release.wait(timeout=5)
        return None

    adapter.read_current_task = block_native_poll  # type: ignore[method-assign]
    service = MeshingService(database, adapter, live_phase_timeout_seconds=0.2)
    started = service.start_live_session(
        MeshingLiveSessionStart(
            automation_id=automation.id,
            model_ids=[model.id],
            connection=FluentConnectionConfig(mode="launch"),
        )
    )
    start_future = service._live_start_futures[started.session_id]
    start_future.result(timeout=3)
    poll_future: Future[None] | None = None
    try:
        deadline = monotonic() + 3
        while not entered.is_set() and monotonic() < deadline:
            service.get_live_session(started.session_id)
            poll_future = service._native_poll.get(started.session_id)
            Event().wait(0.02)
        assert entered.is_set()
        assert poll_future is not None

        deadline = monotonic() + 3
        snapshot = service.live.get(started.session_id)
        while snapshot.native_task_poll_error is None and monotonic() < deadline:
            Event().wait(0.02)
            snapshot = service.live.get(started.session_id)
        assert "0.2 秒没有返回" in (snapshot.native_task_poll_error or "")
        assert service._adapter_unresponsive is True

        stopped_at = monotonic()
        stopped = service.stop_live_session(started.session_id)
        assert monotonic() - stopped_at < 0.3
        assert stopped.status == "stopped"
    finally:
        release.set()
        if poll_future is not None:
            poll_future.result(timeout=3)
        service._executor.shutdown(wait=True, cancel_futures=True)
