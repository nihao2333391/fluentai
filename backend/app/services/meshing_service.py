"""Coordinated Meshing preset application with jobs and sync logs."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from threading import Lock, Timer
from typing import Any, Protocol, cast
from uuid import uuid4

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
    MeshingReadReport,
    MeshingReadRequest,
    MeshingReferenceInspection,
    MeshingTaskDeleteReport,
    MeshingTaskHistoryRead,
    MeshingTaskRead,
    MeshingWorkflowReport,
    MeshingWriteReport,
    MeshingWriteRequest,
    SyncLogCreate,
)
from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.factory import SessionAdapterFactory, SharedAdapterFactory
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_plan import watertight_steps
from app.repositories.common import utc_now
from app.repositories.jobs import JobRepository
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.meshing_tasks import MeshingTaskRepository
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

TASK_TERMINAL_STATUSES = {"completed", "failed", "stopped"}


class MeshingAdapterBusyError(RuntimeError):
    """A Fluent call is active or unresponsive, so the service will not queue more work."""


class _ExitableAdapter(Protocol):
    """Optional exit hook implemented by worker-backed session adapters."""

    on_exit: Callable[[], None] | None


@dataclass
class _ActiveSlot:
    """One live session that currently occupies a Fluent parallel slot."""

    session_id: str
    processor_count: int
    endpoint_key: tuple[str, str, int | None, str | None] | None


class _AdapterRuntime:
    """Serializes Fluent calls and tracks busy state for one adapter lane.

    Sessions backed by the shared adapter all share one runtime (the legacy
    single-Fluent behaviour). Sessions backed by worker subprocesses each get
    their own runtime so a stuck or slow task cannot block the others.
    """

    def __init__(self, name: str) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
        self.state_lock = Lock()
        self.live_start_futures: dict[str, Future[None]] = {}
        self.native_poll: dict[str, Future[None]] = {}
        self.native_poll_timers: dict[str, Timer] = {}
        self.native_task_change: dict[str, Future[None]] = {}
        self.active_adapter_future: Future[object] | None = None
        self.adapter_unresponsive = False


class MeshingService:
    """Own the Meshing adapter sessions and persist apply activity."""

    def __init__(
        self,
        database: Database,
        adapter: MeshingWorkflowAdapter,
        *,
        live_phase_timeout_seconds: float = 180.0,
        live_hard_timeout_seconds: float = 900.0,
        session_adapter_factory: SessionAdapterFactory | None = None,
        max_parallel_sessions: int = 1,
    ) -> None:
        self.database = database
        self.adapter = adapter
        self.tasks = MeshingTaskRepository(database)
        self.tasks.backfill_legacy_archives()
        self.tasks.mark_running_interrupted()
        self._session_factory: SessionAdapterFactory = (
            session_adapter_factory or SharedAdapterFactory(adapter)
        )
        self._default_max_parallel = max(1, max_parallel_sessions)
        self.live = MeshingLiveManager(
            database,
            adapter,
            phase_timeout_seconds=live_phase_timeout_seconds,
            phase_hard_timeout_seconds=live_hard_timeout_seconds,
        )
        self._last_connection_config: FluentConnectionConfig | None = None
        self._runtime_primary = _AdapterRuntime("meshing-adapter")
        self._session_runtimes: dict[str, _AdapterRuntime] = {}
        self._session_adapters: dict[str, MeshingWorkflowAdapter] = {}
        self._live_queue_lock = Lock()
        self._queued_live_session_ids: list[str] = []
        self._active_live_sessions: dict[str, _ActiveSlot] = {}
        self._native_poll_timeout_seconds = max(0.05, min(30.0, live_phase_timeout_seconds))

    # ------------------------------------------------------------------
    # adapter lanes
    # ------------------------------------------------------------------

    def set_session_adapter_factory(self, factory: SessionAdapterFactory) -> None:
        """Swap in the per-session adapter strategy (e.g. subprocess workers)."""
        self._session_factory = factory

    # Compatibility accessors for the legacy shared-adapter lane. Tests and
    # older call sites reach these names directly; in shared mode every session
    # runs on this lane, so the semantics match the previous single-adapter
    # implementation exactly.
    @property
    def _executor(self) -> ThreadPoolExecutor:
        return self._runtime_primary.executor

    @property
    def _operation_state_lock(self) -> Lock:
        return self._runtime_primary.state_lock

    @property
    def _live_start_futures(self) -> dict[str, Future[None]]:
        return self._runtime_primary.live_start_futures

    @property
    def _native_poll(self) -> dict[str, Future[None]]:
        return self._runtime_primary.native_poll

    @property
    def _adapter_unresponsive(self) -> bool:
        return self._runtime_primary.adapter_unresponsive

    @_adapter_unresponsive.setter
    def _adapter_unresponsive(self, value: bool) -> None:
        self._runtime_primary.adapter_unresponsive = value

    @property
    def _active_adapter_future(self) -> Future[object] | None:
        return self._runtime_primary.active_adapter_future

    @_active_adapter_future.setter
    def _active_adapter_future(self, value: Future[object] | None) -> None:
        self._runtime_primary.active_adapter_future = value

    def _runtime_for(self, session_id: str | None) -> _AdapterRuntime:
        if session_id is None or self._session_factory.reusable:
            return self._runtime_primary
        runtime = self._session_runtimes.get(session_id)
        if runtime is None:
            runtime = _AdapterRuntime(f"meshing-{session_id[:8]}")
            self._session_runtimes[session_id] = runtime
        return runtime

    def _session_adapter(self, session_id: str) -> MeshingWorkflowAdapter:
        return self._session_adapters.get(session_id, self.adapter)

    def _run[T](
        self,
        operation: Callable[[], T],
        *,
        timeout_seconds: float | None = 180.0,
        session_id: str | None = None,
        operation_name: str = "Fluent Meshing 操作",
    ) -> T:
        runtime = self._runtime_for(session_id)
        effective_timeout_seconds = (
            self.live.phase_hard_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        with runtime.state_lock:
            if runtime.adapter_unresponsive:
                raise MeshingAdapterBusyError(
                    "Fluent 前一次调用超时，平台已停止提交新请求。"
                    "请检查 Fluent 控制台并重启 Fluent AI 后再连接。"
                )
            if any(not future.done() for future in runtime.live_start_futures.values()):
                raise MeshingAdapterBusyError(
                    "Fluent 正在自动准备当前模型。平台会继续轮询步骤状态，请勿重复提交操作。"
                )
            if any(not future.done() for future in runtime.native_poll.values()):
                raise MeshingAdapterBusyError(
                    "Fluent 当前步骤查询仍未返回。平台没有重复提交参数读写请求。"
                )
            active_future = runtime.active_adapter_future
            if active_future is not None and not active_future.done():
                raise MeshingAdapterBusyError("Fluent 正在处理前一项请求。平台没有重复提交新请求。")
            future: Future[T] = runtime.executor.submit(operation)
            runtime.active_adapter_future = future  # type: ignore[assignment]
        try:
            return future.result(timeout=effective_timeout_seconds)
        except FutureTimeoutError as exc:
            elapsed_limit = effective_timeout_seconds
            with runtime.state_lock:
                runtime.adapter_unresponsive = True
            if session_id is not None:
                self.live.fail_unresponsive_operation(session_id, operation_name, elapsed_limit)
            raise MeshingAdapterBusyError(
                f"{operation_name}连续 {elapsed_limit:g} 秒没有返回。"
                "平台已停止提交后续请求；当前 Fluent 请求无法被安全中断，请检查 Fluent 控制台。"
            ) from exc
        finally:
            if future.done():
                self._clear_active_adapter_future(runtime, future)
            else:
                future.add_done_callback(
                    lambda completed: self._clear_active_adapter_future(runtime, completed)
                )

    @staticmethod
    def _clear_active_adapter_future(runtime: _AdapterRuntime, future: Future[Any]) -> None:
        with runtime.state_lock:
            if runtime.active_adapter_future is future:
                runtime.active_adapter_future = None
                runtime.adapter_unresponsive = False

    # ------------------------------------------------------------------
    # connection helpers
    # ------------------------------------------------------------------

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

    def _disconnect_impl(self) -> FluentStatus:
        self.adapter.disconnect()
        self._last_connection_config = None
        return self.adapter.status()

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

    # ------------------------------------------------------------------
    # live session scheduling
    # ------------------------------------------------------------------

    def start_live_session(self, payload: MeshingLiveSessionStart) -> MeshingLiveSessionSnapshot:
        config = payload.connection or self.default_connection_config()
        if payload.connection is None and config.mode == "launch":
            config = config.model_copy(update={"ui_mode": "gui"})
        reusable = self._session_factory.reusable
        reuse_connection = False
        if reusable:
            with self._live_queue_lock:
                fluent_is_reserved = bool(self._active_live_sessions) or bool(
                    self._queued_live_session_ids
                )
            if not fluent_is_reserved:
                current_status = self._run(self.adapter.status)
                reuse_connection = bool(
                    payload.connection is None
                    and current_status.connected
                    and self._last_connection_config is not None
                    and self._last_connection_config.mode == config.mode
                    and self._last_connection_config.ui_mode == "gui"
                )

        session_id = str(uuid4())
        task_id = str(uuid4())
        run_dir = self._create_run_dir(task_id)
        session_adapter = self._session_factory.create(session_id=session_id, run_dir=run_dir)
        self._session_adapters[session_id] = session_adapter
        if hasattr(session_adapter, "on_exit"):
            exitable = cast("_ExitableAdapter", session_adapter)
            exitable.on_exit = lambda: self._on_session_adapter_exit(session_id)

        snapshot = self.live.start(
            payload.automation_id,
            payload.model_ids,
            config,
            reuse_connection,
            adapter=session_adapter,
            session_id=session_id,
            task_id=task_id,
            run_dir=run_dir,
        )
        automation = MeshingAutomationRepository(self.database).get(payload.automation_id)
        preset = MeshingAutomationRepository(self.database).preset_revision(
            payload.automation_id, automation.published_revision or automation.revision
        )
        models = [ModelRepository(self.database).get(model_id) for model_id in payload.model_ids]
        self.tasks.create(
            snapshot.task_id,
            automation.id,
            automation.name,
            automation.published_revision or automation.revision,
            preset.model_dump(mode="json"),
            [self._model_snapshot(model) for model in models],
            snapshot.session_id,
        )
        with self._live_queue_lock:
            self._queued_live_session_ids.append(snapshot.session_id)
        active_snapshot = self._start_queued_live_sessions(snapshot.session_id)
        return active_snapshot or snapshot

    def _start_queued_live_sessions(
        self, target_session_id: str | None = None
    ) -> MeshingLiveSessionSnapshot | None:
        """Admit queued sessions into free parallel slots.

        The scan skips candidates that are temporarily blocked (attach
        endpoint already in use or processor budget exhausted) so they do not
        hold up later sessions that could run right away.
        """
        started_snapshot: MeshingLiveSessionSnapshot | None = None
        admissions: list[str] = []
        with self._live_queue_lock:
            for candidate_id in list(self._queued_live_session_ids):
                if len(self._active_live_sessions) >= self._effective_max_parallel():
                    break
                config = self.live.connection_config(candidate_id)
                endpoint_key = self._endpoint_key(config)
                if endpoint_key is not None and any(
                    slot.endpoint_key == endpoint_key
                    for slot in self._active_live_sessions.values()
                ):
                    continue
                if not self._budget_allows(config.processor_count):
                    continue
                self._active_live_sessions[candidate_id] = _ActiveSlot(
                    session_id=candidate_id,
                    processor_count=config.processor_count,
                    endpoint_key=endpoint_key,
                )
                admissions.append(candidate_id)
            for candidate_id in admissions:
                self._queued_live_session_ids.remove(candidate_id)
        for candidate_id in admissions:
            snapshot = self.live.activate(candidate_id)
            self.tasks.sync(snapshot)
            if candidate_id == target_session_id:
                started_snapshot = snapshot
            runtime = self._runtime_for(candidate_id)
            future = runtime.executor.submit(
                self._begin_queued_live_session,
                candidate_id,
                self._native_task_change_handler(candidate_id),
                self._native_poll_handler(candidate_id),
            )
            with runtime.state_lock:
                runtime.live_start_futures[candidate_id] = future
            future.add_done_callback(partial(self._observe_live_start, candidate_id))
        return started_snapshot

    def _native_task_change_handler(self, session_id: str) -> Callable[[str], None]:
        return lambda task_name: self._schedule_native_task_change(session_id, task_name)

    def _native_poll_handler(self, session_id: str) -> Callable[[], None]:
        return lambda: self._schedule_native_poll(session_id)

    def _begin_queued_live_session(
        self,
        session_id: str,
        on_native_task: Callable[[str], None],
        on_native_surface_mesh_complete: Callable[[], None],
    ) -> None:
        # The adapter check runs only when this task reaches the head of the queue.
        # A prior task may have connected Fluent after this request was accepted.
        session_adapter = self._session_adapter(session_id)
        current_status = session_adapter.status()
        current_config = self.live.connection_config(session_id)
        can_reuse = bool(
            current_status.connected
            and self._last_connection_config is not None
            and current_config.mode == self._last_connection_config.mode
            and current_config.ui_mode == self._last_connection_config.ui_mode
        )
        self.live.set_reuse_connection(session_id, can_reuse)
        self.live.begin(session_id, on_native_task, on_native_surface_mesh_complete)
        if session_adapter.status().connected:
            self._last_connection_config = current_config

    def _sync_task_and_advance(self, snapshot: MeshingLiveSessionSnapshot) -> None:
        self.tasks.sync(snapshot)
        if snapshot.status not in TASK_TERMINAL_STATUSES:
            return
        self._release_session(snapshot.session_id, dispose_worker=snapshot.status == "stopped")
        self._start_queued_live_sessions()

    def _release_session(self, session_id: str, *, dispose_worker: bool) -> None:
        with self._live_queue_lock:
            self._active_live_sessions.pop(session_id, None)
            self._queued_live_session_ids = [
                item for item in self._queued_live_session_ids if item != session_id
            ]
            adapter = self._session_adapters.get(session_id)
        if dispose_worker and adapter is not None:
            self._session_factory.dispose(adapter)

    def _observe_live_start(self, session_id: str, future: Future[None]) -> None:
        try:
            error = future.exception()
        except BaseException as exc:
            error = exc
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            runtime.live_start_futures.pop(session_id, None)
        if error is not None:
            self.live.fail_background_start(session_id, error)
        self._sync_task_and_advance(self.live.get(session_id))

    def _on_session_adapter_exit(self, session_id: str) -> None:
        """Fail the owning task when its worker process dies unexpectedly."""
        try:
            current = self.live.get(session_id)
        except Exception:
            return
        if current.status in TASK_TERMINAL_STATUSES or current.status == "queued":
            return
        self.live.fail_background_start(
            session_id,
            RuntimeError("独立 Fluent 工作进程已退出，任务无法继续执行。请重新创建任务。"),
        )
        self._sync_task_and_advance(self.live.get(session_id))

    def _effective_max_parallel(self) -> int:
        configured = self._read_setting_int(
            "meshing_max_parallel_sessions", self._default_max_parallel
        )
        return max(1, min(configured, self._session_factory.max_sessions))

    def _budget_allows(self, processor_count: int) -> bool:
        budget = self._read_setting_int("meshing_processor_budget", 0)
        if budget <= 0:
            return True
        used = sum(slot.processor_count for slot in self._active_live_sessions.values())
        return used + processor_count <= budget

    def _read_setting_int(self, key: str, default: int) -> int:
        try:
            values = SettingsRepository(self.database).get_all()
        except Exception:
            return default
        raw = str(values.get(key, "")).strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    @staticmethod
    def _endpoint_key(
        config: FluentConnectionConfig,
    ) -> tuple[str, str, int | None, str | None] | None:
        if config.mode != "attach":
            return None
        return ("attach", config.host, config.port, config.server_info_file)

    def _create_run_dir(self, task_id: str) -> Path:
        run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
        run_dir = self.database.path.parent / "meshing-results" / task_id / run_id
        for name in ("input", "fluent-work", "mesh", "logs", "report"):
            (run_dir / name).mkdir(parents=True, exist_ok=True)
        return run_dir

    @staticmethod
    def _model_snapshot(model: object) -> dict[str, object]:
        raw_path = str(getattr(model, "file_path", ""))
        path = Path(raw_path).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        file_size: int | None = None
        modified_at: str | None = None
        try:
            stat = resolved.stat()
        except OSError:
            stat = None
        if stat is not None:
            file_size = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
        return {
            "id": getattr(model, "id", None),
            "name": getattr(model, "name", ""),
            "file_path": raw_path,
            "resolved_path": str(resolved),
            "file_size": file_size,
            "modified_at": modified_at,
        }

    # ------------------------------------------------------------------
    # native step polling
    # ------------------------------------------------------------------

    def _schedule_native_task_change(self, session_id: str, task_name: str) -> None:
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            pending = runtime.native_task_change.get(session_id)
            if pending is not None and not pending.done():
                return
            if any(not start.done() for start in runtime.live_start_futures.values()):
                return
            if runtime.adapter_unresponsive or (
                runtime.active_adapter_future is not None
                and not runtime.active_adapter_future.done()
            ):
                return
            future = runtime.executor.submit(self.live.native_task_changed, session_id, task_name)
            runtime.native_task_change[session_id] = future
            runtime.active_adapter_future = future  # type: ignore[assignment]
        future.add_done_callback(
            lambda completed: self._observe_native_task_change(session_id, completed)
        )

    def _observe_native_task_change(self, session_id: str, future: Future[None]) -> None:
        try:
            error = future.exception()
        except BaseException as exc:
            error = exc
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            if runtime.native_task_change.get(session_id) is future:
                runtime.native_task_change.pop(session_id, None)
            if runtime.active_adapter_future is future:
                runtime.active_adapter_future = None
                runtime.adapter_unresponsive = False
        if error is not None:
            self.live.fail_background_task_change(session_id, error)

    def get_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        snapshot = self.live.get(session_id)
        self.tasks.sync(snapshot)
        should_poll_native_task = snapshot.status in {"waiting", "connected"} or (
            snapshot.status == "running" and snapshot.phase == "generating_surface"
        )
        if should_poll_native_task and self.live.native_task_poll_required(session_id):
            self._schedule_native_poll(session_id)
        return snapshot

    def _schedule_native_poll(self, session_id: str) -> None:
        future: Future[None] | None = None
        timeout_timer: Timer | None = None
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            pending = runtime.native_poll.get(session_id)
            if pending is not None and not pending.done():
                return
            if any(not start.done() for start in runtime.live_start_futures.values()):
                return
            if runtime.adapter_unresponsive or (
                runtime.active_adapter_future is not None
                and not runtime.active_adapter_future.done()
            ):
                return
            future = runtime.executor.submit(self.live.poll_native_step, session_id)
            runtime.native_poll[session_id] = future
            runtime.active_adapter_future = future  # type: ignore[assignment]
            timeout_timer = Timer(
                self._native_poll_timeout_seconds,
                self._expire_native_poll,
                args=(session_id, future, self._native_poll_timeout_seconds),
            )
            timeout_timer.daemon = True
            runtime.native_poll_timers[session_id] = timeout_timer
            timeout_timer.start()
        future.add_done_callback(lambda completed: self._observe_native_poll(session_id, completed))

    def _expire_native_poll(
        self, session_id: str, future: Future[None], timeout_seconds: float
    ) -> None:
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            if runtime.native_poll.get(session_id) is not future or future.done():
                return
            runtime.adapter_unresponsive = True
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
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            timer = runtime.native_poll_timers.pop(session_id, None)
            if timer is not None:
                timer.cancel()
            if runtime.native_poll.get(session_id) is future:
                runtime.native_poll.pop(session_id, None)
            if runtime.active_adapter_future is future:
                runtime.active_adapter_future = None
                runtime.adapter_unresponsive = False
        if error is not None:
            self.live.native_task_poll_failed(session_id, error)
        else:
            self.live.native_task_poll_succeeded(session_id)

    # ------------------------------------------------------------------
    # live step operations
    # ------------------------------------------------------------------

    def enter_live_step(
        self, session_id: str, payload: MeshingLiveStepRequest
    ) -> MeshingLiveStepReport:
        return self._run(
            lambda: self.live.enter_step(session_id, payload.step_index),
            session_id=session_id,
            operation_name="写入并读取 Fluent 步骤参数",
        )

    def read_live_step(self, session_id: str, step_index: int) -> MeshingLiveStepReport:
        # The UI asks for the session and current step in one refresh cycle.
        # get_live_session() may have scheduled a native task poll just before
        # this read. Wait for that read-only poll to finish, then retry the
        # guard in _run() in case another refresh scheduled a poll in between.
        while True:
            runtime = self._runtime_for(session_id)
            with runtime.state_lock:
                pending_poll = runtime.native_poll.get(session_id)
                if pending_poll is not None and pending_poll.done():
                    pending_poll = None
            if pending_poll is not None:
                try:
                    pending_poll.result(timeout=min(self._native_poll_timeout_seconds, 10.0))
                except FutureTimeoutError as exc:
                    raise MeshingAdapterBusyError(
                        "Fluent 当前步骤查询仍未返回。平台继续等待当前查询，没有重复读取参数。"
                    ) from exc
                except Exception:
                    # The poll observer records this failure. Parameter reads
                    # may still work, so allow the normal read to try next.
                    pass
            try:
                return self._run(
                    lambda: self.live.read_step(session_id, step_index),
                    session_id=session_id,
                    operation_name="读取 Fluent 步骤参数",
                )
            except MeshingAdapterBusyError:
                # A second refresh may have scheduled a poll just after the
                # wait above. Retry only when that exact read-only poll exists;
                # other busy states must continue to block this request.
                with runtime.state_lock:
                    pending_poll = runtime.native_poll.get(session_id)
                    if pending_poll is None or pending_poll.done():
                        raise

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
        report = self._run(
            lambda: self.live.execute_step(session_id, payload.step_index),
            timeout_seconds=None,
            session_id=session_id,
            operation_name="执行 Fluent 工作流步骤",
        )
        self._sync_task_and_advance(report.snapshot)
        return report

    def retry_live_preparation(self, session_id: str) -> MeshingLiveSessionSnapshot:
        snapshot = self._run(
            lambda: self._retry_live_preparation_impl(session_id),
            session_id=session_id,
            operation_name="重试 Fluent 自动准备",
        )
        self._sync_task_and_advance(snapshot)
        return snapshot

    def _retry_live_preparation_impl(self, session_id: str) -> MeshingLiveSessionSnapshot:
        session = self.live.get(session_id)
        if session.phase != "failed":
            return session
        if session.status == "stopped":
            raise ValueError("已停止的实时 Meshing 会话不能重试。")

        self._ensure_session_slot(session_id)
        session_adapter = self._session_adapter(session_id)
        try:
            if not session_adapter.status().connected:
                config = self.live.connection_config(session_id)
                status = session_adapter.connect(config)
                if not status.connected:
                    raise RuntimeError("Fluent Meshing 重连后仍未就绪。")
                self._last_connection_config = config
            return self.live.retry_prepare(session_id)
        except Exception as exc:
            self.live.fail_background_start(session_id, exc)
            return self.live.get(session_id)

    def _ensure_session_slot(self, session_id: str) -> None:
        """Re-acquire a Fluent slot for a terminal session that is being retried."""
        with self._live_queue_lock:
            if session_id in self._active_live_sessions:
                return
            config = self.live.connection_config(session_id)
            endpoint_key = self._endpoint_key(config)
            blocked = (
                len(self._active_live_sessions) >= self._effective_max_parallel()
                or bool(self._queued_live_session_ids)
                or not self._budget_allows(config.processor_count)
                or (
                    endpoint_key is not None
                    and any(
                        slot.endpoint_key == endpoint_key
                        for slot in self._active_live_sessions.values()
                    )
                )
            )
            if blocked:
                raise MeshingAdapterBusyError("Fluent 正在处理其他任务，请等待当前任务结束后重试。")
            self._active_live_sessions[session_id] = _ActiveSlot(
                session_id=session_id,
                processor_count=config.processor_count,
                endpoint_key=endpoint_key,
            )

    def next_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        snapshot = self._run(
            lambda: self.live.next_model(session_id),
            session_id=session_id,
            operation_name="切换 Fluent 几何模型",
        )
        self._sync_task_and_advance(snapshot)
        return snapshot

    def retry_live_model(self, session_id: str) -> MeshingLiveSessionSnapshot:
        snapshot = self._run(
            lambda: self._retry_live_model_impl(session_id),
            session_id=session_id,
            operation_name="重新导入 Fluent 几何模型",
        )
        self._sync_task_and_advance(snapshot)
        return snapshot

    def _retry_live_model_impl(self, session_id: str) -> MeshingLiveSessionSnapshot:
        self._ensure_session_slot(session_id)
        return self.live.retry_model(session_id)

    def stop_live_session(self, session_id: str) -> MeshingLiveSessionSnapshot:
        current = self.live.get(session_id)
        if current.status == "queued":
            snapshot = self._run(lambda: self.live.stop_queued(session_id))
            self._sync_task_and_advance(snapshot)
            return snapshot
        runtime = self._runtime_for(session_id)
        with runtime.state_lock:
            live_start_pending = any(
                not future.done() for future in runtime.live_start_futures.values()
            )
            adapter_call_pending = (
                runtime.active_adapter_future is not None
                and not runtime.active_adapter_future.done()
            )
            adapter_unresponsive = runtime.adapter_unresponsive
        if live_start_pending or adapter_call_pending or adapter_unresponsive:
            snapshot = self.live.stop_background_tracking(session_id)
        else:
            snapshot = self._run(lambda: self.live.stop(session_id), session_id=session_id)
        self._sync_task_and_advance(snapshot)
        return snapshot

    def shutdown(self) -> None:
        """Release every worker subprocess and runtime lane."""
        with self._live_queue_lock:
            adapters = list(self._session_adapters.values())
            self._session_adapters.clear()
        for adapter in adapters:
            with contextlib.suppress(Exception):
                self._session_factory.dispose(adapter)
        self._runtime_primary.executor.shutdown(wait=False, cancel_futures=True)
        for runtime in self._session_runtimes.values():
            for timer in runtime.native_poll_timers.values():
                timer.cancel()
            runtime.executor.shutdown(wait=False, cancel_futures=True)
        self._session_runtimes.clear()

    # ------------------------------------------------------------------
    # tasks and archives
    # ------------------------------------------------------------------

    def list_meshing_tasks(self, include_deleted: bool = False) -> list[MeshingTaskRead]:
        return self.tasks.list(include_deleted=include_deleted)

    def meshing_task_history(
        self, task_id: str, include_deleted: bool = False
    ) -> MeshingTaskHistoryRead:
        return self.tasks.history(task_id, include_deleted=include_deleted)

    def delete_meshing_task(
        self, task_id: str, *, cleanup_artifacts: bool = False
    ) -> MeshingTaskDeleteReport:
        task = self.tasks.get(task_id)
        if task.status in {"queued", "preparing", "waiting_surface", "waiting_volume"}:
            raise ValueError("请先在任务会话中停止 Fluent，再删除任务。")

        artifacts = self.tasks.artifacts(task_id)
        files_retained = 0
        files_deleted = 0
        files_missing = 0
        result_root = (self.database.path.parent / "meshing-results").resolve()
        for artifact in artifacts:
            if artifact.status == "missing":
                files_missing += 1
                continue
            if artifact.status == "deleted":
                continue
            file_path = Path(artifact.file_path).expanduser().resolve()
            try:
                file_path.relative_to(result_root)
            except ValueError:
                files_retained += 1
                continue
            if not cleanup_artifacts:
                files_retained += 1
                continue
            with self.database.connect() as connection:
                shared = connection.execute(
                    "SELECT COUNT(*) AS count FROM meshing_task_artifacts "
                    "WHERE file_path=? AND task_id<>? AND status='retained'",
                    (artifact.file_path, task_id),
                ).fetchone()
            if shared is not None and int(shared["count"]) > 0:
                files_retained += 1
                continue
            if not file_path.is_file():
                self.tasks.mark_artifact_status(artifact.id, "missing")
                files_missing += 1
                continue
            try:
                file_path.unlink()
                self.tasks.mark_artifact_status(artifact.id, "deleted")
                files_deleted += 1
            except OSError:
                files_retained += 1

        message = (
            "任务记录已删除；归档文件按所选规则处理。"
            if cleanup_artifacts
            else "任务记录已删除；网格和历史文件仍保留在归档目录。"
        )
        self.tasks.soft_delete(task_id, message)
        if task.session_id:
            self._release_session(task.session_id, dispose_worker=True)
        return MeshingTaskDeleteReport(
            task_id=task_id,
            deleted=True,
            files_retained=files_retained,
            files_deleted=files_deleted,
            files_missing=files_missing,
            message=message,
        )

    def archive_live_result(
        self, session_id: str, payload: MeshingArchiveCreate
    ) -> MeshingArchiveRecord:
        return self._run(
            lambda: self.live.archive_result(session_id, payload),
            session_id=session_id,
        )

    def list_live_archives(self, session_id: str) -> list[MeshingArchiveRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM meshing_result_archives "
                "WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        records: list[MeshingArchiveRecord] = []
        for row in rows:
            try:
                document = json.loads(Path(row["record_json_path"]).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                document = {}
            records.append(
                MeshingArchiveRecord(
                    id=row["id"],
                    session_id=row["session_id"],
                    task_id=row["task_id"],
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

    # ------------------------------------------------------------------
    # legacy single-adapter operations
    # ------------------------------------------------------------------

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

    def apply_automation(
        self,
        automation_id: int,
        payload: ApplyMeshingAutomationRequest,
    ) -> MeshingWorkflowReport:
        return self._run(lambda: self._apply_automation_impl(automation_id, payload))

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

            preset_to_apply = (
                automations.preset_revision(automation.id, automation.published_revision)
                if automation.published_revision is not None
                else automation.preset
            )
            if preset_to_apply.workflow_type == "watertight":
                active_steps = set(watertight_steps(preset_to_apply.items))
                active_items = [
                    item
                    for item in preset_to_apply.items
                    if item.task_path and item.task_path[0] in active_steps
                ]
                preset_to_apply = preset_to_apply.model_copy(update={"items": active_items})

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
