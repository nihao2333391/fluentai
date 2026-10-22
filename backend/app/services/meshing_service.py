"""Coordinated Meshing preset application with jobs and sync logs."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

from app.database import Database
from app.domain import (
    ApplyMeshingAutomationRequest,
    FluentConnectionConfig,
    FluentLaunchMode,
    FluentStatus,
    FluentUiMode,
    JobCreate,
    MeshingApplyReport,
    MeshingWorkflowReport,
    SyncLogCreate,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.repositories.jobs import JobRepository
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository
from app.repositories.sync_logs import SyncLogRepository

MESHING_GEOMETRY_EXTENSIONS = {
    ".dsco",
    ".scdoc",
    ".step",
    ".stp",
    ".iges",
    ".igs",
    ".pmdb",
    ".fmd",
    ".tgf",
    ".x_t",
    ".x_b",
    ".sat",
    ".sab",
}


class MeshingService:
    """Own the Meshing adapter session and persist apply activity."""

    def __init__(self, database: Database, adapter: MeshingWorkflowAdapter) -> None:
        self.database = database
        self.adapter = adapter
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meshing-adapter")

    def _run[T](self, operation: Callable[[], T]) -> T:
        return self._executor.submit(operation).result()

    def apply_automation(
        self,
        automation_id: int,
        payload: ApplyMeshingAutomationRequest,
    ) -> MeshingWorkflowReport:
        return self._run(lambda: self._apply_automation_impl(automation_id, payload))

    def default_connection_config(self) -> FluentConnectionConfig:
        values = SettingsRepository(self.database).get_all()
        port_text = values.get("fluent_port", "").strip()
        return FluentConnectionConfig(
            mode=cast(FluentLaunchMode, values.get("fluent_connect_mode", "launch")),
            fluent_path=values.get("fluent_path") or None,
            product_version=values.get("fluent_version", "25.2.0"),
            ui_mode=cast(FluentUiMode, values.get("fluent_ui_mode", "gui")),
            host=values.get("fluent_host", "127.0.0.1"),
            port=int(port_text) if port_text else None,
        )

    def _apply_automation_impl(
        self,
        automation_id: int,
        payload: ApplyMeshingAutomationRequest,
    ) -> MeshingWorkflowReport:
        automations = MeshingAutomationRepository(self.database)
        models = ModelRepository(self.database)
        jobs = JobRepository(self.database)
        logs = SyncLogRepository(self.database)

        job = jobs.create(
            JobCreate(
                job_type="apply-meshing-automation",
                payload={"meshing_automation_id": automation_id, "model_id": payload.model_id},
            )
        )
        current_automation_id: int | None = None
        current_model_id: int | None = None
        connection_status: FluentStatus | None = None
        apply_report: MeshingApplyReport | None = None
        sync_log_id: int | None = None
        try:
            jobs.update(job.id, status="running", progress=5, message="Loading resources.")
            automation = automations.get(automation_id)
            current_automation_id = automation.id
            model = models.get(payload.model_id)
            current_model_id = model.id

            suffix = Path(model.file_path).suffix.lower()
            if suffix not in MESHING_GEOMETRY_EXTENSIONS:
                raise ValueError(
                    "Meshing apply requires a supported geometry file; got "
                    f"{suffix or 'no suffix'}."
                )

            validation = MESHING_SCHEMA_INDEX.validate(automation.preset)
            if not validation.valid:
                raise ValueError("Meshing preset is invalid: " + "; ".join(validation.errors))

            connection_status = self.adapter.status()
            if not connection_status.connected:
                config = payload.connection or self.default_connection_config()
                connection_status = self.adapter.connect(config)
            jobs.update(job.id, status="running", progress=30, message="Fluent Meshing connected.")

            apply_report = self.adapter.apply_preset(
                automation.preset,
                model.file_path,
                import_geometry=payload.import_geometry,
            )
            succeeded = apply_report.status == "success"
            sync_log = logs.create(
                SyncLogCreate(
                    direction="apply",
                    target="Fluent Meshing",
                    meshing_automation_id=current_automation_id,
                    model_id=current_model_id,
                    payload={
                        "meshing_automation_name": automation.name,
                        "model_name": model.name,
                        "file_path": model.file_path,
                        "report": apply_report.model_dump(mode="json"),
                    },
                    status="success" if succeeded else "failed",
                    message=(
                        "Meshing preset applied and verified before mesh generation."
                        if succeeded
                        else "Meshing preset apply failed."
                    ),
                )
            )
            sync_log_id = sync_log.id

            if not succeeded:
                jobs.update(
                    job.id,
                    status="failed",
                    progress=100,
                    message="Meshing preset apply failed.",
                    result={"sync_log_id": sync_log_id},
                    error=apply_report.error or "Meshing apply failed.",
                )
                return MeshingWorkflowReport(
                    status="failed",
                    automation_id=automation_id,
                    model_id=payload.model_id,
                    job_id=job.id,
                    message=apply_report.error or "Meshing preset applied with failures.",
                    connection=connection_status,
                    apply_report=apply_report,
                    sync_log_id=sync_log_id,
                )

            jobs.update(
                job.id,
                status="succeeded",
                progress=100,
                message="Meshing preset applied successfully.",
                result={
                    "sync_log_id": sync_log_id,
                    "applied_arguments": len(apply_report.results),
                    "created_children": len(apply_report.created_children),
                },
            )
            return MeshingWorkflowReport(
                status="success",
                automation_id=automation_id,
                model_id=payload.model_id,
                job_id=job.id,
                message="Meshing preset applied and verified before mesh generation.",
                connection=connection_status,
                apply_report=apply_report,
                sync_log_id=sync_log_id,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            try:
                sync_log = logs.create(
                    SyncLogCreate(
                        direction="apply",
                        target="Fluent Meshing",
                        meshing_automation_id=current_automation_id,
                        model_id=current_model_id,
                        payload={"error": error},
                        status="failed",
                        message=error,
                    )
                )
                sync_log_id = sync_log.id
            except Exception:
                sync_log_id = None
            jobs.update(
                job.id,
                status="failed",
                progress=100,
                message="Meshing workflow failed.",
                result={"sync_log_id": sync_log_id} if sync_log_id else None,
                error=error,
            )
            return MeshingWorkflowReport(
                status="failed",
                automation_id=automation_id,
                model_id=payload.model_id,
                job_id=job.id,
                message=error,
                connection=connection_status,
                apply_report=apply_report,
                sync_log_id=sync_log_id,
            )
