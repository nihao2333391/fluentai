"""In-memory Meshing adapter for service and API tests."""

from typing import Literal

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingArgumentWriteResult,
    MeshingNameCheck,
    MeshingPresetDocument,
)


class FakeMeshingAdapter:
    def __init__(self, *, known_names: set[str] | None = None) -> None:
        self.connected = False
        self.mode: Literal["launch", "attach"] | None = None
        self.known_names = set(known_names or {"wall-big", "wall-small", "inlet", "outlet"})
        self.applied_presets: list[tuple[MeshingPresetDocument, str, bool]] = []

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        self.connected = True
        self.mode = config.mode
        return self.status()

    def disconnect(self) -> None:
        self.connected = False
        self.mode = None

    def status(self) -> FluentStatus:
        return FluentStatus(connected=self.connected, mode=self.mode, version="25.2.0-fake")

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
