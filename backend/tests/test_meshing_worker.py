"""Tests for the per-task Fluent worker subprocess and its wire protocol."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from queue import Queue

import pytest

from app.domain import FluentConnectionConfig
from app.meshing.worker_client import SubprocessMeshingAdapter, WorkerCrashError
from app.meshing.worker_host import WorkerHost
from app.meshing.worker_protocol import (
    RemoteAdapterError,
    decode_error,
    encode_error,
    encode_result,
    invoke_adapter,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]

FAKE_ADAPTER_TARGET = "app.meshing.fake:FakeMeshingAdapter"


def _worker_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(BACKEND_ROOT),
            "PYTHONUNBUFFERED": "1",
            "FLUENT_AI_WORKER_ADAPTER": FAKE_ADAPTER_TARGET,
            "FLUENT_AI_WORKER_PRELOAD_PYFLUENT": "0",
        }
    )
    return env


def _spawn(tmp_path: Path, name: str) -> SubprocessMeshingAdapter:
    return SubprocessMeshingAdapter(
        run_dir=tmp_path / name,
        adapter_target=FAKE_ADAPTER_TARGET,
        preload_pyfluent=False,
        startup_timeout_seconds=30,
        env=_worker_env(tmp_path),
    )


def test_error_round_trip_preserves_known_types() -> None:
    decoded = decode_error(encode_error(ValueError("bad port")))
    assert isinstance(decoded, ValueError)
    assert str(decoded) == "bad port"

    decoded = decode_error(encode_error(RuntimeError("boom")))
    assert isinstance(decoded, RuntimeError)

    decoded = decode_error(encode_error(KeyError("missing")))
    assert isinstance(decoded, KeyError)

    decoded = decode_error({"type": "WeirdError", "message": "x"})
    assert isinstance(decoded, RemoteAdapterError)
    assert decoded.remote_type == "WeirdError"


def test_encode_result_dumps_models() -> None:
    from app.domain import FluentStatus

    payload = encode_result("status", FluentStatus(connected=True, mode="launch"))
    assert payload["connected"] is True
    assert payload["mode"] == "launch"


def test_invoke_adapter_rejects_unknown_method() -> None:
    from app.meshing.fake import FakeMeshingAdapter

    with pytest.raises(Exception, match="Unknown worker method"):
        invoke_adapter(FakeMeshingAdapter(), "nope", {})


def test_worker_host_serves_adapter_over_streams() -> None:
    from app.meshing.fake import FakeMeshingAdapter

    class AttachRejectingAdapter(FakeMeshingAdapter):
        def connect(self, config):  # type: ignore[no-untyped-def]
            if config.mode == "attach":
                raise ValueError("Attach mode requires a port or server-info file.")
            return super().connect(config)

    adapter = AttachRejectingAdapter()
    stdin_read, stdin_write = os.pipe()
    stdout_read, stdout_write = os.pipe()

    host_stdin = os.fdopen(stdin_read, "r", encoding="utf-8")
    host_stdout = os.fdopen(stdout_write, "w", encoding="utf-8", buffering=1)
    client_stdin = os.fdopen(stdin_write, "w", encoding="utf-8", buffering=1)
    client_stdout = os.fdopen(stdout_read, "r", encoding="utf-8")

    exit_code: Queue[int] = Queue()
    thread = threading.Thread(
        target=lambda: exit_code.put(
            WorkerHost(adapter, input_stream=host_stdin, output_stream=host_stdout).run()
        ),
        daemon=True,
    )
    thread.start()

    ready = json.loads(client_stdout.readline())
    assert ready["event"] == "ready"

    client_stdin.write(
        json.dumps(
            {
                "id": 1,
                "method": "connect",
                "params": {"config": FluentConnectionConfig(mode="launch").model_dump(mode="json")},
            }
        )
        + "\n"
    )
    client_stdin.flush()
    response = json.loads(client_stdout.readline())
    assert response["id"] == 1
    assert response["result"]["connected"] is True
    assert adapter.connect_calls == 1

    client_stdin.write(json.dumps({"id": 2, "method": "status", "params": {}}) + "\n")
    client_stdin.flush()
    response = json.loads(client_stdout.readline())
    assert response["result"]["connected"] is True

    # Adapter exceptions cross the boundary with their type and message.
    client_stdin.write(
        json.dumps(
            {
                "id": 3,
                "method": "connect",
                "params": {"config": FluentConnectionConfig(mode="attach").model_dump(mode="json")},
            }
        )
        + "\n"
    )
    client_stdin.flush()
    response = json.loads(client_stdout.readline())
    assert response["error"]["type"] == "ValueError"
    assert "port" in response["error"]["message"]

    client_stdin.write(json.dumps({"id": 4, "method": "disconnect", "params": {}}) + "\n")
    client_stdin.flush()
    response = json.loads(client_stdout.readline())
    assert response["result"] is None

    client_stdin.close()
    assert exit_code.get(timeout=5) == 0


def test_subprocess_worker_round_trip_with_fake_adapter(tmp_path: Path) -> None:
    adapter = _spawn(tmp_path, "run")
    transcripts: list[str] = []
    try:
        # status() must not spawn the worker process.
        assert adapter.alive is False
        assert adapter.status().connected is False

        status = adapter.connect(FluentConnectionConfig(mode="launch", ui_mode="gui"))
        assert status.connected is True
        assert status.version == "25.2.0-fake"

        subscription = adapter.register_transcript_callback(transcripts.append)
        assert subscription is not None

        assert adapter.read_current_task() is None
        assert adapter.status().connected is True

        adapter.disconnect()
    finally:
        adapter.dispose()

    # The worker writes its stderr into the task log directory and chdirs
    # into the per-task fluent-work directory.
    assert (tmp_path / "run" / "logs" / "worker.log").is_file()
    assert (tmp_path / "run" / "fluent-work").is_dir()


def test_subprocess_worker_propagates_value_errors(tmp_path: Path) -> None:
    adapter = _spawn(tmp_path, "run")
    adapter._extra_env["FLUENT_AI_WORKER_ADAPTER"] = (
        "app.meshing.fake:AttachRejectingMeshingAdapter"
    )
    try:
        with pytest.raises(ValueError, match="port"):
            adapter.connect(FluentConnectionConfig(mode="attach"))
    finally:
        adapter.dispose()


def test_subprocess_worker_calls_fail_after_dispose(tmp_path: Path) -> None:
    adapter = _spawn(tmp_path, "run")
    adapter.connect(FluentConnectionConfig(mode="launch"))
    adapter.dispose()
    assert adapter.alive is False
    with pytest.raises(WorkerCrashError):
        adapter.available_task_names("watertight")


def test_subprocess_worker_notifies_on_crash(tmp_path: Path) -> None:
    adapter = _spawn(tmp_path, "run")
    exited = threading.Event()
    adapter.on_exit = exited.set
    adapter.connect(FluentConnectionConfig(mode="launch"))
    assert adapter.alive
    # Simulate an unexpected worker death (e.g. Fluent crash taking the
    # process down); the client must surface the exit notification.
    assert adapter._process is not None
    SubprocessMeshingAdapter._kill_process(adapter._process)
    assert exited.wait(timeout=10)
    adapter.dispose()


def test_subprocess_worker_dispose_is_quiet(tmp_path: Path) -> None:
    adapter = _spawn(tmp_path, "run")
    exited = threading.Event()
    adapter.on_exit = exited.set
    adapter.connect(FluentConnectionConfig(mode="launch"))
    adapter.dispose()
    assert not adapter.alive
    # Intentional disposal must not fire the unexpected-exit notification.
    assert not exited.wait(timeout=2)
