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
    MeshingLiveSessionSnapshot,
    MeshingLiveSessionStart,
    MeshingLiveStepReport,
    MeshingLiveStepRequest,
    MeshingLiveWriteRequest,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingWorkflowReport,
    MeshingWriteReport,
    MeshingWriteRequest,
    SyncLogCreate,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.repositories.common import utc_now
from app.repositories.jobs import JobRepository
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository
from app.repositories.sync_logs import SyncLogRepository
from app.services.job_control import JobCancelledError, ensure_job_active
from app.services.meshing_live import MeshingLiveManager

MESHING_GEOMETRY_EXTENSIONS = {
    ".dsco",
    ".scdoc",
    ".scdocx",
    ".step",
    ".stp",
    ".stpz",
    ".iges",
    ".igs",
    ".jt",
    ".3dxml",
    ".catpart",
    ".catproduct",
    ".sldprt",
    ".sldasm",
    ".ipt",
    ".iam",
    ".prt",
    ".asm",
    ".par",
    ".stl",
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
        self.live = MeshingLiveManager(database, adapter)
        self._last_connection_config: FluentConnectionConfig | None = None

    def _run[T](self, operation: Callable[[], T]) -> T:
        return self._executor.submit(operation).result()

    def status(self) -> FluentStatus:
        return self._run(self.adapter.status)

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        status = self._run(lambda: self.adapter.connect(config))
        if status.connected:
            self._last_connection_config = config
        return status

    def disconnect(self) -> FluentStatus:
        return self._run(self._disconnect_impl)

    def start_live_session(self, payload: MeshingLiveSessionStart) -> MeshingLiveSessionSnapshot:
        config = payload.connection or self.default_connection_config()
        if payload.connection is None and config.mode == "launch":
            config = config.model_copy(update={"ui_mode": "gui"})
        current_status = self._run(self.adapter.status)
        reuse_connection = bool(
            payload.connection is None
            and current_status.connected
            and self._last_connection_config is not None
            and self._last_connection_config.mode == config.mode
            and self._last_connection_config.ui_mode == "gui"
        )
        snapshot = self._run(
            lambda: self.live.start(
                payload.automation_id,
                payload.model_ids,
                config,
                reuse_connection,
            )
        )
        self._last_connection_config = config
        self._executor.submit(self.live.begin, snapshot.session_id)
        return snapshot

    def get_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self.live.get(session_id)

    def enter_live_step(
        self, session_id: str, payload: MeshingLiveStepRequest
    ) -> MeshingLiveStepReport:
        return self._run(lambda: self.live.enter_step(session_id, payload.step_index))

    def read_live_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        return self._run(lambda: self.live.read_step(session_id, step_index))

    def write_live_step(
        self, session_id: str, payload: MeshingLiveWriteRequest
    ) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.write_step(session_id, payload.step_index, payload.items)
        )

    def execute_live_step(
        self, session_id: str, payload: MeshingLiveStepRequest
    ) -> MeshingLiveStepReport:
        return self._run(lambda: self.live.execute_step(session_id, payload.step_index))

    def next_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(lambda: self.live.next_model(session_id))

    def retry_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(lambda: self.live.retry_model(session_id))

    def stop_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(lambda: self.live.stop(session_id))

    def _disconnect_impl(self) -> FluentStatus:
        self.adapter.disconnect()
        self._last_connection_config = None
        return self.adapter.status()

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport:
        return self._run(lambda: self.adapter.read_arguments(request))

    def write_arguments(self, request: MeshingWriteRequest) -> MeshingWriteReport:
        return self._run(lambda: self._write_arguments_impl(request))

    def _write_arguments_impl(self, request: MeshingWriteRequest) -> MeshingWriteReport:
        report = self.adapter.write_arguments(request)
        SyncLogRepository(self.database).create(
            SyncLogCreate(
                direction="write",
                target="Fluent Meshing",
                payload={
                    "workflow_type": request.workflow_type,
                    "items": [item.model_dump(mode="json") for item in request.items],
                    "report": report.model_dump(mode="json"),
                },
                status=report.status,
                message=(
                    f"{len(report.results)} Meshing argument write(s)."
                    if report.status == "success"
                    else (report.error or "Meshing argument write failed.")
                ),
            )
        )
        return report

    def apply_automation(
        self,
        automation_id: int,
        payload: ApplyMeshingAutomationRequest,
    ) -> MeshingWorkflowReport:
        return self._run(lambda: self._apply_automation_impl(automation_id, payload))

    def default_connection_config(self) -> FluentConnectionConfig:
        values = SettingsRepository(self.database).get_all()
        port_text = values.get("meshing_port", values.get("fluent_port", "")).strip()
        return FluentConnectionConfig(
            mode=cast(
                FluentLaunchMode,
                values.get("meshing_connect_mode", values.get("fluent_connect_mode", "launch")),
            ),
            fluent_path=values.get("meshing_fluent_path") or values.get("fluent_path") or None,
            product_version=values.get("fluent_version", "25.2.0"),
            ui_mode=cast(
                FluentUiMode,
                values.get("meshing_ui_mode", values.get("fluent_ui_mode", "no_gui")),
            ),
            host=values.get("meshing_host", values.get("fluent_host", "127.0.0.1")),
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
            ensure_job_active(jobs, job.id)
            jobs.update(job.id, status="running", progress=30, message="Fluent Meshing connected.")

            ensure_job_active(jobs, job.id)
            jobs.update(
                job.id,
                status="running",
                progress=55,
                message="Importing geometry and validating names.",
            )
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
            SettingsRepository(self.database).update(
                {
                    "recent_model_id": str(model.id),
                    "recent_meshing_automation_id": str(automation.id),
                    "recent_session_at": utc_now(),
                }
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
                message="Cancelled by user." if isinstance(exc, JobCancelledError) else error,
                connection=connection_status,
                apply_report=apply_report,
                sync_log_id=sync_log_id,
            )
