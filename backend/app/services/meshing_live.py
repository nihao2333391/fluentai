"""In-memory orchestration for interactive Fluent Meshing workflow sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from app.database import Database
from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingArgumentReference,
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


class MeshingLiveManager:
    """Coordinate one interactive Meshing session and its model queue."""

    def __init__(self, database: Database, adapter: MeshingWorkflowAdapter) -> None:
        self.database = database
        self.adapter = adapter
        self._sessions: dict[str, _LiveSession] = {}
        self._log_lock = RLock()

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
            steps=[MeshingLiveStepState(task_path=[name]) for name in WATERTIGHT_LIVE_STEPS],
            preset_items=list(automation.preset.items),
            reuse_connection=reuse_connection,
        )
        self._sessions[session.session_id] = session
        self._log(session, "info", f"正在启动 Fluent Meshing: {automation.name}")
        return self._snapshot(session)

    def begin(self, session_id: str) -> None:
        session = self._require(session_id)
        try:
            if session.reuse_connection:
                status = self.adapter.status()
                if not status.connected:
                    raise RuntimeError("Existing Fluent Meshing session is no longer connected.")
            else:
                status = self.adapter.connect(session.connection_config)
            session.connection_status = status
            session.steps[0].status = "active"
            session.current_step_index = 0
            session.status = "waiting"
            session.message = "Fluent Meshing 已连接, 请执行导入几何模型。"
            self._log(session, "success", session.message)
            self.adapter.register_transcript_callback(
                lambda text: self._ingest_transcript(session, text)
            )
        except Exception as exc:
            model = self._current_model(session)
            session.status = "failed"
            session.message = self._friendly_start_error(self._error_message(exc), model.file_path)
            model.status = "failed"
            model.error = session.message
            session.steps[0].status = "failed"
            session.steps[0].message = session.message
            self._log(session, "error", session.message, model.model_id)

    def get(self, session_id: str) -> MeshingLiveSessionSnapshot:
        return self._snapshot(self._require(session_id))

    def enter_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._select_step(session, step_index)
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
        failed = (write_report is not None and write_report.status == "failed") or (
            read_report.status == "failed"
        )
        session.steps[step_index].status = "failed" if failed else "active"
        session.steps[step_index].message = (
            (write_report.error if write_report else None) or read_report.error or ""
        )
        session.status = "failed" if failed else "waiting"
        session.message = session.steps[step_index].message
        return self._step_report(session, step_index, write_report, read_report)

    def read_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._require_step(session, step_index)
        return self._step_report(session, step_index, None, self._read_step(session, step_index))

    def write_step(
        self,
        session_id: str,
        step_index: int,
        items: list[MeshingPresetItem],
    ) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._select_step(session, step_index)
        write_report = self.adapter.write_arguments(
            MeshingWriteRequest(
                workflow_type=session.workflow_type,
                items=items,
                verify=True,
                create_compound_child=True,
            )
        )
        self._track_children(session, items)
        read_report = self._read_step(session, step_index)
        failed = write_report.status == "failed" or read_report.status == "failed"
        session.steps[step_index].status = "failed" if failed else "active"
        session.steps[step_index].message = (
            write_report.error or read_report.error or "参数已写入 Fluent 并回读。"
        )
        session.status = "failed" if failed else "waiting"
        self._log(
            session,
            "error" if failed else "success",
            session.steps[step_index].message,
            self._current_model(session).model_id,
        )
        return self._step_report(session, step_index, write_report, read_report)

    def execute_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        session = self._require(session_id)
        self._select_step(session, step_index)
        if step_index == 0:
            return self._execute_import_step(session)
        task_path = session.steps[step_index].task_path
        session.steps[step_index].status = "running"
        session.status = "running"
        model = self._current_model(session)
        self._log(session, "info", f"正在执行: {'/'.join(task_path)}", model.model_id)
        execution = self.adapter.execute_task(session.workflow_type, task_path)
        for line in execution.output:
            self._log(session, "info", line, model.model_id)
        read_report = self._read_step(session, step_index)
        if execution.status == "success":
            session.steps[step_index].status = "completed"
            session.steps[step_index].message = execution.message
            self._log(session, "success", execution.message, model.model_id)
            if step_index == len(WATERTIGHT_LIVE_STEPS) - 1:
                model.status = "completed"
                session.status = (
                    "completed"
                    if session.current_model_index == len(session.models) - 1
                    else "waiting"
                )
                session.message = f"{model.name} 的 7 步工作流程已完成。"
            else:
                session.current_step_index = step_index + 1
                session.status = "waiting"
                session.message = f"已切换到下一步: {session.steps[step_index + 1].task_path[-1]}"
        else:
            session.steps[step_index].status = "failed"
            session.steps[step_index].message = execution.message
            session.status = "failed"
            session.message = execution.message
            model.status = "failed"
            model.error = execution.message
            self._log(session, "error", execution.message, model.model_id)
        return self._step_report(session, step_index, None, read_report)

    def _execute_import_step(self, session: _LiveSession) -> MeshingLiveStepReport:
        model = self._current_model(session)
        session.steps[0].status = "running"
        session.status = "running"
        self._log(session, "info", f"正在执行导入几何模型: {model.name}", model.model_id)
        try:
            self.adapter.reset_workflow(session.workflow_type)
            self._import_current_model(session)
            read_report = self._read_step(session, 0)
            return self._step_report(session, 0, None, read_report)
        except Exception as exc:
            message = self._friendly_start_error(self._error_message(exc), model.file_path)
            session.steps[0].status = "failed"
            session.steps[0].message = message
            session.status = "failed"
            session.message = message
            model.status = "failed"
            model.error = message
            self._log(session, "error", message, model.model_id)
            return self._step_report(session, 0, None, None)

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
            self.adapter.unregister_transcript_callback()
            self.adapter.disconnect()
        finally:
            session.connection_status = FluentStatus(connected=False, mode=None)
            session.status = "stopped"
            session.message = "实时 Meshing 会话已停止。"
            self._log(session, "warning", session.message)
        return self._snapshot(session)

    def _switch_model(self, session: _LiveSession, index: int) -> MeshingLiveSessionSnapshot:
        session.current_model_index = index
        session.current_step_index = 0
        session.status = "connected"
        session.message = "正在切换模型。"
        for step in session.steps:
            step.status = "pending"
            step.message = ""
        for model_index, model in enumerate(session.models):
            if model_index < index and model.status != "failed":
                model.status = "completed"
        try:
            self.adapter.reset_workflow(session.workflow_type)
            session.connection_status = self.adapter.status()
            current = self._current_model(session)
            current.status = "pending"
            current.error = None
            session.current_step_index = 0
            session.steps[0].status = "active"
            session.status = "waiting"
            session.message = f"已切换到 {current.name}, 请执行导入几何模型。"
            self._log(session, "success", session.message, current.model_id)
        except Exception as exc:
            model = self._current_model(session)
            model.status = "failed"
            model.error = self._error_message(exc)
            session.status = "failed"
            session.message = model.error
            self._log(session, "error", model.error, model.model_id)
        return self._snapshot(session)

    def _import_current_model(self, session: _LiveSession) -> None:
        model = self._current_model(session)
        model.status = "importing"
        session.steps[0].status = "running"
        session.status = "running"
        self._log(session, "info", f"正在导入几何: {model.name}", model.model_id)
        preset = MeshingPresetDocument(
            schema_version=1,
            fluent_version="25.2.0",
            workflow_type=session.workflow_type,
            items=[item for item in session.preset_items if item.task_path == ["import_geometry"]],
        )
        report = self.adapter.apply_preset(preset, model.file_path, import_geometry=True)
        if report.status != "success":
            raise RuntimeError(report.error or "几何导入失败。")
        model.status = "ready"
        model.error = None
        session.steps[0].status = "completed"
        session.steps[0].message = "几何已导入。"
        session.current_step_index = 1
        session.status = "waiting"
        session.message = f"已导入 {model.name}, 可以开始添加局部尺寸。"
        self._log(session, "success", session.message, model.model_id)

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
        return self.adapter.read_arguments(
            MeshingReadRequest(workflow_type=session.workflow_type, items=references)
        )

    def _read_references(
        self,
        session: _LiveSession,
        task: dict[str, Any],
        task_path: list[str],
    ) -> list[MeshingArgumentReference]:
        references = self._argument_references(task.get("arguments") or [], task_path)
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
        return [item for item in session.preset_items if item.task_path == task_path]

    def _select_step(self, session: _LiveSession, step_index: int) -> None:
        self._require_step(session, step_index)
        session.current_step_index = step_index
        for index in range(step_index + 1, len(session.steps)):
            if session.steps[index].status == "completed":
                session.steps[index].status = "pending"
                session.steps[index].message = ""

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
        return MeshingLiveSessionSnapshot(
            session_id=session.session_id,
            automation_id=session.automation_id,
            automation_name=session.automation_name,
            workflow_type=session.workflow_type,
            status=session.status,
            connection=session.connection_status,
            models=session.models,
            current_model_index=session.current_model_index,
            current_step_index=session.current_step_index,
            steps=session.steps,
            logs=session.logs[-200:],
            message=session.message,
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

    def _ingest_transcript(self, session: _LiveSession, text: str) -> None:
        for line in text.replace("\r", "\n").splitlines():
            cleaned = line.strip()
            if cleaned:
                self._log(
                    session,
                    "info",
                    cleaned,
                    self._current_model(session).model_id,
                )

    @staticmethod
    def _error_message(error: Exception) -> str:
        return f"{type(error).__name__}: {error}"

    @staticmethod
    def _friendly_start_error(message: str, file_path: str) -> str:
        if "Discovery" in message or "CAD Import" in message or "CAD Readers" in message:
            return (
                f"几何导入失败: {file_path}。当前 CAD/Discovery 读取器未能启动。"
                "请确认 ANSYS CAD Configuration Manager 已配置 SpaceClaim/Discovery, "
                "或先将模型另存为 .pmdb、STEP 后再导入。"
            )
        return message
