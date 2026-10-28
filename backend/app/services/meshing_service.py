"""Coordinated Meshing preset application with jobs and sync logs."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import Lock, Timer
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
    MeshingArchiveCreate,
    MeshingArchiveRecord,
    MeshingLiveSessionSnapshot,
    MeshingLiveSessionStart,
    MeshingLiveStepReport,
    MeshingLiveStepRequest,
    MeshingLiveWriteRequest,
    MeshingReferenceInspection,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingWorkflowReport,
    MeshingWriteReport,
    MeshingWriteRequest,
    SyncLogCreate,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_plan import watertight_steps
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


class MeshingAdapterBusyError(RuntimeError):
    """A Fluent call is active or unresponsive, so the service will not queue more work."""


class MeshingService:
    """Own the Meshing adapter session and persist apply activity."""

    def __init__(
        self,
        database: Database,
        adapter: MeshingWorkflowAdapter,
        *,
        live_phase_timeout_seconds: float = 180.0,
        live_hard_timeout_seconds: float = 900.0,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meshing-adapter")
        self.live = MeshingLiveManager(
            database,
            adapter,
            phase_timeout_seconds=live_phase_timeout_seconds,
            phase_hard_timeout_seconds=live_hard_timeout_seconds,
        )
        self._last_connection_config: FluentConnectionConfig | None = None
        self._native_poll: dict[str, Future[None]] = {}
        self._native_poll_timers: dict[str, Timer] = {}
        self._native_task_change: dict[str, Future[None]] = {}
        self._live_start_futures: dict[str, Future[None]] = {}
        self._operation_state_lock = Lock()
        self._active_adapter_future: Future[object] | None = None
        self._adapter_unresponsive = False
        self._native_poll_timeout_seconds = max(
            0.05, min(30.0, live_phase_timeout_seconds)
        )

    def _run[T](
        self,
        operation: Callable[[], T],
        *,
        timeout_seconds: float | None = 180.0,
        session_id: str | None = None,
        operation_name: str = "Fluent Meshing 操作",
    ) -> T:
        effective_timeout_seconds = (
            self.live.phase_hard_timeout_seconds
            if timeout_seconds is None
            else timeout_seconds
        )
        with self._operation_state_lock:
            if self._adapter_unresponsive:
                raise MeshingAdapterBusyError(
                    "Fluent 前一次调用超时，平台已停止提交新请求。"
                    "请检查 Fluent 控制台并重启 Fluent AI 后再连接。"
                )
            if any(not future.done() for future in self._live_start_futures.values()):
                raise MeshingAdapterBusyError(
                    "Fluent 正在自动准备当前模型。平台会继续轮询步骤状态，请勿重复提交操作。"
                )
            if any(not future.done() for future in self._native_poll.values()):
                raise MeshingAdapterBusyError(
                    "Fluent 当前步骤查询仍未返回。平台没有重复提交参数读写请求。"
                )
            if self._active_adapter_future is not None and not self._active_adapter_future.done():
                raise MeshingAdapterBusyError(
                    "Fluent 正在处理前一项请求。平台没有重复提交新请求。"
                )
            future: Future[T] = self._executor.submit(operation)
            self._active_adapter_future = future  # type: ignore[assignment]
        try:
            return future.result(timeout=effective_timeout_seconds)
        except FutureTimeoutError as exc:
            elapsed_limit = effective_timeout_seconds
            with self._operation_state_lock:
                self._adapter_unresponsive = True
            if session_id is not None:
                self.live.fail_unresponsive_operation(
                    session_id, operation_name, elapsed_limit
                )
            raise MeshingAdapterBusyError(
                f"{operation_name}连续 {elapsed_limit:g} 秒没有返回。"
                "平台已停止提交后续请求；当前 Fluent 请求无法被安全中断，请检查 Fluent 控制台。"
            ) from exc
        finally:
            if future.done():
                self._clear_active_adapter_future(future)
            else:
                future.add_done_callback(self._clear_active_adapter_future)

    def _clear_active_adapter_future(self, future: Future[object]) -> None:
        with self._operation_state_lock:
            if self._active_adapter_future is future:
                self._active_adapter_future = None
                self._adapter_unresponsive = False

    def status(self) -> FluentStatus:
        return self._run(self.adapter.status)

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        status = self._run(
            lambda: self.adapter.connect(config),
            timeout_seconds=float(config.start_timeout + 5),
            operation_name="连接 Fluent Meshing",
        )
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
        future = self._executor.submit(
            self.live.begin,
            snapshot.session_id,
            lambda task_name: self._schedule_native_task_change(
                snapshot.session_id, task_name
            ),
            lambda: self._schedule_native_poll(snapshot.session_id),
        )
        with self._operation_state_lock:
            self._live_start_futures[snapshot.session_id] = future
        future.add_done_callback(
            lambda completed: self._observe_live_start(snapshot.session_id, completed)
        )
        return snapshot

    def _observe_live_start(self, session_id: str, future: Future[None]) -> None:
        try:
            error = future.exception()
        except BaseException as exc:
            error = exc
        with self._operation_state_lock:
            self._live_start_futures.pop(session_id, None)
        if error is not None:
            self.live.fail_background_start(session_id, error)

    def _schedule_native_task_change(self, session_id: str, task_name: str) -> None:
        with self._operation_state_lock:
            pending = self._native_task_change.get(session_id)
            if pending is not None and not pending.done():
                return
            if any(not start.done() for start in self._live_start_futures.values()):
                return
            if self._adapter_unresponsive or (
                self._active_adapter_future is not None
                and not self._active_adapter_future.done()
            ):
                return
            future = self._executor.submit(
                self.live.native_task_changed, session_id, task_name
            )
            self._native_task_change[session_id] = future
            self._active_adapter_future = future  # type: ignore[assignment]
        future.add_done_callback(
            lambda completed: self._observe_native_task_change(session_id, completed)
        )

    def _observe_native_task_change(
        self, session_id: str, future: Future[None]
    ) -> None:
        try:
            error = future.exception()
        except BaseException as exc:
            error = exc
        with self._operation_state_lock:
            if self._native_task_change.get(session_id) is future:
                self._native_task_change.pop(session_id, None)
            if self._active_adapter_future is future:
                self._active_adapter_future = None
                self._adapter_unresponsive = False
        if error is not None:
            self.live.fail_background_task_change(session_id, error)

    def get_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        snapshot = self.live.get(session_id)
        should_poll_native_task = snapshot.status in {"waiting", "connected"} or (
            snapshot.status == "running" and snapshot.phase == "generating_surface"
        )
        if should_poll_native_task:
            self._schedule_native_poll(session_id)
        return snapshot

    def _schedule_native_poll(self, session_id: str) -> None:
        future: Future[None] | None = None
        timeout_timer: Timer | None = None
        with self._operation_state_lock:
            pending = self._native_poll.get(session_id)
            if pending is not None and not pending.done():
                return
            if any(not start.done() for start in self._live_start_futures.values()):
                return
            if self._adapter_unresponsive or (
                self._active_adapter_future is not None
                and not self._active_adapter_future.done()
            ):
                return
            future = self._executor.submit(self.live.poll_native_step, session_id)
            self._native_poll[session_id] = future
            self._active_adapter_future = future  # type: ignore[assignment]
            timeout_timer = Timer(
                self._native_poll_timeout_seconds,
                self._expire_native_poll,
                args=(session_id, future, self._native_poll_timeout_seconds),
            )
            timeout_timer.daemon = True
            self._native_poll_timers[session_id] = timeout_timer
            timeout_timer.start()
        future.add_done_callback(
            lambda completed: self._observe_native_poll(session_id, completed)
        )

    def _expire_native_poll(
        self, session_id: str, future: Future[None], timeout_seconds: float
    ) -> None:
        with self._operation_state_lock:
            if self._native_poll.get(session_id) is not future or future.done():
                return
            self._adapter_unresponsive = True
        self.live.native_task_poll_failed(
            session_id,
            TimeoutError("Fluent 当前步骤查询未返回"),
            timeout_seconds=timeout_seconds,
        )

    def _observe_native_poll(self, session_id: str, future: Future[None]) -> None:
        try:
            error = future.exception()
        except BaseException as exc:
            error = exc
        with self._operation_state_lock:
            timer = self._native_poll_timers.pop(session_id, None)
            if timer is not None:
                timer.cancel()
            if self._native_poll.get(session_id) is future:
                self._native_poll.pop(session_id, None)
            if self._active_adapter_future is future:
                self._active_adapter_future = None
                self._adapter_unresponsive = False
        if error is not None:
            self.live.native_task_poll_failed(session_id, error)
        else:
            self.live.native_task_poll_succeeded(session_id)

    def enter_live_step(
        self, session_id: str, payload: MeshingLiveStepRequest
    ) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.enter_step(session_id, payload.step_index),
            session_id=session_id,
            operation_name="写入并读取 Fluent 步骤参数",
        )

    def read_live_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.read_step(session_id, step_index),
            session_id=session_id,
            operation_name="读取 Fluent 步骤参数",
        )

    def write_live_step(
        self, session_id: str, payload: MeshingLiveWriteRequest
    ) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.write_step(session_id, payload.step_index, payload.items),
            session_id=session_id,
            operation_name="写入 Fluent 步骤参数",
        )

    def execute_live_step(
        self, session_id: str, payload: MeshingLiveStepRequest
    ) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.execute_step(session_id, payload.step_index),
            timeout_seconds=None,
            session_id=session_id,
            operation_name="执行 Fluent 工作流步骤",
        )

    def retry_live_preparation(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(
            lambda: self.live.retry_prepare(session_id),
            session_id=session_id,
            operation_name="重试 Fluent 自动准备",
        )

    def next_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(
            lambda: self.live.next_model(session_id),
            session_id=session_id,
            operation_name="切换 Fluent 几何模型",
        )

    def retry_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._run(
            lambda: self.live.retry_model(session_id),
            session_id=session_id,
            operation_name="重新导入 Fluent 几何模型",
        )

    def stop_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        with self._operation_state_lock:
            live_start_pending = any(
                not future.done() for future in self._live_start_futures.values()
            )
            adapter_call_pending = (
                self._active_adapter_future is not None
                and not self._active_adapter_future.done()
            )
            adapter_unresponsive = self._adapter_unresponsive
        if live_start_pending or adapter_call_pending or adapter_unresponsive:
            return self.live.stop_background_tracking(session_id)
        return self._run(lambda: self.live.stop(session_id))

    def _disconnect_impl(self) -> FluentStatus:
        self.adapter.disconnect()
        self._last_connection_config = None
        return self.adapter.status()

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport:
        return self._run(lambda: self.adapter.read_arguments(request))

    def inspect_reference_model(self, model_id: int) -> MeshingReferenceInspection:
        model = ModelRepository(self.database).get(model_id)
        path = Path(model.file_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in MESHING_GEOMETRY_EXTENSIONS:
            raise ValueError(f"参考模型文件不存在或格式不受支持: {path}")
        config = self.default_connection_config().model_copy(
            update={"mode": "launch", "ui_mode": "no_gui"}
        )
        inspection_adapter = type(self.adapter)()
        try:
            status = inspection_adapter.connect(config)
            labels = inspection_adapter.inspect_reference_labels(str(path))
            return MeshingReferenceInspection(
                model_id=model.id,
                model_name=model.name,
                fluent_version=status.version,
                labels=labels,
                message=f"Fluent 已读取 {len(labels)} 个可确认的标签。",
            )
        finally:
            inspection_adapter.disconnect()

    def archive_live_result(
        self, session_id: str, payload: MeshingArchiveCreate
    ) -> MeshingArchiveRecord:
        return self._run(lambda: self.live.archive_result(session_id, payload))

    def list_live_archives(self, session_id: str) -> list[MeshingArchiveRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM meshing_result_archives WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        records: list[MeshingArchiveRecord] = []
        for row in rows:
            document = json.loads(Path(row["record_json_path"]).read_text(encoding="utf-8"))
            records.append(
                MeshingArchiveRecord(
                    id=row["id"],
                    session_id=row["session_id"],
                    automation_id=row["automation_id"] or 0,
                    model_id=row["model_id"] or 0,
                    mesh_path=row["mesh_path"],
                    record_json_path=row["record_json_path"],
                    record_markdown_path=row["record_markdown_path"],
                    created_at=row["created_at"],
                    difference_count=len(document.get("differences", [])),
                    unavailable_count=len(document.get("unavailable_comparisons", [])),
                )
            )
        return records

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

            preset_to_apply = automation.preset
            if automation.preset.workflow_type == "watertight":
                active_steps = set(watertight_steps(automation.preset.items))
                active_items = [
                    item
                    for item in automation.preset.items
                    if item.task_path and item.task_path[0] in active_steps
                ]
                preset_to_apply = automation.preset.model_copy(update={"items": active_items})

            suffix = Path(model.file_path).suffix.lower()
            if suffix not in MESHING_GEOMETRY_EXTENSIONS:
                raise ValueError(
                    "Meshing apply requires a supported geometry file; got "
                    f"{suffix or 'no suffix'}."
                )

            validation = MESHING_SCHEMA_INDEX.validate(preset_to_apply)
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
                preset_to_apply,
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
