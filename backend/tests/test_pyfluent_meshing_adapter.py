"""Regression checks for minimizing synchronous PyFluent state reads."""

from __future__ import annotations

import re
import sys
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
        self.read_count = 0
        self.batch_state_calls: list[dict[str, Any]] = []

    def get_state(self) -> dict[str, Any]:
        self.read_count += 1
        return self.state

    def set_state(self, state: dict[str, Any]) -> None:
        self.batch_state_calls.append(dict(state))
        self.state.update(state)

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
            "boundary_current_list": ["inlet-hot", "inlet-cold"],
            "boundary_current_type_list": ["velocity-inlet", "velocity-inlet"],
            "boundary_label_list": ["inlet-hot", "inlet-cold"],
            "boundary_label_type_list": ["velocity-inlet", "velocity-inlet"],
        },
    )
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
        "velocity-inlet",
        "velocity-inlet",
    ]
    assert update_boundaries.arguments.state["boundary_label_type_list"] == ["wall", "wall"]
    assert len(update_boundaries.arguments.batch_state_calls) == 1
    assert update_boundaries.arguments.batch_state_calls[0]["old_boundary_label_type_list"] == [
        "velocity-inlet",
        "velocity-inlet",
    ]
    assert update_boundaries.arguments.batch_state_calls[0]["boundary_label_type_list"] == [
        "wall",
        "wall",
    ]


def test_execute_update_boundaries_reports_submitted_and_live_table_state(
    monkeypatch: Any,
) -> None:
    adapter_module = _import_adapter(monkeypatch)

    class UpdatingTask(FakeTask):
        def __call__(self) -> bool:
            self.arguments.state["boundary_current_type_list"] = ["wall", "wall"]
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
        "Update Boundaries state after execution" in line
        and "boundary_current_type_list': ['wall', 'wall']" in line
        for line in report.output
    )


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
