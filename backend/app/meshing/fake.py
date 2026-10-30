"""In-memory Meshing adapter for service and API tests."""

from collections.abc import Callable
from typing import Literal

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingArgumentReference,
    MeshingArgumentWriteResult,
    MeshingNameCheck,
    MeshingPresetDocument,
    MeshingPresetValue,
    MeshingReadItemResult,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingTaskExecutionReport,
    MeshingWriteReport,
    MeshingWriteRequest,
)


class FakeMeshingAdapter:
    def __init__(self, *, known_names: set[str] | None = None) -> None:
        self.connected = False
        self.mode: Literal["launch", "attach"] | None = None
        self.known_names = set(known_names or {"wall-big", "wall-small", "inlet", "outlet"})
        self.applied_presets: list[tuple[MeshingPresetDocument, str, bool]] = []
        self.executed_tasks: list[tuple[str, tuple[str, ...]]] = []
        self.workflow_resets = 0
        self.transcript_callback: Callable[[str], None] | None = None
        self.current_task_callback: Callable[[str], None] | None = None
        self.current_task: str | None = None
        self.last_config: FluentConnectionConfig | None = None
        self.connect_calls = 0
        self.values: dict[
            tuple[tuple[str, ...], tuple[str, ...], str | None], MeshingPresetValue
        ] = {
            (("import_geometry",), ("file_format",), None): "CAD",
            (("import_geometry",), ("length_unit",), None): "mm",
            (("create_surface_mesh",), ("cfd_surface_mesh_controls", "min_size"), None): 0.001,
            (("create_surface_mesh",), ("cfd_surface_mesh_controls", "max_size"), None): 0.01,
        }

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        self.connect_calls += 1
        self.last_config = config
        self.connected = True
        self.mode = config.mode
        return self.status()

    def disconnect(self) -> None:
        self.connected = False
        self.mode = None

    def status(self) -> FluentStatus:
        return FluentStatus(connected=self.connected, mode=self.mode, version="25.2.0-fake")

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport:
        if not self.connected:
            return MeshingReadReport(
                workflow_type=request.workflow_type,
                status="failed",
                error="Fake Fluent Meshing is not connected.",
            )
        references = request.items or [
            MeshingArgumentReference(
                task_path=list(task_path),
                argument_path=list(argument_path),
            )
            for task_path, argument_path, child in self.values
            if child is None
        ]
        items = []
        for reference in references:
            key = (
                tuple(reference.task_path),
                tuple(reference.argument_path),
                reference.compound_child_name,
            )
            found = key in self.values
            items.append(
                MeshingReadItemResult(
                    task_path=reference.task_path,
                    argument_path=reference.argument_path,
                    compound_child_name=reference.compound_child_name,
                    found=found,
                    value=self.values[key] if found else None,
                    error=None if found else "Argument path was not found.",
                )
            )
        return MeshingReadReport(
            workflow_type=request.workflow_type,
            status="success",
            task_names=["import_geometry", "add_local_sizing", "create_surface_mesh"],
            items=items,
            error=None,
        )

    def write_arguments(self, request: MeshingWriteRequest) -> MeshingWriteReport:
        if not self.connected:
            return MeshingWriteReport(
                workflow_type=request.workflow_type,
                status="failed",
                verified=request.verify,
                error="Fake Fluent Meshing is not connected.",
            )
        selector_names = {"boi_face_label_list", "bl_label_list", "zone_selection_list"}
        missing_names = sorted(
            {
                str(name)
                for item in request.items
                if item.argument_path[-1] in selector_names and isinstance(item.value, list)
                for name in item.value
                if isinstance(name, str) and name not in self.known_names
            }
        )
        if missing_names:
            return MeshingWriteReport(
                workflow_type=request.workflow_type,
                status="failed",
                missing_names=missing_names,
                verified=request.verify,
                error="目标几何中找不到这些面/区域名称: " + ", ".join(missing_names),
            )
        results = []
        for item in request.items:
            key = (tuple(item.task_path), tuple(item.argument_path), item.compound_child_name)
            self.values[key] = item.value
            actual = self.values.get(key)
            results.append(
                MeshingArgumentWriteResult(
                    task_path=item.task_path,
                    argument_path=item.argument_path,
                    compound_child_name=item.compound_child_name,
                    expected=item.value,
                    actual=actual,
                    success=actual == item.value,
                )
            )
        return MeshingWriteReport(
            workflow_type=request.workflow_type,
            status="success" if all(result.success for result in results) else "failed",
            results=results,
            verified=request.verify,
        )

    def apply_preset(
        self,
        preset: MeshingPresetDocument,
        model_path: str,
        *,
        import_geometry: bool = True,
    ) -> MeshingApplyReport:
        if not self.connected:
            raise RuntimeError("Fake Fluent Meshing is not connected.")
        self.applied_presets.append((preset, model_path, import_geometry))
        checks: list[MeshingNameCheck] = []
        missing: list[str] = []
        results: list[MeshingArgumentWriteResult] = []
        for item in preset.items:
            if item.value_mode == "at_use" or (
                item.task_path == ["import_geometry"]
                and item.argument_path[-1] in {"file_name", "file_names", "mesh_file_name"}
            ):
                continue
            self.values[
                (tuple(item.task_path), tuple(item.argument_path), item.compound_child_name)
            ] = item.value
            if isinstance(item.value, list):
                for value in item.value:
                    if not isinstance(value, str) or value in self.known_names:
                        continue
                    check = MeshingNameCheck(kind="selection", name=value, found=False)
                    checks.append(check)
                    missing.append(f"selection:{value}")
            results.append(
                MeshingArgumentWriteResult(
                    task_path=item.task_path,
                    argument_path=item.argument_path,
                    compound_child_name=item.compound_child_name,
                    expected=item.value,
                    actual=item.value,
                    success=True,
                )
            )
        return MeshingApplyReport(
            workflow_type=preset.workflow_type,
            status="failed" if missing else "success",
            results=[] if missing else results,
            name_checks=checks,
            created_children=sorted(
                {
                    item.compound_child_name
                    for item in preset.items
                    if item.compound_child_name is not None
                }
            ),
            stopped_before=["Generate the Surface Mesh", "Generate the Volume Mesh"],
            imported_model=model_path if import_geometry else None,
            missing_names=missing,
            error=("Missing required Meshing names: " + ", ".join(missing)) if missing else None,
        )

    def execute_task(
        self,
        workflow_type: str,
        task_path: list[str],
    ) -> MeshingTaskExecutionReport:
        if not self.connected:
            return MeshingTaskExecutionReport(
                status="failed",
                task_path=task_path,
                message="Fake Fluent Meshing is not connected.",
            )
        self.executed_tasks.append((workflow_type, tuple(task_path)))
        return MeshingTaskExecutionReport(
            status="success",
            task_path=task_path,
            message=f"{'/'.join(task_path)} completed.",
            output=[f"execute {'/'.join(task_path)}", "Task completed."],
        )

    def reset_workflow(self, workflow_type: str) -> None:
        self.workflow_resets += 1

    def available_task_names(self, workflow_type: str) -> list[str]:
        from app.meshing.workflow_plan import CONTRACT

        return list(CONTRACT["step_order"])

    def register_transcript_callback(self, callback: Callable[[str], None]) -> str | None:
        self.transcript_callback = callback
        return "fake-transcript"

    def unregister_transcript_callback(self) -> None:
        self.transcript_callback = None

    def read_current_task(self) -> str | None:
        return self.current_task

    def register_current_task_callback(self, callback: Callable[[str], None]) -> bool:
        self.current_task_callback = callback
        return True

    def unregister_current_task_callback(self) -> None:
        self.current_task_callback = None

    def inspect_reference_labels(self, model_path: str) -> list[str]:
        if not self.connected:
            raise RuntimeError("Fake Fluent Meshing is not connected.")
        self.apply_preset(
            MeshingPresetDocument(
                schema_version=2, fluent_version="25.2.0", workflow_type="watertight", items=[]
            ),
            model_path,
        )
        return sorted(self.known_names)


class AttachRejectingMeshingAdapter(FakeMeshingAdapter):
    """Fake adapter that rejects attach mode like the real PyFluent adapter."""

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        if config.mode == "attach" and not config.port and not config.server_info_file:
            raise ValueError("Attach mode requires a port or server-info file.")
        return super().connect(config)
