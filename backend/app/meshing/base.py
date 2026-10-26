"""Contract for a dedicated Fluent Meshing workflow session."""

from collections.abc import Callable
from typing import Protocol

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingPresetDocument,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingTaskExecutionReport,
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

    def execute_task(
        self,
        workflow_type: str,
        task_path: list[str],
    ) -> MeshingTaskExecutionReport: ...

    def reset_workflow(self, workflow_type: str) -> None: ...

    def register_transcript_callback(self, callback: Callable[[str], None]) -> str | None: ...

    def unregister_transcript_callback(self) -> None: ...
