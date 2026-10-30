"""Regression checks for minimizing synchronous PyFluent state reads."""

from __future__ import annotations

import re
import sys
from collections import UserList
from types import ModuleType
from typing import Any

from app.domain import (
    MeshingArgumentReference,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingReadRequest,
    MeshingWriteRequest,
)


def _import_adapter(monkeypatch: Any) -> Any:
    workflow_module = ModuleType("ansys.fluent.core.workflow")
    workflow_module.camel_to_snake_case = lambda value: re.sub(
        r"(?<!^)(?=[A-Z])", "_", str(value)
    ).lower()
    core_module = ModuleType("ansys.fluent.core")
    core_module.__path__ = []  # type: ignore[attr-defined]
    fluent_module = ModuleType("ansys.fluent")
    fluent_module.__path__ = []  # type: ignore[attr-defined]
    ansys_module = ModuleType("ansys")
    ansys_module.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansys", ansys_module)
    monkeypatch.setitem(sys.modules, "ansys.fluent", fluent_module)
    monkeypatch.setitem(sys.modules, "ansys.fluent.core", core_module)
    monkeypatch.setitem(sys.modules, "ansys.fluent.core.workflow", workflow_module)
    from app.meshing import pyfluent_adapter

    return pyfluent_adapter


class CountingArguments:
    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.remote_state = state
        self.mirror_writes_to_remote = True
        self.read_count = 0
        self.remote_read_count = 0
        self.batch_state_calls: list[dict[str, Any]] = []

    def get_state(self) -> dict[str, Any]:
        self.read_count += 1
        return self.state

    def get_remote_state(self) -> dict[str, Any]:
        self.remote_read_count += 1
        return self.remote_state

    def set_state(self, state: dict[str, Any]) -> None:
        self.batch_state_calls.append(dict(state))
        self.state.update(state)
        if self.remote_state is not self.state and self.mirror_writes_to_remote:
            self.remote_state.update(state)

    def __getattr__(self, name: str) -> Any:
        class StateField:
            def set_state(_self, value: Any) -> None:
                self.state[name] = value

        return StateField()


class FakeTask:
    def __init__(
        self,
        name: str,
        state: dict[str, Any],
        children: list[FakeTask] | None = None,
    ) -> None:
        self.name = name
        self.arguments = CountingArguments(state)
        self._children = children or []

    def python_name(self) -> str:
        return self.name

    def tasks(self) -> list[FakeTask]:
        return self._children


class FakeWorkflow:
    def __init__(self, tasks: list[FakeTask]) -> None:
        self._tasks = tasks

    def tasks(self) -> list[FakeTask]:
        return self._tasks


class ActiveSession:
    def is_active(self) -> bool:
        return True


def test_read_arguments_fetches_state_once_per_task_or_child(monkeypatch: Any) -> None:
    adapter_module = _import_adapter(monkeypatch)
    sizing_child = FakeTask("wall-size", {"boi_size": 0.01, "growth_rate": 1.2})
    sizing = FakeTask("add_local_sizing", {}, [sizing_child])
    surface = FakeTask("create_surface_mesh", {"min_size": 0.001, "max_size": 0.02})
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([sizing, surface])
    adapter._workflow_type = "watertight"

    request = MeshingReadRequest(
        workflow_type="watertight",
        items=[
            MeshingArgumentReference(
                task_path=["add_local_sizing"],
                argument_path=["boi_size"],
                compound_child_name="wall-size",
            ),
            MeshingArgumentReference(
                task_path=["create_surface_mesh"],
                argument_path=["min_size"],
            ),
            MeshingArgumentReference(
                task_path=["add_local_sizing"],
                argument_path=["growth_rate"],
                compound_child_name="wall-size",
            ),
            MeshingArgumentReference(
                task_path=["create_surface_mesh"],
                argument_path=["max_size"],
            ),
        ],
    )

    report = adapter.read_arguments(request)

    assert report.status == "success"
    assert [item.value for item in report.items] == [0.01, 0.001, 1.2, 0.02]
    assert sizing_child.arguments.read_count == 1
    assert surface.arguments.read_count == 1


def test_read_arguments_error_includes_task_and_missing_argument_paths(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)

    class BrokenArguments(CountingArguments):
        def get_state(self) -> dict[str, Any]:
            raise RuntimeError("Fluent RPC channel closed")

    surface = FakeTask("create_surface_mesh", {})
    surface.arguments = BrokenArguments({})
    geometry = FakeTask("describe_geometry", {})
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([surface, geometry])
    adapter._workflow_type = "watertight"

    report = adapter.read_arguments(
        MeshingReadRequest(
            workflow_type="watertight",
            items=[
                MeshingArgumentReference(
                    task_path=["create_surface_mesh"],
                    argument_path=["cfd_surface_mesh_controls", "min_size"],
                ),
                MeshingArgumentReference(
                    task_path=["describe_geometry"],
                    argument_path=["setup", "geometry_type"],
                ),
            ],
        )
    )

    assert report.status == "failed"
    assert report.error is not None
    assert "create_surface_mesh: RuntimeError: Fluent RPC channel closed" in report.error
    assert "describe_geometry.setup.geometry_type" in report.error
    assert [item.error for item in report.items] == [
        "RuntimeError: Fluent RPC channel closed",
        "Argument path was not found.",
    ]


def test_normalize_state_parses_pyfluent_stringified_list_arguments(monkeypatch: Any) -> None:
    adapter_module = _import_adapter(monkeypatch)

    state = adapter_module._normalize_state(
        {
            "BoundaryCurrentList": "['inlet-hot', 'outlet']",
            "BoundaryCurrentTypeList": "['velocity-inlet', 'pressure-outlet']",
            "BoundaryAllowedTypeList": UserList(["wall", "velocity-inlet"]),
            "description": "['keep', 'as', 'text']",
        }
    )

    assert state["boundary_current_list"] == ["inlet-hot", "outlet"]
    assert state["boundary_current_type_list"] == ["velocity-inlet", "pressure-outlet"]
    assert state["boundary_allowed_type_list"] == ["wall", "velocity-inlet"]
    assert state["description"] == "['keep', 'as', 'text']"


def test_name_catalog_is_skipped_when_preset_has_no_selectors(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter_module,
        "_collect_name_catalog",
        lambda _workflow: (_ for _ in ()).throw(AssertionError("unneeded full scan")),
    )
    preset = MeshingPresetDocument(
        schema_version=2,
        workflow_type="watertight",
        items=[
            MeshingPresetItem(
                task_path=["import_geometry"],
                argument_path=["length_unit"],
                value="mm",
            ),
            MeshingPresetItem(
                task_path=["add_local_sizing"],
                argument_path=["boi_size"],
                value=0.01,
                compound_child_name="wall-size",
            ),
        ],
    )

    checks, missing = adapter_module._validate_preset_names(FakeWorkflow([]), preset)

    assert checks == []
    assert missing == []


def test_live_selector_write_verifies_against_fluent_readback(monkeypatch: Any) -> None:
    adapter_module = _import_adapter(monkeypatch)
    monkeypatch.setattr(
        adapter_module,
        "_collect_name_catalog",
        lambda _workflow: (_ for _ in ()).throw(AssertionError("slow global scan")),
    )
    sizing_child = FakeTask("size-big", {"boi_face_label_list": ["wall"]})
    sizing = FakeTask("add_local_sizing", {}, [sizing_child])
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([sizing])
    adapter._workflow_type = "watertight"

    report = adapter.write_arguments(
        MeshingWriteRequest(
            workflow_type="watertight",
            items=[
                MeshingPresetItem(
                    task_path=["add_local_sizing"],
                    argument_path=["boi_face_label_list"],
                    value=["wall"],
                    compound_child_name="size-big",
                )
            ],
            verify=True,
        )
    )

    assert report.status == "success"
    assert report.results[0].success
    assert report.results[0].actual == ["wall"]
    assert sizing_child.arguments.read_count == 1


def test_update_boundaries_writes_old_and_target_boundary_types(monkeypatch: Any) -> None:
    adapter_module = _import_adapter(monkeypatch)
    update_boundaries = FakeTask(
        "update_boundaries",
        {
            "selection_type": "label",
            "boundary_current_list": UserList(["inlet-hot", "inlet-cold"]),
            "boundary_current_type_list": UserList(["velocity-inlet", "velocity-inlet"]),
            "boundary_label_list": ["inlet-hot", "inlet-cold"],
            "boundary_label_type_list": ["velocity-inlet", "velocity-inlet"],
        },
    )
    update_boundaries.arguments.remote_state = {
        **update_boundaries.arguments.state,
        "boundary_current_type_list": ["pressure-outlet", "wall"],
    }
    update_boundaries.arguments.mirror_writes_to_remote = False
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.write_arguments(
        MeshingWriteRequest(
            workflow_type="watertight",
            items=[
                MeshingPresetItem(
                    task_path=["update_boundaries"],
                    argument_path=["selection_type"],
                    value="label",
                ),
                MeshingPresetItem(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_label_list"],
                    value=["inlet-hot", "inlet-cold"],
                ),
                MeshingPresetItem(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_label_type_list"],
                    value=["wall", "wall"],
                ),
            ],
            verify=True,
        )
    )

    assert report.status == "success"
    assert update_boundaries.arguments.state["old_boundary_label_list"] == [
        "inlet-hot",
        "inlet-cold",
    ]
    assert update_boundaries.arguments.state["old_boundary_label_type_list"] == [
        "pressure-outlet",
        "wall",
    ]
    assert update_boundaries.arguments.state["boundary_label_type_list"] == ["wall", "wall"]
    assert len(update_boundaries.arguments.batch_state_calls) == 1
    assert update_boundaries.arguments.batch_state_calls[0]["old_boundary_label_type_list"] == [
        "pressure-outlet",
        "wall",
    ]
    assert update_boundaries.arguments.batch_state_calls[0]["boundary_label_type_list"] == [
        "wall",
        "wall",
    ]
    assert update_boundaries.arguments.read_count == 0
    assert update_boundaries.arguments.remote_read_count == 1
    assert report.verified is False
    assert report.status == "success"
    assert all(result.success for result in report.results)
    assert all("after Update Boundaries executes" in result.message for result in report.results)
    assert update_boundaries.arguments.remote_state["boundary_label_type_list"] == [
        "velocity-inlet",
        "velocity-inlet",
    ]


def test_execute_update_boundaries_reports_submitted_and_live_table_state(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)

    class UpdatingTask(FakeTask):
        def __call__(self) -> bool:
            self.arguments.remote_state = {
                **self.arguments.state,
                "boundary_current_type_list": ["wall", "wall"],
            }
            return True

    update_boundaries = UpdatingTask(
        "update_boundaries",
        {
            "selection_type": "label",
            "boundary_label_list": ["inlet-hot", "inlet-cold"],
            "boundary_label_type_list": ["wall", "wall"],
            "old_boundary_label_list": ["inlet-hot", "inlet-cold"],
            "old_boundary_label_type_list": ["velocity-inlet", "velocity-inlet"],
            "boundary_current_list": ["inlet-hot", "inlet-cold"],
            "boundary_current_type_list": ["velocity-inlet", "velocity-inlet"],
        },
    )
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.execute_task("watertight", ["update_boundaries"])

    assert report.status == "success"
    assert any(
        "boundary_label_type_list': ['wall', 'wall']" in line
        and "old_boundary_label_type_list': ['velocity-inlet', 'velocity-inlet']" in line
        for line in report.output
    )
    assert any(
        "Update Boundaries state after execution (fresh Fluent readback)" in line
        and "boundary_current_type_list': ['wall', 'wall']" in line
        for line in report.output
    )
    assert any(
        "Update Boundaries state after execution (cached)" in line
        and "boundary_current_type_list': ['velocity-inlet', 'velocity-inlet']" in line
        for line in report.output
    )


def test_update_boundaries_read_arguments_bypasses_stale_pyfluent_cache(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)
    update_boundaries = FakeTask(
        "update_boundaries",
        {
            "selection_type": "label",
            "boundary_current_list": ["inlet-hot", "inlet-cold"],
            "boundary_current_type_list": ["velocity-inlet", "velocity-inlet"],
        },
    )
    update_boundaries.arguments.remote_state = {
        "selection_type": "label",
        "boundary_current_list": ["inlet-hot", "inlet-cold"],
        "boundary_current_type_list": ["wall", "wall"],
    }
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.read_arguments(
        MeshingReadRequest(
            workflow_type="watertight",
            items=[
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_type_list"],
                )
            ],
        )
    )

    assert report.status == "success"
    assert report.items[0].value == ["wall", "wall"]
    assert update_boundaries.arguments.read_count == 0
    assert update_boundaries.arguments.remote_read_count == 1


class _RemoteField:
    """Per-argument object exposing PyFluent's dynamic remote reader."""

    def __init__(self, value: Any = None, *, raises: bool = False) -> None:
        self._value = value
        self._raises = raises

    def get_remote_state(self) -> Any:
        if self._raises:
            raise RuntimeError("Dynamic argument is not readable.")
        return self._value

    def set_state(self, value: Any) -> None:
        self._value = value


def _field_aware_task(
    state: dict[str, Any],
    fields: dict[str, _RemoteField],
    remote_state: dict[str, Any] | None = None,
) -> FakeTask:
    class FieldAwareArguments(CountingArguments):
        def __getattr__(self, name: str) -> Any:
            if name in fields:
                return fields[name]
            return super().__getattr__(name)

    task = FakeTask("update_boundaries", state)
    task.arguments = FieldAwareArguments(state)
    if remote_state is not None:
        task.arguments.remote_state = remote_state
    return task


def test_update_boundaries_read_parses_legacy_string_literal_remote_values(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)
    update_boundaries = _field_aware_task(
        {"selection_type": "label"},
        {
            "boundary_current_list": _RemoteField("['inlet-hot', 'inlet-cold']"),
            "boundary_current_type_list": _RemoteField("['wall', 'wall']"),
        },
        remote_state={"selection_type": "label"},
    )
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.read_arguments(
        MeshingReadRequest(
            workflow_type="watertight",
            items=[
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_list"],
                ),
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_type_list"],
                ),
            ],
            fresh=True,
        )
    )

    assert report.status == "success"
    values = {item.argument_path[-1]: item.value for item in report.items}
    assert values["boundary_current_list"] == ["inlet-hot", "inlet-cold"]
    assert values["boundary_current_type_list"] == ["wall", "wall"]


def test_update_boundaries_read_marks_unreadable_live_table_as_not_found(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)
    # PyFluent returns no usable list for the dynamic table: the per-field
    # remote reader yields None and the task snapshot omits the fields.
    update_boundaries = _field_aware_task(
        {"selection_type": "label"},
        {
            "boundary_current_list": _RemoteField(None),
            "boundary_current_type_list": _RemoteField(None),
        },
        remote_state={"selection_type": "label"},
    )
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.read_arguments(
        MeshingReadRequest(
            workflow_type="watertight",
            items=[
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_list"],
                ),
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_type_list"],
                ),
            ],
            fresh=True,
        )
    )

    assert report.status == "failed"
    assert len(report.items) == 2
    assert all(not item.found for item in report.items)
    assert all(item.error for item in report.items)


def test_update_boundaries_read_falls_back_to_fresh_snapshot_when_field_read_fails(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)
    update_boundaries = _field_aware_task(
        {
            "selection_type": "label",
            "boundary_current_list": ["inlet-hot", "inlet-cold"],
            "boundary_current_type_list": ["velocity-inlet", "velocity-inlet"],
        },
        {
            "boundary_current_list": _RemoteField(raises=True),
            "boundary_current_type_list": _RemoteField(raises=True),
        },
        remote_state={
            "selection_type": "label",
            "boundary_current_list": ["inlet-hot", "inlet-cold"],
            "boundary_current_type_list": ["wall", "wall"],
        },
    )
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.read_arguments(
        MeshingReadRequest(
            workflow_type="watertight",
            items=[
                MeshingArgumentReference(
                    task_path=["update_boundaries"],
                    argument_path=["boundary_current_type_list"],
                ),
            ],
            fresh=True,
        )
    )

    assert report.status == "success"
    assert report.items[0].value == ["wall", "wall"]


def test_update_boundaries_fails_when_fluent_task_returns_false(monkeypatch: Any) -> None:
    adapter_module = _import_adapter(monkeypatch)

    class FalseTask(FakeTask):
        def __call__(self) -> bool:
            return False

    update_boundaries = FalseTask("update_boundaries", {})
    adapter = adapter_module.PyFluentMeshingAdapter(session=ActiveSession())
    adapter._workflow = FakeWorkflow([update_boundaries])
    adapter._workflow_type = "watertight"

    report = adapter.execute_task("watertight", ["update_boundaries"])

    assert report.status == "failed"
    assert "returned False" in report.message
