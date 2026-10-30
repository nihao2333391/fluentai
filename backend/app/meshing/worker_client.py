"""Parent-side proxy for one Fluent Meshing adapter hosted in a worker subprocess.

``SubprocessMeshingAdapter`` implements the :class:`MeshingWorkflowAdapter`
protocol by forwarding every call over newline-delimited JSON on the worker's
stdio. The worker process is spawned lazily on the first call that needs a live
Fluent session and can be disposed and respawned at will, which lets a session
release its Fluent instance on completion and rebuild it on retry.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from concurrent.futures import Future
from io import TextIOWrapper
from pathlib import Path
from typing import Any

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
from app.meshing.worker_protocol import (
    WorkerCrashError as WorkerCrashError,
)
from app.meshing.worker_protocol import (
    WorkerProtocolError,
    decode_error,
)

DEFAULT_ADAPTER_TARGET = "app.meshing.pyfluent_adapter:PyFluentMeshingAdapter"


class SubprocessMeshingAdapter:
    """MeshingWorkflowAdapter facade over a per-task worker subprocess."""

    def __init__(
        self,
        *,
        run_dir: Path | None = None,
        python_executable: str | None = None,
        adapter_target: str = DEFAULT_ADAPTER_TARGET,
        preload_pyfluent: bool = True,
        startup_timeout_seconds: float = 60.0,
        env: dict[str, str] | None = None,
    ) -> None:
        self.run_dir = run_dir
        self._python_executable = python_executable or sys.executable
        self._adapter_target = adapter_target
        self._preload_pyfluent = preload_pyfluent
        self._startup_timeout_seconds = startup_timeout_seconds
        self._extra_env = dict(env or {})
        self.on_exit: Callable[[], None] | None = None

        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()
        self._request_ids = itertools.count(1)
        self._pending: dict[int, Future[Any]] = {}
        self._ready = threading.Event()
        self._disposed = False
        self._crash_error: BaseException | None = None

        self._transcript_callback: Callable[[str], None] | None = None
        self._current_task_callback: Callable[[str], None] | None = None
        self._transcript_subscription: str | None = None
        self._current_task_subscription = False

    # ------------------------------------------------------------------
    # process lifecycle
    # ------------------------------------------------------------------

    @property
    def alive(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def _ensure_process(self) -> subprocess.Popen[str]:
        spawn = False
        with self._lock:
            if self._disposed:
                raise WorkerCrashError("Fluent 工作进程已被释放，无法继续执行操作。")
            if self.alive:
                assert self._process is not None
                return self._process
            process = self._spawn_locked()
            spawn = True
        if spawn:
            self._reregister_callbacks()
        return process

    def _spawn_locked(self) -> subprocess.Popen[str]:
        run_dir = self.run_dir
        stderr_path: Path | None = None
        if run_dir is not None:
            (run_dir / "fluent-work").mkdir(parents=True, exist_ok=True)
            (run_dir / "logs").mkdir(parents=True, exist_ok=True)
            stderr_path = run_dir / "logs" / "worker.log"
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "FLUENT_AI_WORKER_ADAPTER": self._adapter_target,
                "FLUENT_AI_WORKER_PRELOAD_PYFLUENT": "1" if self._preload_pyfluent else "0",
            }
        )
        # The worker chdirs into its task directory, so relative PYTHONPATH
        # entries inherited from the parent would stop resolving.
        python_path = env.get("PYTHONPATH", "")
        if python_path:
            env["PYTHONPATH"] = os.pathsep.join(
                os.path.abspath(entry) if entry else entry
                for entry in python_path.split(os.pathsep)
            )
        env.update(self._extra_env)
        if run_dir is not None:
            env["FLUENT_AI_WORKER_RUN_DIR"] = str(run_dir)

        cwd = str(run_dir / "fluent-work") if run_dir is not None else None
        stderr_handle: TextIOWrapper | None = None
        if stderr_path is not None:
            stderr_handle = stderr_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [self._python_executable, "-m", "app.meshing_worker"],
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_handle if stderr_handle is not None else subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if stderr_handle is not None:
            # The child owns the duplicated handle after the spawn.
            stderr_handle.close()

        self._process = process
        self._ready.clear()
        self._crash_error = None
        reader = _ReaderThread(self, process)
        reader.start()
        if not self._ready.wait(timeout=self._startup_timeout_seconds):
            self._kill_process(process)
            raise WorkerCrashError(
                f"Fluent 工作进程在 {self._startup_timeout_seconds:g} 秒内未就绪。"
                "请检查任务目录下 logs/worker.log 与 Python 环境。"
            )
        return process

    @staticmethod
    def _kill_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=5)

    def dispose(self) -> None:
        """Disconnect Fluent gracefully, then terminate the worker process."""
        with self._lock:
            if self._disposed:
                return
            self._disposed = True
            process = self._process
        if process is not None and process.poll() is None:
            with contextlib.suppress(Exception):
                self._request_on(process, "disconnect", {}, timeout=15.0)
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._kill_process(process)
        self._fail_pending(WorkerCrashError("Fluent 工作进程已退出。"))

    # ------------------------------------------------------------------
    # RPC plumbing
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._request_on(self._ensure_process(), method, params, timeout=timeout)

    def _request_on(
        self,
        process: subprocess.Popen[str],
        method: str,
        params: dict[str, Any],
        *,
        timeout: float | None = None,
    ) -> Any:
        future: Future[Any] = Future()
        with self._lock:
            request_id = next(self._request_ids)
            self._pending[request_id] = future
        payload = json.dumps(
            {"id": request_id, "method": method, "params": params},
            ensure_ascii=False,
        )
        try:
            stdin = process.stdin
            if stdin is None or process.poll() is not None:
                raise WorkerCrashError("Fluent 工作进程已退出，请求无法送达。")
            stdin.write(payload + "\n")
            stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise WorkerCrashError("Fluent 工作进程已退出，请求无法送达。") from exc
        try:
            return future.result(timeout=timeout)
        finally:
            with self._lock:
                self._pending.pop(request_id, None)

    def _handle_response(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        if not isinstance(request_id, int):
            return
        with self._lock:
            future = self._pending.get(request_id)
        if future is None or future.done():
            return
        if isinstance(message.get("error"), dict):
            future.set_exception(decode_error(message["error"]))
        else:
            future.set_result(message.get("result"))

    def _handle_event(self, message: dict[str, Any]) -> None:
        event = message.get("event")
        if event == "ready":
            self._ready.set()
        elif event == "transcript":
            callback = self._transcript_callback
            if callback is not None:
                callback(str(message.get("text", "")))
        elif event == "current_task":
            callback = self._current_task_callback
            if callback is not None:
                raw = message.get("name")
                callback(str(raw) if raw is not None else "")

    def _on_stream_closed(self, error: BaseException | None) -> None:
        self._crash_error = error or WorkerCrashError("Fluent 工作进程已退出。")
        self._ready.set()
        self._fail_pending(self._crash_error)
        with self._lock:
            intentional = self._disposed
            on_exit = self.on_exit
        if on_exit is not None and not intentional:
            with contextlib.suppress(Exception):
                on_exit()

    def _fail_pending(self, error: BaseException) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(error)

    def _reregister_callbacks(self) -> None:
        if self._transcript_callback is not None:
            try:
                self._transcript_subscription = self._request("register_transcript_callback", {})
            except Exception:
                self._transcript_subscription = None
        if self._current_task_callback is not None:
            try:
                self._current_task_subscription = bool(
                    self._request("register_current_task_callback", {})
                )
            except Exception:
                self._current_task_subscription = False

    # ------------------------------------------------------------------
    # MeshingWorkflowAdapter
    # ------------------------------------------------------------------

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        result = self._request("connect", {"config": config.model_dump(mode="json")})
        return FluentStatus.model_validate(result)

    def disconnect(self) -> None:
        self._request("disconnect", {})

    def status(self) -> FluentStatus:
        if not self.alive:
            return FluentStatus(connected=False, mode=None)
        result = self._request("status", {})
        return FluentStatus.model_validate(result)

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport:
        result = self._request("read_arguments", {"request": request.model_dump(mode="json")})
        return MeshingReadReport.model_validate(result)

    def write_arguments(self, request: MeshingWriteRequest) -> MeshingWriteReport:
        result = self._request("write_arguments", {"request": request.model_dump(mode="json")})
        return MeshingWriteReport.model_validate(result)

    def apply_preset(
        self,
        preset: MeshingPresetDocument,
        model_path: str,
        *,
        import_geometry: bool = True,
    ) -> MeshingApplyReport:
        result = self._request(
            "apply_preset",
            {
                "preset": preset.model_dump(mode="json"),
                "model_path": model_path,
                "import_geometry": import_geometry,
            },
        )
        return MeshingApplyReport.model_validate(result)

    def execute_task(self, workflow_type: str, task_path: list[str]) -> MeshingTaskExecutionReport:
        result = self._request(
            "execute_task",
            {"workflow_type": workflow_type, "task_path": list(task_path)},
        )
        return MeshingTaskExecutionReport.model_validate(result)

    def reset_workflow(self, workflow_type: str) -> None:
        self._request("reset_workflow", {"workflow_type": workflow_type})

    def available_task_names(self, workflow_type: str) -> list[str]:
        result = self._request("available_task_names", {"workflow_type": workflow_type})
        return [str(item) for item in result]

    def register_transcript_callback(self, callback: Callable[[str], None]) -> str | None:
        self._transcript_callback = callback
        try:
            self._transcript_subscription = self._request("register_transcript_callback", {})
        except WorkerCrashError:
            self._transcript_subscription = None
        return self._transcript_subscription

    def unregister_transcript_callback(self) -> None:
        self._transcript_callback = None
        self._transcript_subscription = None
        if self.alive:
            with contextlib.suppress(Exception):
                self._request("unregister_transcript_callback", {})

    def read_current_task(self) -> str | None:
        result = self._request("read_current_task", {})
        return None if result is None else str(result)

    def register_current_task_callback(self, callback: Callable[[str], None]) -> bool:
        self._current_task_callback = callback
        try:
            self._current_task_subscription = bool(
                self._request("register_current_task_callback", {})
            )
        except WorkerCrashError:
            self._current_task_subscription = False
        return self._current_task_subscription

    def unregister_current_task_callback(self) -> None:
        self._current_task_callback = None
        self._current_task_subscription = False
        if self.alive:
            with contextlib.suppress(Exception):
                self._request("unregister_current_task_callback", {})

    def inspect_reference_labels(self, model_path: str) -> list[str]:
        result = self._request("inspect_reference_labels", {"model_path": model_path})
        return [str(item) for item in result]


class _ReaderThread:
    """Drain worker stdout and resolve pending requests or dispatch events."""

    def __init__(self, client: SubprocessMeshingAdapter, process: subprocess.Popen[str]) -> None:
        self._client = client
        self._process = process

    def start(self) -> None:
        threading.Thread(target=self._run, name="meshing-worker-reader", daemon=True).start()

    def _run(self) -> None:
        stream = self._process.stdout
        error: BaseException | None = None
        try:
            if stream is None:
                raise WorkerProtocolError("Fluent 工作进程缺少 stdout 管道。")
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(message, dict):
                    continue
                if "id" in message:
                    self._client._handle_response(message)
                elif "event" in message:
                    self._client._handle_event(message)
        except Exception as exc:
            error = exc
        finally:
            self._client._on_stream_closed(error)
