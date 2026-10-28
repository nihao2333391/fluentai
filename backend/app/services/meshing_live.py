"""In-memory orchestration for interactive Fluent Meshing workflow sessions."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, RLock, Timer
from time import perf_counter
from typing import Any, Callable, Literal
from uuid import uuid4

from app.database import Database
from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingArgumentReference,
    MeshingArchiveCreate,
    MeshingArchiveRecord,
    MeshingLiveLogEntry,
    MeshingLiveModelState,
    MeshingLiveSessionSnapshot,
    MeshingLiveStepReport,
    MeshingLiveStepState,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingWriteReport,
    MeshingWriteRequest,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_plan import watertight_steps
from app.repositories.common import utc_now
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository

WATERTIGHT_LIVE_STEPS = [
    "import_geometry",
    "add_local_sizing",
    "create_surface_mesh",
    "describe_geometry",
    "update_regions",
    "add_boundary_layer",
    "create_volume_mesh",
]
FLUID_ONLY_SETUP_TYPE = "The geometry consists of only fluid regions with no voids"


def _live_steps_for_preset(items: list[MeshingPresetItem]) -> list[str]:
    return watertight_steps(items)


@dataclass
class _LiveSession:
    session_id: str
    automation_id: int
    automation_name: str
    workflow_type: Literal["watertight", "fault-tolerant"]
    connection_config: FluentConnectionConfig
    models: list[MeshingLiveModelState]
    steps: list[MeshingLiveStepState]
    preset_items: list[MeshingPresetItem]
    connection_status: FluentStatus | None = None
    reuse_connection: bool = False
    status: Literal[
        "starting", "connected", "running", "waiting", "completed", "failed", "stopped"
    ] = "starting"
    current_model_index: int = 0
    current_step_index: int = 0
    logs: list[MeshingLiveLogEntry] = field(default_factory=list)
    child_names: dict[tuple[str, ...], set[str]] = field(default_factory=dict)
    next_log_sequence: int = 1
    message: str = ""
    native_step_subscription: bool = False
    last_native_task: str | None = None
    native_task_poll_error: str | None = None
    native_task_poll_failures: int = 0
    native_surface_mesh_transcript_success: bool = False
    transcript_tail: str = ""
    phase: str = "importing"
    phase_started_at: float = field(default_factory=perf_counter)
    abort_event: Event = field(default_factory=Event)
    abort_message: str = ""
    phase_generation: int = 0
    phase_timer: Timer | None = None
    phase_deadline_timer: Timer | None = None
    satisfied_at_use: set[tuple[tuple[str, ...], tuple[str, ...], str | None]] = field(default_factory=set)


class MeshingLiveManager:
    """Coordinate one interactive Meshing session and its model queue."""

    def __init__(
        self,
        database: Database,
        adapter: MeshingWorkflowAdapter,
        *,
        phase_timeout_seconds: float = 180.0,
        phase_hard_timeout_seconds: float = 900.0,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.phase_timeout_seconds = phase_timeout_seconds
        self.phase_hard_timeout_seconds = max(
            phase_timeout_seconds, phase_hard_timeout_seconds
        )
        self._sessions: dict[str, _LiveSession] = {}
        self._log_lock = RLock()
        self._phase_lock = RLock()

    def start(
        self,
        automation_id: int,
        model_ids: list[int],
        connection_config: FluentConnectionConfig,
        reuse_connection: bool,
    ) -> MeshingLiveSessionSnapshot:
        automation = MeshingAutomationRepository(self.database).get(automation_id)
        if automation.preset.workflow_type != "watertight":
            raise ValueError("实时同步目前仅支持 Watertight Geometry 工作流程。")
        repository = ModelRepository(self.database)
        models = [repository.get(model_id) for model_id in dict.fromkeys(model_ids)]
        preset_items = list(automation.preset.items)
        step_names = _live_steps_for_preset(preset_items)
        session = _LiveSession(
            session_id=str(uuid4()),
            automation_id=automation.id,
            automation_name=automation.name,
            workflow_type=automation.preset.workflow_type,
            connection_config=connection_config,
            models=[
                MeshingLiveModelState(model_id=model.id, name=model.name, file_path=model.file_path)
                for model in models
            ],
            steps=[MeshingLiveStepState(task_path=[name]) for name in step_names],
            preset_items=preset_items,
            reuse_connection=reuse_connection,
        )
        self._sessions[session.session_id] = session
        self._log(session, "info", f"正在启动 Fluent Meshing: {automation.name}")
        return self._snapshot(session)

    def begin(
        self,
        session_id: str,
        on_native_task: Callable[[str], None] | None = None,
        on_native_surface_mesh_complete: Callable[[], None] | None = None,
    ) -> None:
        session = self._require(session_id)
        startup_started = perf_counter()
        self._set_phase(session, "connecting", "正在连接 Fluent Meshing。")
        try:
            self._raise_if_aborted(session)
            if session.reuse_connection:
                status = self.adapter.status()
                if not status.connected:
                    raise RuntimeError("Existing Fluent Meshing session is no longer connected.")
            else:
                status = self.adapter.connect(session.connection_config)
            self._raise_if_aborted(session)
            session.connection_status = status
            self._log(
                session,
                "success",
                f"Fluent 已连接，用时 {perf_counter() - startup_started:.1f} 秒。",
                self._current_model(session).model_id,
            )
            session.steps[0].status = "running"
            session.current_step_index = 0
            session.status = "running"
            session.message = "Fluent Meshing 已连接, 正在导入几何模型。"
            self._log(session, "info", session.message)
            self.adapter.register_transcript_callback(
                lambda text: self._ingest_transcript(
                    session, text, on_native_surface_mesh_complete
                )
            )
            self._raise_if_aborted(session)
            if on_native_task is not None:
                session.native_step_subscription = self.adapter.register_current_task_callback(
                    on_native_task
                )
                self._raise_if_aborted(session)
            self._execute_import_step(session)
        except Exception as exc:
            if session.abort_event.is_set():
                return
            model = self._current_model(session)
            self._set_phase(session, "failed")
            session.status = "failed"
            session.message = self._friendly_start_error(self._error_message(exc), model.file_path)
            model.status = "failed"
            model.error = session.message
            session.steps[0].status = "failed"
            session.steps[0].message = session.message
            self._log(session, "error", session.message, model.model_id)

    def get(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._snapshot(self._require(session_id))

    def fail_background_start(self, session_id: str, error: BaseException) -> None:
        session = self._require(session_id)
        if session.status in {"failed", "stopped", "completed"}:
            return
        model = self._current_model(session)
        message = self._friendly_start_error(self._error_message(error), model.file_path)
        index = min(max(session.current_step_index, 0), len(session.steps) - 1)
        session.steps[index].status = "failed"
        session.steps[index].message = message
        session.status = "failed"
        session.message = message
        self._set_phase(session, "failed")
        model.status = "failed"
        model.error = message
        self._log(session, "error", message, model.model_id)

    def fail_background_task_change(
        self, session_id: str, error: BaseException
    ) -> None:
        session = self._require(session_id)
        if session.status in {"failed", "stopped", "completed"}:
            return
        message = (
            "Fluent 原生步骤状态处理失败："
            f"{self._error_message(error)}。平台已停止后续自动步骤。"
        )
        with self._phase_lock:
            session.abort_message = message
            session.abort_event.set()
            session.phase_generation += 1
            if session.phase_timer is not None:
                session.phase_timer.cancel()
                session.phase_timer = None
            if session.phase_deadline_timer is not None:
                session.phase_deadline_timer.cancel()
                session.phase_deadline_timer = None
            session.phase = "failed"
            session.phase_started_at = perf_counter()
            session.status = "failed"
            session.message = message
            index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            session.steps[index].status = "failed"
            session.steps[index].message = message
            model = self._current_model(session)
            if model.status != "ready":
                model.status = "failed"
            model.error = message
        self._log(session, "error", message, model.model_id)

    def stop_background_tracking(self, session_id: str) -> MeshingLiveSessionSnapshot:
        """Stop follow-up work without disconnecting during an active Fluent RPC."""
        session = self._require(session_id)
        message = (
            "平台已停止后续自动步骤。当前 Fluent 请求无法被安全中断；"
            "Fluent 连接保持打开，请检查 Fluent 控制台。"
        )
        with self._phase_lock:
            session.abort_message = message
            session.abort_event.set()
            session.phase_generation += 1
            if session.phase_timer is not None:
                session.phase_timer.cancel()
                session.phase_timer = None
            if session.phase_deadline_timer is not None:
                session.phase_deadline_timer.cancel()
                session.phase_deadline_timer = None
            session.phase = "failed"
            session.phase_started_at = perf_counter()
            session.status = "stopped"
            session.message = message
            index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            if session.steps[index].status in {"running", "active"}:
                session.steps[index].status = "failed"
                session.steps[index].message = message
        self._log(session, "warning", message, self._current_model(session).model_id)
        return self._snapshot(session)

    def fail_unresponsive_operation(
        self, session_id: str, operation: str, timeout_seconds: float
    ) -> None:
        session = self._require(session_id)
        message = (
            f"Fluent 操作“{operation}”连续 {timeout_seconds:g} 秒没有返回。"
            "平台已停止后续自动步骤；当前 Fluent 请求无法被安全中断，请检查 Fluent 控制台。"
        )
        with self._phase_lock:
            if session.status in {"failed", "stopped", "completed"}:
                return
            session.abort_message = message
            session.abort_event.set()
            session.phase_generation += 1
            if session.phase_timer is not None:
                session.phase_timer.cancel()
                session.phase_timer = None
            if session.phase_deadline_timer is not None:
                session.phase_deadline_timer.cancel()
                session.phase_deadline_timer = None
            session.phase = "failed"
            session.phase_started_at = perf_counter()
            session.status = "failed"
            session.message = message
            index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            session.steps[index].status = "failed"
            session.steps[index].message = message
            model = self._current_model(session)
            if model.status != "ready":
                model.status = "failed"
                model.error = message
        self._log(session, "error", message, model.model_id)

    def poll_native_step(self, session_id: str) -> None:
        session = self._require(session_id)
        if session.status not in {"waiting", "connected", "running"}:
            return
        if session.phase not in {"surface_ready", "generating_surface"}:
            return
        self.native_task_changed(session_id, self.adapter.read_current_task())

    def native_task_poll_failed(
        self, session_id: str, error: BaseException, *, timeout_seconds: float | None = None
    ) -> None:
        session = self._require(session_id)
        if session.status in {"stopped", "completed"}:
            return
        session.native_task_poll_failures += 1
        if timeout_seconds is None:
            reason = f"{type(error).__name__}: {error}"
            message = (
                f"Fluent 当前步骤自动检测失败（连续第 {session.native_task_poll_failures} 次）："
                f"{reason}。平台会自动重试；请检查 Fluent 连接和控制台。"
            )
        else:
            message = (
                f"读取 Fluent 当前步骤连续 {timeout_seconds:g} 秒没有返回。"
                "平台已暂停新的 Fluent 请求，当前查询仍在运行；查询返回后会恢复自动检测。"
                "请检查 Fluent 控制台。"
            )
        session.native_task_poll_error = message
        if session.native_task_poll_failures == 1 or session.native_task_poll_failures % 5 == 0:
            self._log(session, "warning", message, self._current_model(session).model_id)

    def native_task_poll_succeeded(self, session_id: str) -> None:
        session = self._require(session_id)
        if session.native_task_poll_error is None:
            return
        session.native_task_poll_error = None
        session.native_task_poll_failures = 0
        if session.status not in {"stopped", "completed"}:
            self._log(
                session,
                "success",
                "Fluent 当前步骤自动检测已恢复。",
                self._current_model(session).model_id,
            )

    def native_task_changed(self, session_id: str, native_name: str | None) -> None:
        session = self._require(session_id)
        if not native_name or session.status in {"starting", "stopped", "failed"}:
            return
        normalized = native_name.strip().casefold()
        matched_index: int | None = None
        for index, step in enumerate(session.steps):
            task_name = step.task_path[-1]
            task = MESHING_SCHEMA_INDEX.get_task(session.workflow_type, [task_name])
            aliases = {task_name.casefold()}
            if task is not None:
                aliases.add(str(task.get("display_name", "")).casefold())
            if normalized not in aliases:
                continue
            matched_index = index
            break
        if matched_index is None:
            return

        previous_native_task = session.last_native_task
        session.last_native_task = native_name
        if previous_native_task is None or previous_native_task.strip().casefold() != normalized:
            session.last_native_task = native_name
            self._log(
                session, "info", f"Fluent 当前选择: {native_name}",
                self._current_model(session).model_id,
            )

        if session.native_surface_mesh_transcript_success:
            self._resume_after_native_surface_mesh(session, matched_index)

    def _resume_after_native_surface_mesh(
        self, session: _LiveSession, native_step_index: int
    ) -> bool:
        if session.phase not in {"surface_ready", "generating_surface"}:
            return False
        surface_index = next(
            (i for i, step in enumerate(session.steps)
             if step.task_path == ["create_surface_mesh"]),
            None,
        )
        if surface_index is None or native_step_index != surface_index + 1:
            return False

        with self._phase_lock:
            if (
                session.phase not in {"surface_ready", "generating_surface"}
                or session.status not in {"waiting", "running"}
                or not session.native_surface_mesh_transcript_success
            ):
                return False
            session.native_surface_mesh_transcript_success = False
            surface_step = session.steps[surface_index]
            surface_step.status = "completed"
            surface_step.message = "Fluent 原生界面已确认表面网格完成。"
            session.current_step_index = native_step_index
            session.status = "running"
            message = "已检测到 Fluent 原生表面网格完成，正在自动准备后续参数。"
            self._set_phase(session, "preparing_volume", message)

        self._log(session, "success", message, self._current_model(session).model_id)
        self._prepare_volume(session)
        return True

    def enter_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._raise_if_aborted(session)
        self._require_step(session, step_index)
        started = perf_counter()
        try:
            return self._enter_step(session, step_index, started)
        except Exception as exc:
            if session.abort_event.is_set():
                raise
            self._live_step_operation_failed(session, step_index, "参数同步", exc, started)
            return self._step_report(session, step_index, None, None)

    def _enter_step(
        self, session: _LiveSession, step_index: int, started: float
    ) -> MeshingLiveStepReport:
        self._select_step(session, step_index)
        step = session.steps[step_index]
        step.status = "running"
        session.status = "running"
        session.message = f"正在同步 Fluent 步骤: {'/'.join(step.task_path)}"
        self._log(session, "info", session.message, self._current_model(session).model_id)
        if step.preset_status in {"applied", "manual"}:
            read_report = self._read_step(session, step_index)
            step.duration_ms = round((perf_counter() - started) * 1000)
            step.status = "active" if read_report.status == "success" else "failed"
            session.status = "waiting" if read_report.status == "success" else "failed"
            step.message = read_report.error or f"步骤状态已读取，用时 {step.duration_ms / 1000:.1f} 秒。"
            self._log(session, "info", step.message, self._current_model(session).model_id)
            return self._step_report(session, step_index, None, read_report)
        items = self._step_preset_items(session, step_index)
        write_report: MeshingWriteReport | None = None
        if items:
            write_report = self.adapter.write_arguments(
                MeshingWriteRequest(
                    workflow_type=session.workflow_type,
                    items=items,
                    verify=True,
                    create_compound_child=True,
                )
            )
            self._raise_if_aborted(session)
            self._track_children(session, items)
            self._log(
                session,
                "success" if write_report.status == "success" else "error",
                (
                    f"已写入第 {step_index + 1} 步的 {len(items)} 项预设并回读。"
                    if write_report.status == "success"
                    else write_report.error or "步骤预设写入失败。"
                ),
                self._current_model(session).model_id,
            )
        read_report = self._read_step(session, step_index)
        self._raise_if_aborted(session)
        failed = (write_report is not None and write_report.status == "failed") or (
            read_report.status == "failed"
        )
        step.preset_status = "manual" if failed else "applied"
        session.steps[step_index].status = "failed" if failed else "active"
        session.steps[step_index].message = (
            (write_report.error if write_report else None) or read_report.error or ""
        )
        step.duration_ms = round((perf_counter() - started) * 1000)
        if not step.message:
            step.message = f"参数同步完成，用时 {step.duration_ms / 1000:.1f} 秒。"
        session.status = "failed" if failed else "waiting"
        session.message = session.steps[step_index].message
        if failed:
            model = self._current_model(session)
            model.status = "failed"
            model.error = session.steps[step_index].message or "Fluent 参数同步失败。"
        self._log(
            session,
            "error" if failed else "success",
            f"{step.message}（耗时 {step.duration_ms / 1000:.1f} 秒）",
            self._current_model(session).model_id,
        )
        return self._step_report(session, step_index, write_report, read_report)

    def read_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._require_step(session, step_index)
        try:
            read_report = self._read_step(session, step_index)
        except Exception as exc:
            if session.abort_event.is_set():
                raise
            read_report = MeshingReadReport(
                workflow_type=session.workflow_type,
                status="failed",
                error=f"Fluent 参数读取失败: {self._error_message(exc)}",
            )
            self._log(
                session,
                "error",
                read_report.error or "Fluent 参数读取失败。",
                self._current_model(session).model_id,
            )
        return self._step_report(session, step_index, None, read_report)

    def write_step(
        self,
        session_id: str,
        step_index: int,
        items: list[MeshingPresetItem],
    ) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._raise_if_aborted(session)
        self._require_step(session, step_index)
        started = perf_counter()
        try:
            return self._write_step(session, step_index, items, started)
        except Exception as exc:
            if session.abort_event.is_set():
                raise
            self._live_step_operation_failed(session, step_index, "参数写入", exc, started)
            return self._step_report(session, step_index, None, None)

    def _write_step(
        self,
        session: _LiveSession,
        step_index: int,
        items: list[MeshingPresetItem],
        started: float,
    ) -> MeshingLiveStepReport:
        self._select_step(session, step_index)
        step = session.steps[step_index]
        step.status = "running"
        session.status = "running"
        session.message = f"正在写入并回读 Fluent 参数: {'/'.join(step.task_path)}"
        write_report = self.adapter.write_arguments(
            MeshingWriteRequest(
                workflow_type=session.workflow_type,
                items=items,
                verify=True,
                create_compound_child=True,
            )
        )
        if write_report.status == "success":
            session.satisfied_at_use.update(
                (tuple(item.task_path), tuple(item.argument_path), item.compound_child_name)
                for item in items
            )
        self._track_children(session, items)
        read_report = self._read_step(session, step_index)
        failed = write_report.status == "failed" or read_report.status == "failed"
        session.steps[step_index].status = "failed" if failed else "active"
        session.steps[step_index].message = (
            write_report.error or read_report.error or "参数已写入 Fluent 并回读。"
        )
        step.duration_ms = round((perf_counter() - started) * 1000)
        session.steps[step_index].message += f"（耗时 {step.duration_ms / 1000:.1f} 秒）"
        session.status = "failed" if failed else "waiting"
        if failed:
            model = self._current_model(session)
            model.status = "failed"
            model.error = session.steps[step_index].message
        self._log(
            session,
            "error" if failed else "success",
            session.steps[step_index].message,
            self._current_model(session).model_id,
        )
        return self._step_report(session, step_index, write_report, read_report)

    def _live_step_operation_failed(
        self,
        session: _LiveSession,
        step_index: int,
        operation: str,
        error: Exception,
        started: float,
    ) -> None:
        step = session.steps[step_index]
        elapsed_ms = round((perf_counter() - started) * 1000)
        message = (
            f"Fluent 步骤“{'/'.join(step.task_path)}”{operation}失败："
            f"{self._error_message(error)}（耗时 {elapsed_ms / 1000:.1f} 秒）"
        )
        self._set_phase(session, "failed", message)
        session.status = "failed"
        session.current_step_index = step_index
        session.message = message
        step.status = "failed"
        step.duration_ms = elapsed_ms
        step.message = message
        model = self._current_model(session)
        model.status = "ready"
        model.error = message
        self._log(session, "error", message, model.model_id)

    def execute_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        task_name = session.steps[step_index].task_path[-1]
        expected_phase = {
            "create_surface_mesh": "surface_ready",
            "create_volume_mesh": "volume_ready",
        }.get(task_name)
        if expected_phase is None or session.phase != expected_phase:
            raise ValueError("请等待当前阶段参数核对完成，再使用对应的生成网格按钮。")
        self._set_phase(
            session,
            "generating_surface" if task_name == "create_surface_mesh" else "generating_volume",
            f"正在 Fluent 中生成{'面' if task_name == 'create_surface_mesh' else '体'}网格。",
        )
        report = self._execute_one_step(session_id, step_index)
        if report.status == "failed":
            self._set_phase(session, "failed")
        elif task_name == "create_surface_mesh":
            self._prepare_volume(session)
        else:
            self._set_phase(session, "completed")
        return self._step_report(session, step_index, None, report.read_report)

    def _execute_one_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._raise_if_aborted(session)
        self._select_step(session, step_index)
        if step_index == 0:
            return self._execute_import_step(session)
        task_path = session.steps[step_index].task_path
        started = perf_counter()
        session.steps[step_index].status = "running"
        session.status = "running"
        model = self._current_model(session)
        session.message = f"正在执行 Fluent 步骤: {'/'.join(task_path)}"
        self._log(session, "info", session.message, model.model_id)
        try:
            execution = self.adapter.execute_task(session.workflow_type, task_path)
            self._raise_if_aborted(session)
        except Exception as exc:
            if session.abort_event.is_set():
                return self._step_report(session, step_index, None, None)
            message = f"Fluent 步骤“{task_path[-1]}”调用失败：{self._error_message(exc)}"
            session.steps[step_index].status = "failed"
            session.steps[step_index].message = message
            session.status = "failed"
            self._set_phase(session, "failed", message)
            model.status = "failed"
            model.error = message
            self._log(session, "error", message, model.model_id)
            return self._step_report(session, step_index, None, None)
        duration_ms = round((perf_counter() - started) * 1000)
        session.steps[step_index].duration_ms = duration_ms
        for line in execution.output:
            self._log(session, "info", line, model.model_id)
        try:
            read_report = (
                self._read_step(session, step_index)
                if execution.status == "success"
                else None
            )
            self._raise_if_aborted(session)
        except Exception as exc:
            if session.abort_event.is_set():
                return self._step_report(session, step_index, None, None)
            message = f"Fluent 步骤“{task_path[-1]}”回读失败：{self._error_message(exc)}"
            session.steps[step_index].status = "failed"
            session.steps[step_index].message = message
            session.status = "failed"
            self._set_phase(session, "failed", message)
            model.status = "failed"
            model.error = message
            self._log(session, "error", message, model.model_id)
            return self._step_report(session, step_index, None, None)
        if read_report is not None and read_report.status == "failed":
            execution.status = "failed"
            execution.message = read_report.error or "Fluent 任务完成，但参数回读失败。"
        if read_report is not None and task_path == ["update_boundaries"]:
            mismatch = self._boundary_update_mismatch(session, read_report)
            if mismatch:
                execution.status = "failed"
                execution.message = mismatch
        if execution.status == "success":
            session.steps[step_index].status = "completed"
            session.steps[step_index].message = (
                f"{execution.message}（耗时 {duration_ms / 1000:.1f} 秒）"
            )
            self._log(session, "success", session.steps[step_index].message, model.model_id)
            if step_index == len(session.steps) - 1:
                model.status = "completed"
                session.status = (
                    "completed"
                    if session.current_model_index == len(session.models) - 1
                    else "waiting"
                )
                session.message = f"{model.name} 的 {len(session.steps)} 步工作流程已完成。"
            else:
                session.current_step_index = step_index + 1
                session.status = "waiting"
                session.message = f"已切换到下一步: {session.steps[step_index + 1].task_path[-1]}"
        else:
            session.steps[step_index].status = "failed"
            session.steps[step_index].message = (
                f"Fluent 步骤“{task_path[-1]}”执行失败（耗时 {duration_ms / 1000:.1f} 秒）："
                f"{execution.message}"
            )
            session.status = "failed"
            session.message = session.steps[step_index].message
            model.status = "failed"
            model.error = session.steps[step_index].message
            self._log(session, "error", session.steps[step_index].message, model.model_id)
        return self._step_report(session, step_index, None, read_report)

    def _execute_import_step(self, session: _LiveSession) -> MeshingLiveStepReport:
        model = self._current_model(session)
        session.steps[0].status = "running"
        session.status = "running"
        self._log(session, "info", f"正在执行导入几何模型: {model.name}", model.model_id)
        try:
            self.adapter.reset_workflow(session.workflow_type)
            self._raise_if_aborted(session)
            self._import_current_model(session)
            self._raise_if_aborted(session)
            self._prepare_surface(session)
            self._raise_if_aborted(session)
            if session.phase == "failed":
                return self._step_report(session, 0, None, None)
            if session.phase != "surface_ready":
                raise RuntimeError(
                    f"自动准备结束时阶段状态异常: {session.phase}。"
                )
            local_sizing_configured = any(
                item.task_path == ["add_local_sizing"]
                for item in session.preset_items
            )
            sizing_result = "局部尺寸已执行" if local_sizing_configured else "模板未配置局部尺寸"
            self._log(
                session,
                "success",
                f"{sizing_result}，面网格参数已写入并回读。",
                model.model_id,
            )
            return self._step_report(session, 0, None, None)
        except Exception as exc:
            if session.abort_event.is_set():
                return self._step_report(
                    session,
                    min(max(session.current_step_index, 0), len(session.steps) - 1),
                    None,
                    None,
                )
            message = self._friendly_start_error(self._error_message(exc), model.file_path)
            self._set_phase(session, "failed")
            session.status = "failed"
            session.message = message
            model.status = "failed"
            model.error = message
            failed_index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            session.steps[failed_index].status = "failed"
            session.steps[failed_index].message = message
            self._log(session, "error", message, model.model_id)
            return self._step_report(session, failed_index, None, None)

    def next_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        session = self._require(session_id)
        next_index = session.current_model_index + 1
        if next_index >= len(session.models):
            session.status = "completed"
            return self._snapshot(session)
        return self._switch_model(session, next_index)

    def retry_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        session = self._require(session_id)
        return self._switch_model(session, session.current_model_index)

    def stop(self, session_id: str) -> MeshingLiveSessionSnapshot:
        session = self._require(session_id)
        try:
            self.adapter.unregister_current_task_callback()
            self.adapter.unregister_transcript_callback()
            self.adapter.disconnect()
        finally:
            session.connection_status = FluentStatus(connected=False, mode=None)
            session.status = "stopped"
            session.message = "实时 Meshing 会话已停止。"
            self._log(session, "warning", session.message)
        return self._snapshot(session)

    def archive_result(
        self, session_id: str, payload: MeshingArchiveCreate
    ) -> MeshingArchiveRecord:
        session = self._require(session_id)
        if session.connection_status is None or not session.connection_status.connected:
            raise ValueError("Fluent 会话未连接，请先核对 Fluent 状态。")
        source = Path(payload.mesh_path).expanduser().resolve()
        if not source.is_file() or not source.name.lower().endswith((".msh", ".msh.h5")):
            raise ValueError("请选择 Fluent 已保存的 .msh 或 .msh.h5 网格文件。")
        if source.stat().st_size == 0:
            raise ValueError("网格文件为空。")
        archive_id = str(uuid4())
        directory = self.database.path.parent / "meshing-results" / archive_id
        directory.mkdir(parents=True, exist_ok=False)
        archived_mesh = directory / source.name
        shutil.copy2(source, archived_mesh)

        static_schema = json.loads(
            (Path(__file__).resolve().parents[1] / "meshing" / "workflow_schema.json")
            .read_text(encoding="utf-8")
        )
        defaults = {
            (tuple(step["task_path"]), tuple(field["path"])): field["default"]
            for step in static_schema["steps"]
            for field in step.get("fields", [])
            if "default" in field and field["default"] is not None
        }
        differences: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []
        read_errors: list[str] = []
        for index, step in enumerate(session.steps):
            report = self._read_step(session, index)
            if report.status != "success":
                read_errors.append(f"{'/'.join(step.task_path)}: {report.error or '读取失败'}")
                continue
            for item in report.items:
                if not item.found:
                    continue
                key = (tuple(item.task_path), tuple(item.argument_path))
                row = {
                    "task_path": item.task_path,
                    "argument_path": item.argument_path,
                    "compound_child_name": item.compound_child_name,
                    "final_value": item.value,
                }
                if key not in defaults:
                    unavailable.append({**row, "comparison": "无法比较"})
                elif item.value != defaults[key]:
                    differences.append({**row, "default_value": defaults[key]})
        if read_errors:
            raise RuntimeError("最终参数读取未完成: " + "; ".join(read_errors))

        model = self._current_model(session)
        record = {
            "schema_version": 1,
            "fluent_version": session.connection_status.version,
            "default_source_version": "Fluent 2025 R2 / 25.2.0",
            "session_id": session.session_id,
            "automation_id": session.automation_id,
            "automation_name": session.automation_name,
            "model_id": model.model_id,
            "model_name": model.name,
            "model_path": model.file_path,
            "source_mesh_path": str(source),
            "archived_mesh_path": str(archived_mesh),
            "modeling_notes": payload.modeling_notes,
            "step_states": [step.model_dump(mode="json") for step in session.steps],
            "differences": differences,
            "unavailable_comparisons": unavailable,
            "created_at": utc_now(),
        }
        json_path = directory / "record.json"
        markdown_path = directory / "record.md"
        json_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"# {model.name} 网格结果记录",
            "",
            f"- 模板：{session.automation_name}",
            f"- 目标模型：{model.file_path}",
            f"- 归档网格：{archived_mesh}",
            f"- Fluent 版本：{session.connection_status.version or '未知'}",
            "- 默认值依据：Fluent 2025 R2 / 25.2.0 静态工作流定义",
            "",
            "## 与默认值不同的参数",
            "",
        ]
        lines.extend(
            f"- {'/'.join(row['task_path'])} · {'/'.join(row['argument_path'])}"
            f"：默认 {json.dumps(row['default_value'], ensure_ascii=False)}；"
            f"最终 {json.dumps(row['final_value'], ensure_ascii=False)}"
            for row in differences
        )
        if not differences:
            lines.append("- 无可确认的差异。")
        lines.extend(["", "## 无法比较的项目", ""])
        lines.extend(
            f"- {'/'.join(row['task_path'])} · {'/'.join(row['argument_path'])}"
            f"：最终 {json.dumps(row['final_value'], ensure_ascii=False)}"
            for row in unavailable
        )
        if not unavailable:
            lines.append("- 无。")
        lines.extend(["", "## 建模笔记", "", payload.modeling_notes or "无。", ""])
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO meshing_result_archives
                (id, session_id, automation_id, model_id, mesh_path,
                 record_json_path, record_markdown_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    archive_id, session.session_id, session.automation_id, model.model_id,
                    str(archived_mesh), str(json_path), str(markdown_path), record["created_at"],
                ),
            )
        self._log(session, "success", f"已归档网格与参数差异: {archived_mesh}", model.model_id)
        return MeshingArchiveRecord(
            id=archive_id,
            session_id=session.session_id,
            automation_id=session.automation_id,
            model_id=model.model_id,
            mesh_path=str(archived_mesh),
            record_json_path=str(json_path),
            record_markdown_path=str(markdown_path),
            created_at=record["created_at"],
            difference_count=len(differences),
            unavailable_count=len(unavailable),
        )

    def _switch_model(self, session: _LiveSession, index: int) -> MeshingLiveSessionSnapshot:
        session.abort_event.clear()
        session.abort_message = ""
        session.native_surface_mesh_transcript_success = False
        session.transcript_tail = ""
        session.current_model_index = index
        session.current_step_index = 0
        session.status = "connected"
        session.message = "正在切换模型。"
        for step in session.steps:
            step.status = "pending"
            step.preset_status = "pending"
            step.message = ""
        session.satisfied_at_use.clear()
        self._set_phase(session, "importing", "正在切换并导入下一个几何模型。")
        for model_index, model in enumerate(session.models):
            if model_index < index and model.status != "failed":
                model.status = "completed"
        try:
            self.adapter.reset_workflow(session.workflow_type)
            session.connection_status = self.adapter.status()
            current = self._current_model(session)
            current.status = "pending"
            current.error = None
            self._import_current_model(session)
            self._prepare_surface(session)
            if session.phase == "surface_ready":
                self._log(session, "success", session.message, current.model_id)
            elif session.phase != "failed":
                raise RuntimeError(f"自动准备结束时阶段状态异常: {session.phase}。")
        except Exception as exc:
            model = self._current_model(session)
            model.status = "failed"
            model.error = self._error_message(exc)
            session.status = "failed"
            self._set_phase(session, "failed", model.error)
            self._log(session, "error", model.error, model.model_id)
        return self._snapshot(session)

    def _import_current_model(self, session: _LiveSession) -> None:
        model = self._current_model(session)
        started = perf_counter()
        model.status = "importing"
        session.steps[0].status = "running"
        self._set_phase(session, "importing", f"正在导入几何: {model.name}")
        session.status = "running"
        self._log(session, "info", f"正在导入几何: {model.name}", model.model_id)
        preset = MeshingPresetDocument(
            schema_version=1,
            fluent_version="25.2.0",
            workflow_type=session.workflow_type,
            items=[
                item for item in session.preset_items
                if item.task_path == ["import_geometry"]
                and item.value_mode == "fixed"
                and item.argument_path[-1] not in {"file_name", "file_names", "mesh_file_name"}
            ],
        )
        report = self.adapter.apply_preset(preset, model.file_path, import_geometry=True)
        self._raise_if_aborted(session)
        if report.status != "success":
            session.steps[0].duration_ms = round((perf_counter() - started) * 1000)
            raise RuntimeError(report.error or "几何导入失败。")
        model.status = "ready"
        model.error = None
        session.steps[0].status = "completed"
        session.steps[0].duration_ms = round((perf_counter() - started) * 1000)
        session.steps[0].message = "几何已导入。"
        session.current_step_index = 1
        session.status = "running"
        session.message = f"已导入 {model.name}，正在自动添加局部尺寸并准备面网格参数。"
        self._log(
            session,
            "success",
            f"几何导入完成，用时 {session.steps[0].duration_ms / 1000:.1f} 秒；继续自动准备。",
            model.model_id,
        )

    def _prepare_step(self, session: _LiveSession, index: int, execute: bool) -> bool:
        if session.abort_event.is_set():
            return False
        step = session.steps[index]
        if step.status == "completed":
            return True
        phase = self._phase_for_preparation_step(step.task_path[-1], execute=False)
        self._set_phase(session, phase, f"正在准备 Fluent 步骤: {'/'.join(step.task_path)}")
        session.status = "running"
        self._log(session, "info", session.message, self._current_model(session).model_id)
        missing = [
            "/".join(item.argument_path)
            for item in session.preset_items
            if item.task_path == step.task_path and item.value_mode == "at_use" and item.required
            and (tuple(item.task_path), tuple(item.argument_path), item.compound_child_name)
            not in session.satisfied_at_use
        ]
        if missing:
            self._preparation_failed(session, index, "请填写使用时参数: " + ", ".join(missing))
            return False
        try:
            report = self.enter_step(session.session_id, index)
        except Exception as exc:
            if session.abort_event.is_set():
                return False
            self._preparation_failed(session, index, self._error_message(exc))
            return False
        if session.abort_event.is_set():
            return False
        if report.status == "failed":
            self._preparation_failed(session, index, report.message)
            return False
        if execute:
            if step.task_path == ["add_local_sizing"]:
                self._set_phase(
                    session,
                    "executing_local_sizing",
                    "正在 Fluent 中执行局部尺寸。",
                )
                self._log(session, "info", session.message, self._current_model(session).model_id)
            session.status = "running"
            try:
                report = self._execute_one_step(session.session_id, index)
            except Exception as exc:
                if session.abort_event.is_set():
                    return False
                self._preparation_failed(session, index, self._error_message(exc))
                return False
            if session.abort_event.is_set():
                return False
            if report.status == "failed":
                self._preparation_failed(session, index, report.message)
                return False
        return True

    @staticmethod
    def _phase_for_preparation_step(task_name: str, *, execute: bool) -> str:
        if task_name == "add_local_sizing":
            return "executing_local_sizing" if execute else "preparing_local_sizing"
        if task_name == "create_surface_mesh":
            return "preparing_surface_mesh"
        return "preparing_surface"

    def _set_phase(self, session: _LiveSession, phase: str, message: str | None = None) -> None:
        with self._phase_lock:
            if session.abort_event.is_set() and phase != "failed":
                return
            session.phase_generation += 1
            generation = session.phase_generation
            if session.phase_timer is not None:
                session.phase_timer.cancel()
                session.phase_timer = None
            if session.phase_deadline_timer is not None:
                session.phase_deadline_timer.cancel()
                session.phase_deadline_timer = None
            session.phase = phase
            session.phase_started_at = perf_counter()
            if message is not None:
                session.message = message
            if phase in {
                "connecting",
                "importing",
                "preparing_surface",
                "preparing_local_sizing",
                "executing_local_sizing",
                "preparing_surface_mesh",
                "preparing_volume",
                "generating_surface",
                "generating_volume",
            }:
                timeout_seconds = self.phase_timeout_seconds
                if phase == "connecting":
                    timeout_seconds = max(
                        timeout_seconds, float(session.connection_config.start_timeout + 5)
                    )
                hard_timeout_seconds = self.phase_hard_timeout_seconds
                if phase == "connecting":
                    hard_timeout_seconds = max(
                        hard_timeout_seconds,
                        float(session.connection_config.start_timeout + 30),
                    )
                timer = Timer(
                    timeout_seconds,
                    self._expire_phase,
                    args=(session.session_id, generation, phase, timeout_seconds),
                )
                timer.daemon = True
                session.phase_timer = timer
                timer.start()
                deadline_timer = Timer(
                    hard_timeout_seconds,
                    self._fail_expired_phase,
                    args=(session.session_id, generation, phase, hard_timeout_seconds),
                )
                deadline_timer.daemon = True
                session.phase_deadline_timer = deadline_timer
                deadline_timer.start()

    def _expire_phase(
        self, session_id: str, generation: int, phase: str, timeout_seconds: float
    ) -> None:
        with self._phase_lock:
            session = self._sessions.get(session_id)
            if (
                session is None
                or session.phase_generation != generation
                or session.phase != phase
                or session.status not in {"starting", "running"}
            ):
                return
            phase_names = {
                "connecting": "连接 Fluent",
                "importing": "导入几何",
                "preparing_surface": "准备面网格前设置",
                "preparing_local_sizing": "写入并回读局部尺寸",
                "executing_local_sizing": "执行局部尺寸",
                "preparing_surface_mesh": "写入并回读面网格参数",
                "preparing_volume": "准备体网格前设置",
                "generating_surface": "生成面网格",
                "generating_volume": "生成体网格",
            }
            message = (
                f"Fluent 在“{phase_names.get(phase, phase)}”阶段连续 "
                f"{timeout_seconds:g} 秒没有返回。"
                "平台继续等待当前请求；Fluent 返回后会自动继续后续准备，且不会重复提交此请求。"
                "请查看 Fluent 控制台是否有错误。"
            )
            session.phase_timer = None
            session.message = message
            index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            if session.steps[index].status in {"running", "active"}:
                session.steps[index].message = message
            model = self._current_model(session)
        self._log(session, "warning", message, model.model_id)

    def _fail_expired_phase(
        self, session_id: str, generation: int, phase: str, timeout_seconds: float
    ) -> None:
        with self._phase_lock:
            session = self._sessions.get(session_id)
            if (
                session is None
                or session.phase_generation != generation
                or session.phase != phase
                or session.status not in {"starting", "running"}
            ):
                return
            phase_names = {
                "connecting": "连接 Fluent",
                "importing": "导入几何",
                "preparing_surface": "准备面网格前设置",
                "preparing_local_sizing": "写入并回读局部尺寸",
                "executing_local_sizing": "执行局部尺寸",
                "preparing_surface_mesh": "写入并回读面网格参数",
                "preparing_volume": "准备体网格前设置",
                "generating_surface": "生成面网格",
                "generating_volume": "生成体网格",
            }
            message = (
                f"Fluent 在“{phase_names.get(phase, phase)}”阶段连续 "
                f"{timeout_seconds:g} 秒没有返回。平台已停止后续自动步骤；"
                "当前 Fluent 请求无法被安全中断。请检查 Fluent 控制台；"
                "确认该请求已结束后再重试。"
            )
            session.abort_message = message
            session.abort_event.set()
            session.phase_generation += 1
            if session.phase_timer is not None:
                session.phase_timer.cancel()
                session.phase_timer = None
            session.phase_deadline_timer = None
            session.phase = "failed"
            session.phase_started_at = perf_counter()
            session.status = "failed"
            session.message = message
            index = min(max(session.current_step_index, 0), len(session.steps) - 1)
            session.steps[index].status = "failed"
            session.steps[index].message = message
            model = self._current_model(session)
            model.error = message
            if model.status != "ready":
                model.status = "failed"
        self._log(session, "error", message, model.model_id)

    @staticmethod
    def _raise_if_aborted(session: _LiveSession) -> None:
        if session.abort_event.is_set():
            raise RuntimeError(session.abort_message or "平台已停止后续自动步骤。")

    def _preparation_failed(self, session: _LiveSession, index: int, reason: str) -> None:
        self._set_phase(session, "failed")
        session.status = "failed"
        session.current_step_index = index
        session.message = f"{session.steps[index].task_path[-1]} 准备失败: {reason}"
        session.steps[index].status = "failed"
        session.steps[index].message = session.message
        model = self._current_model(session)
        # The geometry remains imported; the session phase and step carry the preparation error.
        model.status = "ready"
        model.error = session.message
        self._log(session, "error", session.message, self._current_model(session).model_id)

    def _prepare_surface(self, session: _LiveSession) -> None:
        self._set_phase(session, "preparing_surface", "正在自动准备面网格前设置。")
        session.status = "running"
        for index, step in enumerate(session.steps):
            name = step.task_path[-1]
            if name == "create_surface_mesh":
                if self._prepare_step(session, index, False):
                    if session.abort_event.is_set():
                        return
                    self._set_phase(session, "surface_ready")
                    session.status = "waiting"
                    self._current_model(session).status = "ready"
                    self._current_model(session).error = None
                    session.message = "面网格前设置已写入并回读，请检查后点击“生成面网格”。"
                return
            if name == "add_local_sizing":
                has_controls = any(item.task_path == step.task_path for item in session.preset_items)
                if has_controls and not self._prepare_step(session, index, True):
                    return
                if session.abort_event.is_set():
                    return
                if not has_controls:
                    step.status = "completed"
                    step.preset_status = "applied"
                    step.message = "模板未设置局部尺寸，沿用 Fluent 默认设置。"
        index = max(0, len(session.steps) - 1)
        self._preparation_failed(session, index, "工作流中找不到“生成表面网格”步骤。")

    def _prepare_volume(self, session: _LiveSession) -> None:
        session.native_surface_mesh_transcript_success = False
        self._set_phase(session, "preparing_volume", "正在准备体网格前设置。")
        session.status = "running"
        surface_index = next(i for i, step in enumerate(session.steps)
                             if step.task_path == ["create_surface_mesh"])
        for index in range(surface_index + 1, len(session.steps)):
            name = session.steps[index].task_path[-1]
            if name == "create_volume_mesh":
                if self._prepare_step(session, index, False):
                    self._set_phase(session, "volume_ready")
                    session.status = "waiting"
                    self._current_model(session).status = "ready"
                    self._current_model(session).error = None
                    session.message = "体网格前设置已写入并回读，请检查后点击“生成体网格”。"
                return
            if name == "enclose_fluid_regions":
                capping = next((item.value for item in session.preset_items
                                if item.task_path == ["describe_geometry"]
                                and item.argument_path == ["capping_required"]
                                and item.value_mode == "fixed"), "Yes")
                has_caps = any(item.task_path == [name] and item.compound_child_name
                               for item in session.preset_items)
                if capping == "Yes" and not has_caps:
                    self._preparation_failed(
                        session, index,
                        "该几何需要封盖。请在模板中为每个开口配置封盖标签后重试。",
                    )
                    return
            if name == "add_boundary_layer" and not any(
                item.task_path == ["add_boundary_layer"] for item in session.preset_items
            ):
                session.steps[index].status = "completed"
                session.steps[index].preset_status = "applied"
                session.steps[index].message = "模板未设置边界层，沿用 Fluent 默认设置。"
                continue
            if not self._prepare_step(session, index, True):
                return
            if name == "describe_geometry":
                available = set(self.adapter.available_task_names(session.workflow_type))
                planned = [step.task_path[-1] for step in session.steps[index + 1:]]
                missing = [task for task in planned if task not in available]
                if missing:
                    self._preparation_failed(
                        session, index,
                        "Fluent 当前任务树缺少计划步骤: " + ", ".join(missing),
                    )
                    return
        index = max(0, len(session.steps) - 1)
        self._preparation_failed(session, index, "工作流中找不到“生成体网格”步骤。")

    def retry_prepare(self, session_id: str) -> MeshingLiveSessionSnapshot:
        session = self._require(session_id)
        if session.phase != "failed":
            return self._snapshot(session)
        if session.status == "stopped":
            raise RuntimeError("已停止的实时 Meshing 会话不能重试。")
        session.abort_event.clear()
        session.abort_message = ""
        surface_done = any(step.task_path == ["create_surface_mesh"] and step.status == "completed"
                           for step in session.steps)
        if surface_done:
            self._prepare_volume(session)
        else:
            self._prepare_surface(session)
        return self._snapshot(session)

    def _read_step(self, session: _LiveSession, step_index: int) -> MeshingReadReport:
        task_path = list(session.steps[step_index].task_path)
        task = MESHING_SCHEMA_INDEX.get_task(session.workflow_type, task_path)
        if task is None:
            return MeshingReadReport(
                workflow_type=session.workflow_type,
                status="failed",
                error=f"Unknown Meshing task: {'/'.join(task_path)}",
            )
        references = self._read_references(session, task, task_path)
        report = self.adapter.read_arguments(
            MeshingReadRequest(workflow_type=session.workflow_type, items=references)
        )
        self._raise_if_aborted(session)
        return report

    def _read_references(
        self,
        session: _LiveSession,
        task: dict[str, Any],
        task_path: list[str],
    ) -> list[MeshingArgumentReference]:
        references = self._argument_references(task.get("arguments") or [], task_path)
        if task_path == ["update_boundaries"]:
            fixed_arguments = {
                item.argument_path[-1]
                for item in session.preset_items
                if item.task_path == task_path and item.value_mode == "fixed"
            }
            selection_type = next(
                (
                    str(item.value)
                    for item in session.preset_items
                    if item.task_path == task_path
                    and item.argument_path == ["selection_type"]
                    and item.value_mode == "fixed"
                ),
                "label"
                if fixed_arguments.intersection(
                    {"boundary_label_list", "boundary_label_type_list"}
                )
                else "zone",
            )
            name_argument = (
                "boundary_label_list" if selection_type == "label" else "boundary_zone_list"
            )
            type_argument = (
                "boundary_label_type_list"
                if selection_type == "label"
                else "boundary_zone_type_list"
            )
            references = [
                reference
                for reference in references
                if reference.argument_path
                and reference.argument_path[-1]
                in {
                    "selection_type",
                    name_argument,
                    type_argument,
                    "boundary_current_list",
                    "boundary_current_type_list",
                }
            ]
            references.extend(
                MeshingArgumentReference(
                    task_path=task_path,
                    argument_path=[argument_name],
                )
                for argument_name in (
                    "boundary_current_list",
                    "boundary_current_type_list",
                )
                if not any(
                    reference.argument_path == [argument_name]
                    for reference in references
                )
            )
        template = task.get("child_template")
        if isinstance(template, dict):
            for child_name in sorted(self._child_names_for_task(session, task_path)):
                references.extend(
                    self._argument_references(
                        template.get("arguments") or [],
                        task_path,
                        child_name,
                    )
                )
        return references

    @staticmethod
    def _boundary_update_mismatch(
        session: _LiveSession,
        read_report: MeshingReadReport,
    ) -> str | None:
        """Verify Fluent applied the configured boundary mapping to its live table."""
        actual_values = {
            item.argument_path[-1]: item.value
            for item in read_report.items
            if item.task_path == ["update_boundaries"] and item.argument_path
        }
        preset_values = {
            item.argument_path[-1]: item.value
            for item in session.preset_items
            if item.task_path == ["update_boundaries"] and item.value_mode == "fixed"
        }
        selection_type = preset_values.get("selection_type")
        if selection_type not in {"label", "zone"}:
            if {"boundary_label_list", "boundary_label_type_list"}.intersection(preset_values):
                selection_type = "label"
            elif {"boundary_zone_list", "boundary_zone_type_list"}.intersection(preset_values):
                selection_type = "zone"
            else:
                selection_type = actual_values.get("selection_type")
        if selection_type not in {"label", "zone"}:
            return None
        name_argument = (
            "boundary_label_list" if selection_type == "label" else "boundary_zone_list"
        )
        type_argument = (
            "boundary_label_type_list"
            if selection_type == "label"
            else "boundary_zone_type_list"
        )
        names = preset_values.get(name_argument, actual_values.get(name_argument))
        target_types = preset_values.get(type_argument, actual_values.get(type_argument))
        if names is None and target_types is None:
            return None
        if not isinstance(names, list) or not isinstance(target_types, list):
            return "Fluent 未回读完整的边界名称和目标类型列表。"
        if len(names) != len(target_types):
            return "边界名称与目标类型数量不一致，Fluent 未应用边界映射。"
        if not names:
            return None

        current_names = actual_values.get("boundary_current_list")
        current_types = actual_values.get("boundary_current_type_list")
        if not isinstance(current_names, list) or not isinstance(current_types, list):
            return "Fluent 未返回更新后的实际边界表，无法确认边界类型。"
        if len(current_names) != len(current_types):
            return "Fluent 返回的实际边界表名称与类型数量不一致。"

        current_by_name = {
            name: boundary_type
            for name, boundary_type in zip(current_names, current_types, strict=False)
            if isinstance(name, str) and isinstance(boundary_type, str)
        }
        mismatches = [
            f"{name}：模板要求 {expected_type}，Fluent 实际为 "
            f"{current_by_name.get(name, '未返回该边界')}"
            for name, expected_type in zip(names, target_types, strict=False)
            if not isinstance(name, str)
            or not isinstance(expected_type, str)
            or current_by_name.get(name) != expected_type
        ]
        if not mismatches:
            return None
        return "Fluent 更新边界后的实际类型与模板不一致：" + "；".join(mismatches)

    @staticmethod
    def _argument_references(
        arguments: list[dict[str, Any]],
        task_path: list[str],
        child_name: str | None = None,
        prefix: list[str] | None = None,
    ) -> list[MeshingArgumentReference]:
        references: list[MeshingArgumentReference] = []
        for argument in arguments:
            if argument.get("name") == "<arguments>":
                continue
            path = [*(prefix or []), str(argument.get("name"))]
            children = argument.get("children") or []
            if children:
                references.extend(
                    MeshingLiveManager._argument_references(children, task_path, child_name, path)
                )
            else:
                references.append(
                    MeshingArgumentReference(
                        task_path=task_path,
                        argument_path=path,
                        compound_child_name=child_name,
                    )
                )
        return references

    def _child_names_for_task(self, session: _LiveSession, task_path: list[str]) -> set[str]:
        names = set(session.child_names.get(tuple(task_path), set()))
        names.update(
            item.compound_child_name
            for item in session.preset_items
            if item.task_path == task_path and item.compound_child_name
        )
        return {name for name in names if name}

    def _step_preset_items(self, session: _LiveSession, step_index: int) -> list[MeshingPresetItem]:
        task_path = session.steps[step_index].task_path
        return [
            item for item in session.preset_items
            if item.task_path == task_path and item.value_mode == "fixed"
            and not (
                task_path == ["import_geometry"]
                and item.argument_path[-1] in {"file_name", "file_names", "mesh_file_name"}
            )
        ]

    def _select_step(self, session: _LiveSession, step_index: int) -> None:
        self._require_step(session, step_index)
        session.current_step_index = step_index

    @staticmethod
    def _track_children(session: _LiveSession, items: list[MeshingPresetItem]) -> None:
        for item in items:
            if item.compound_child_name:
                session.child_names.setdefault(tuple(item.task_path), set()).add(
                    item.compound_child_name
                )

    def _require(self, session_id: str) -> _LiveSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise LookupError(f"Meshing live session was not found: {session_id}")
        return session

    @staticmethod
    def _require_step(session: _LiveSession, step_index: int) -> None:
        if step_index < 0 or step_index >= len(session.steps):
            raise ValueError(f"Invalid Meshing workflow step index: {step_index}")

    @staticmethod
    def _current_model(session: _LiveSession) -> MeshingLiveModelState:
        return session.models[session.current_model_index]

    def _snapshot(self, session: _LiveSession) -> MeshingLiveSessionSnapshot:
        phase_elapsed_ms = (
            round((perf_counter() - session.phase_started_at) * 1000)
            if session.status == "running"
            else None
        )
        return MeshingLiveSessionSnapshot(
            session_id=session.session_id,
            automation_id=session.automation_id,
            automation_name=session.automation_name,
            workflow_type=session.workflow_type,
            status=session.status,
            phase=session.phase,
            phase_elapsed_ms=phase_elapsed_ms,
            connection=session.connection_status,
            models=session.models,
            current_model_index=session.current_model_index,
            current_step_index=session.current_step_index,
            steps=session.steps,
            logs=session.logs[-200:],
            message=session.message,
            native_task_poll_error=session.native_task_poll_error,
        )

    def _step_report(
        self,
        session: _LiveSession,
        step_index: int,
        write_report: MeshingWriteReport | None,
        read_report: MeshingReadReport | None,
    ) -> MeshingLiveStepReport:
        failed = (
            (write_report is not None and write_report.status == "failed")
            or (read_report is not None and read_report.status == "failed")
            or session.steps[step_index].status == "failed"
        )
        return MeshingLiveStepReport(
            status="failed" if failed else "success",
            message=session.steps[step_index].message,
            snapshot=self._snapshot(session),
            step_index=step_index,
            task_path=session.steps[step_index].task_path,
            write_report=write_report,
            read_report=read_report,
        )

    def _log(
        self,
        session: _LiveSession,
        level: Literal["info", "success", "warning", "error"],
        message: str,
        model_id: int | None = None,
    ) -> None:
        with self._log_lock:
            session.logs.append(
                MeshingLiveLogEntry(
                    sequence=session.next_log_sequence,
                    timestamp=utc_now(),
                    level=level,
                    message=message,
                    model_id=model_id,
                )
            )
            session.next_log_sequence += 1

    def _ingest_transcript(
        self,
        session: _LiveSession,
        text: str,
        on_native_surface_mesh_complete: Callable[[], None] | None = None,
    ) -> None:
        previous_tail = session.transcript_tail
        combined = previous_tail + text.replace("\r", "\n")
        session.transcript_tail = combined[-2048:]
        normalized = combined.casefold()
        for line in text.replace("\r", "\n").splitlines():
            cleaned = line.strip()
            if cleaned:
                self._log(
                    session,
                    "info",
                    cleaned,
                    self._current_model(session).model_id,
                )

        model_stem = Path(self._current_model(session).file_path).stem.casefold()
        surface_start_marker = "remeshing..."
        surface_start = normalized.rfind(surface_start_marker)
        surface_start_is_new = (
            surface_start >= 0
            and surface_start + len(surface_start_marker) > len(previous_tail)
        )
        if surface_start_is_new and session.phase == "surface_ready":
            self._set_phase(
                session,
                "generating_surface",
                "检测到 Fluent 原生界面正在生成面网格。",
            )
            session.status = "running"
            self._log(
                session,
                "info",
                "检测到 Fluent 原生界面正在生成面网格。",
                self._current_model(session).model_id,
            )

        surface_marker = "surface meshing of"
        completion_marker = "complete in"
        surface_start = normalized.rfind(surface_marker)
        completion_start = normalized.find(completion_marker, surface_start)
        completion_is_new = (
            completion_start >= 0
            and completion_start + len(completion_marker) > len(previous_tail)
        )
        if (
            surface_start >= 0
            and completion_is_new
            and model_stem
            and model_stem in normalized[surface_start:completion_start]
        ):
            with self._phase_lock:
                if session.phase in {"surface_ready", "generating_surface"}:
                    session.native_surface_mesh_transcript_success = True
                    confirmed = True
                else:
                    confirmed = False
            if confirmed and on_native_surface_mesh_complete is not None:
                on_native_surface_mesh_complete()

    @staticmethod
    def _error_message(error: Exception) -> str:
        message = f"{type(error).__name__}: {error}"
        diagnostic = repr(error)
        return f"{message} (diagnostic: {diagnostic})" if diagnostic != str(error) else message

    @staticmethod
    def _friendly_start_error(message: str, file_path: str) -> str:
        if "Discovery" in message or "CAD Import" in message or "CAD Readers" in message:
            return (
                f"几何导入失败: {file_path}。当前 CAD/Discovery 读取器未能启动。"
                "请确认 ANSYS CAD Configuration Manager 已配置 SpaceClaim/Discovery, "
                "或先将模型另存为 .pmdb、STEP 后再导入。"
            )
        return message
