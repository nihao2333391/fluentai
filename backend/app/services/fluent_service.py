"""Fluent operations and the first persisted automation workflow."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, cast

from app.database import Database
from app.domain import (
    ApplyAutomationRequest,
    FluentConnectionConfig,
    FluentLaunchMode,
    FluentOperationReport,
    FluentStatus,
    FluentUiMode,
    JobCreate,
    ModelOpenReport,
    OpenModelRequest,
    PresetDocument,
    PresetItem,
    PresetValidationReport,
    PresetValue,
    SettingCatalogEntry,
    SettingWriteResult,
    SyncLogCreate,
    WorkflowReport,
)
from app.fluent.base import FluentAdapter
from app.fluent.catalog import FLUENT_252_CATALOG
from app.repositories.automations import AutomationRepository
from app.repositories.common import utc_now
from app.repositories.jobs import JobRepository
from app.repositories.models import ModelRepository
from app.repositories.settings import SettingsRepository
from app.repositories.sync_logs import SyncLogRepository
from app.services.job_control import JobCancelledError, ensure_job_active


class FluentService:
    """Own the Fluent adapter session and coordinate persisted workflows."""

    def __init__(self, database: Database, adapter: FluentAdapter) -> None:
        self.database = database
        self.adapter = adapter
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fluent-adapter")

    def _run[T](self, operation: Callable[[], T]) -> T:
        """Run all adapter calls on one dedicated thread."""
        return self._executor.submit(operation).result()

    def status(self) -> FluentStatus:
        return self._run(self.adapter.status)

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        return self._run(lambda: self.adapter.connect(config))

    def disconnect(self) -> FluentStatus:
        return self._run(self._disconnect_impl)

    def _disconnect_impl(self) -> FluentStatus:
        self.adapter.disconnect()
        return self.adapter.status()

    def catalog(self) -> list[SettingCatalogEntry]:
        def operation() -> list[SettingCatalogEntry]:
            catalog = (
                getattr(self.adapter, "catalog", FLUENT_252_CATALOG)
                if self.adapter.status().connected
                else FLUENT_252_CATALOG
            )
            return [
                SettingCatalogEntry(
                    setting_id=definition.setting_id,
                    display_name=definition.display_name,
                    group=definition.group,
                    value_type=definition.value_type,
                    allowed_values=(
                        list(definition.allowed_values)
                        if definition.allowed_values is not None
                        else None
                    ),
                    minimum=definition.minimum,
                    maximum=definition.maximum,
                    description=definition.description,
                )
                for definition in catalog.list()
            ]

        return self._run(operation)

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]:
        return self._run(lambda: self.adapter.read_settings(setting_ids))

    def write_settings(self, items: list[PresetItem]) -> FluentOperationReport:
        return self._run(lambda: self._write_settings_impl(items))

    def _write_settings_impl(self, items: list[PresetItem]) -> FluentOperationReport:
        report = self.adapter.write_settings(items)
        self._log_operation(
            direction="write",
            report=report,
            automation_id=None,
            model_id=None,
            message=f"{len(report.results)} setting write(s).",
        )
        return report

    def validate_preset(self, preset: PresetDocument) -> PresetValidationReport:
        def operation() -> PresetValidationReport:
            catalog = (
                getattr(self.adapter, "catalog", FLUENT_252_CATALOG)
                if self.adapter.status().connected
                else FLUENT_252_CATALOG
            )
            return self._validate_preset_with_catalog(preset, catalog)

        return self._run(operation)

    @staticmethod
    def _validate_preset_with_catalog(
        preset: PresetDocument, catalog: Any
    ) -> PresetValidationReport:
        errors: list[str] = []
        normalized: list[PresetItem] = []
        seen: set[str] = set()
        for item in preset.items:
            if item.setting_id in seen:
                errors.append(f"Duplicate setting: {item.setting_id}")
                continue
            seen.add(item.setting_id)
            try:
                definition = catalog.get(item.setting_id)
                value = definition.validate(item.value)
            except Exception as exc:
                errors.append(f"{item.setting_id}: {type(exc).__name__}: {exc}")
                continue
            normalized.append(
                PresetItem(
                    setting_id=item.setting_id,
                    type=item.type,
                    value=value,
                    required=item.required,
                )
            )
        return PresetValidationReport(
            valid=not errors,
            errors=errors,
            normalized_items=normalized,
        )

    def apply_preset(self, preset: PresetDocument) -> FluentOperationReport:
        return self._run(lambda: self._apply_preset_impl(preset))

    def _apply_preset_impl(self, preset: PresetDocument) -> FluentOperationReport:
        validation = self._validate_preset_with_catalog(
            preset, getattr(self.adapter, "catalog", FLUENT_252_CATALOG)
        )
        if not validation.valid:
            report = FluentOperationReport(
                operation="apply",
                status="failed",
                results=[
                    SettingWriteResult(
                        setting_id=item.setting_id,
                        expected=item.value,
                        actual=None,
                        success=False,
                        message="Preset validation failed.",
                    )
                    for item in preset.items
                ],
            )
        else:
            report = self.adapter.apply_preset(
                PresetDocument(
                    schema_version=preset.schema_version,
                    fluent_version=preset.fluent_version,
                    items=validation.normalized_items,
                )
            )
        self._log_operation(
            direction="apply",
            report=report,
            automation_id=None,
            model_id=None,
            message="Direct preset application.",
        )
        return report

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

    def open_model(self, model_id: int, payload: OpenModelRequest) -> ModelOpenReport:
        return self._run(lambda: self._open_model_impl(model_id, payload))

    def _open_model_impl(self, model_id: int, payload: OpenModelRequest) -> ModelOpenReport:
        model = ModelRepository(self.database).get(model_id)
        connection_status = self.adapter.status()
        try:
            if not connection_status.connected:
                config = payload.connection or self.default_connection_config()
                connection_status = self.adapter.connect(config)
            if payload.load_case:
                self.adapter.load_case(model.file_path)
            SettingsRepository(self.database).update(
                {"recent_model_id": str(model_id), "recent_session_at": utc_now()}
            )
            return ModelOpenReport(
                status="success",
                model_id=model_id,
                message="Model loaded into Fluent.",
                connection=connection_status,
            )
        except Exception as exc:
            return ModelOpenReport(
                status="failed",
                model_id=model_id,
                message=f"{type(exc).__name__}: {exc}",
                connection=connection_status,
            )

    def apply_automation(
        self,
        automation_id: int,
        payload: ApplyAutomationRequest,
    ) -> WorkflowReport:
        return self._run(lambda: self._apply_automation_impl(automation_id, payload))

    def _apply_automation_impl(
        self,
        automation_id: int,
        payload: ApplyAutomationRequest,
    ) -> WorkflowReport:
        automations = AutomationRepository(self.database)
        models = ModelRepository(self.database)
        jobs = JobRepository(self.database)
        logs = SyncLogRepository(self.database)

        job = jobs.create(
            JobCreate(
                job_type="apply-automation",
                payload={"automation_id": automation_id, "model_id": payload.model_id},
            )
        )
        current_automation_id: int | None = None
        current_model_id: int | None = None
        connection_status: FluentStatus | None = None
        apply_report: FluentOperationReport | None = None
        sync_log_id: int | None = None
        try:
            jobs.update(job.id, status="running", progress=5, message="Loading resources.")
            ensure_job_active(jobs, job.id)
            automation = automations.get(automation_id)
            current_automation_id = automation.id
            model = models.get(payload.model_id)
            current_model_id = model.id

            connection_status = self.adapter.status()
            if not connection_status.connected:
                config = payload.connection or self.default_connection_config()
                connection_status = self.adapter.connect(config)
            ensure_job_active(jobs, job.id)
            jobs.update(job.id, status="running", progress=30, message="Fluent connected.")

            if payload.load_case:
                self.adapter.load_case(model.file_path)
            validation = self._validate_preset_with_catalog(
                automation.preset,
                getattr(self.adapter, "catalog", FLUENT_252_CATALOG),
            )
            if not validation.valid:
                raise ValueError("Automation preset is invalid: " + "; ".join(validation.errors))
            ensure_job_active(jobs, job.id)
            jobs.update(job.id, status="running", progress=55, message="Model loaded.")

            ensure_job_active(jobs, job.id)
            jobs.update(
                job.id,
                status="running",
                progress=70,
                message="Applying preset and verifying readback.",
            )
            apply_report = self.adapter.apply_preset(
                PresetDocument(
                    schema_version=automation.preset.schema_version,
                    fluent_version=automation.preset.fluent_version,
                    items=validation.normalized_items,
                )
            )
            succeeded = apply_report.status == "success"
            sync_log = logs.create(
                SyncLogCreate(
                    direction="apply",
                    target="Fluent",
                    automation_id=current_automation_id,
                    model_id=current_model_id,
                    payload={
                        "automation_name": automation.name,
                        "model_name": model.name,
                        "file_path": model.file_path,
                        "report": apply_report.model_dump(mode="json"),
                    },
                    status="success" if succeeded else "failed",
                    message=(
                        "Automation applied and verified."
                        if succeeded
                        else "Automation apply failed readback verification."
                    ),
                )
            )
            sync_log_id = sync_log.id
            if not succeeded:
                jobs.update(
                    job.id,
                    status="failed",
                    progress=100,
                    message="Preset apply failed.",
                    result={"sync_log_id": sync_log_id},
                    error="One or more settings failed readback verification.",
                )
                return WorkflowReport(
                    status="failed",
                    automation_id=automation_id,
                    model_id=payload.model_id,
                    job_id=job.id,
                    message="Automation applied with failures.",
                    connection=connection_status,
                    apply_report=apply_report,
                    sync_log_id=sync_log_id,
                )

            jobs.update(
                job.id,
                status="succeeded",
                progress=100,
                message="Automation applied successfully.",
                result={
                    "sync_log_id": sync_log_id,
                    "applied_settings": len(apply_report.results),
                },
            )
            SettingsRepository(self.database).update(
                {
                    "recent_model_id": str(model.id),
                    "recent_automation_id": str(automation.id),
                    "recent_session_at": utc_now(),
                }
            )
            return WorkflowReport(
                status="success",
                automation_id=automation_id,
                model_id=payload.model_id,
                job_id=job.id,
                message="Automation applied and verified.",
                connection=connection_status,
                apply_report=apply_report,
                sync_log_id=sync_log_id,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            try:
                sync_log = logs.create(
                    SyncLogCreate(
                        direction="apply",
                        target="Fluent",
                        automation_id=current_automation_id,
                        model_id=current_model_id,
                        payload={"error": message},
                        status="failed",
                        message=message,
                    )
                )
                sync_log_id = sync_log.id
            except Exception:
                sync_log_id = None
            jobs.update(
                job.id,
                status="failed",
                progress=100,
                message="Automation workflow failed.",
                result={"sync_log_id": sync_log_id} if sync_log_id else None,
                error=message,
            )
            return WorkflowReport(
                status="failed",
                automation_id=automation_id,
                model_id=payload.model_id,
                job_id=job.id,
                message="Cancelled by user." if isinstance(exc, JobCancelledError) else message,
                connection=connection_status,
                apply_report=apply_report,
                sync_log_id=sync_log_id,
            )

    def _log_operation(
        self,
        *,
        direction: Literal["read", "write", "sync", "apply", "pull"],
        report: FluentOperationReport,
        automation_id: int | None,
        model_id: int | None,
        message: str,
    ) -> None:
        SyncLogRepository(self.database).create(
            SyncLogCreate(
                direction=direction,
                target="Fluent",
                automation_id=automation_id,
                model_id=model_id,
                payload=report.model_dump(mode="json"),
                status="success" if report.status == "success" else "failed",
                message=message,
            )
        )
