"""Contract for a dedicated Fluent Meshing workflow session."""

from typing import Protocol

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingPresetDocument,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingWriteReport,
    MeshingWriteRequest,
)


class MeshingWorkflowAdapter(Protocol):
    def connect(self, config: FluentConnectionConfig) -> FluentStatus: ...

    def disconnect(self) -> None: ...

    def status(self) -> FluentStatus: ...

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport: ...

    def write_arguments(self, request: MeshingWriteRequest) -> MeshingWriteReport: ...

    def apply_preset(
        self,
        preset: MeshingPresetDocument,
        model_path: str,
        *,
        import_geometry: bool = True,
    ) -> MeshingApplyReport: ...
