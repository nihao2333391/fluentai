"""Wire protocol between the sidecar and per-task Fluent worker subprocesses.

Messages are newline-delimited JSON on the worker's stdio:

- request:  ``{"id": 1, "method": "connect", "params": {...}}``
- response: ``{"id": 1, "result": ...}`` or ``{"id": 1, "error": {...}}``
- event:    ``{"event": "ready" | "transcript" | "current_task", ...}``

Every ``MeshingWorkflowAdapter`` method maps to one RPC method. Pydantic
models travel as ``model_dump(mode="json")`` payloads and are rebuilt with
``model_validate`` on the receiving side. Adapter callbacks are marshalled as
events because callables cannot cross a process boundary.
"""

from __future__ import annotations

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

PROTOCOL_VERSION = 1

#: Exception types reconstructed faithfully on the parent side.
REMOTE_EXCEPTIONS: dict[str, type[BaseException]] = {
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "RuntimeError": RuntimeError,
    "TimeoutError": TimeoutError,
    "FileNotFoundError": FileNotFoundError,
    "OSError": OSError,
    "NotImplementedError": NotImplementedError,
}

#: RPC methods whose result is a pydantic model.
MODEL_RESULTS: dict[str, type[Any]] = {
    "connect": FluentStatus,
    "status": FluentStatus,
    "read_arguments": MeshingReadReport,
    "write_arguments": MeshingWriteReport,
    "apply_preset": MeshingApplyReport,
    "execute_task": MeshingTaskExecutionReport,
}

#: RPC methods handled by the worker host's callback bridge.
CALLBACK_METHODS = frozenset(
    {
        "register_transcript_callback",
        "unregister_transcript_callback",
        "register_current_task_callback",
        "unregister_current_task_callback",
    }
)


class RemoteAdapterError(RuntimeError):
    """A worker-side adapter call failed with an unmapped exception type."""

    def __init__(self, message: str, *, remote_type: str = "RuntimeError") -> None:
        super().__init__(message)
        self.remote_type = remote_type


class WorkerProtocolError(RuntimeError):
    """The worker subprocess misbehaved at the protocol level."""


class WorkerCrashError(RuntimeError):
    """The worker subprocess exited while requests were outstanding."""


def encode_error(exc: BaseException) -> dict[str, Any]:
    return {"type": type(exc).__name__, "message": str(exc)}


def decode_error(payload: dict[str, Any]) -> BaseException:
    type_name = str(payload.get("type") or "RuntimeError")
    message = str(payload.get("message") or "")
    exc_type = REMOTE_EXCEPTIONS.get(type_name)
    if exc_type is KeyError:
        return KeyError(message)
    if exc_type is not None:
        return exc_type(message)
    return RemoteAdapterError(message, remote_type=type_name)


def encode_result(method: str, result: Any) -> Any:
    """Convert an adapter return value into a JSON-safe payload."""
    model_type = MODEL_RESULTS.get(method)
    if model_type is not None and result is not None:
        return result.model_dump(mode="json")
    return result


def decode_result(method: str, payload: Any) -> Any:
    """Rebuild an adapter return value from its JSON payload."""
    model_type = MODEL_RESULTS.get(method)
    if model_type is not None and payload is not None:
        return model_type.model_validate(payload)
    return payload


def invoke_adapter(adapter: Any, method: str, params: dict[str, Any]) -> Any:
    """Dispatch one RPC call to a live adapter and return the wire result."""
    if method == "connect":
        return adapter.connect(FluentConnectionConfig.model_validate(params["config"]))
    if method == "disconnect":
        adapter.disconnect()
        return None
    if method == "status":
        return adapter.status()
    if method == "read_arguments":
        return adapter.read_arguments(MeshingReadRequest.model_validate(params["request"]))
    if method == "write_arguments":
        return adapter.write_arguments(MeshingWriteRequest.model_validate(params["request"]))
    if method == "apply_preset":
        return adapter.apply_preset(
            MeshingPresetDocument.model_validate(params["preset"]),
            str(params["model_path"]),
            import_geometry=bool(params.get("import_geometry", True)),
        )
    if method == "execute_task":
        return adapter.execute_task(
            str(params["workflow_type"]),
            [str(item) for item in params["task_path"]],
        )
    if method == "reset_workflow":
        adapter.reset_workflow(str(params["workflow_type"]))
        return None
    if method == "available_task_names":
        return list(adapter.available_task_names(str(params["workflow_type"])))
    if method == "read_current_task":
        return adapter.read_current_task()
    if method == "inspect_reference_labels":
        return list(adapter.inspect_reference_labels(str(params["model_path"])))
    if method in CALLBACK_METHODS:
        raise WorkerProtocolError(f"Callback method {method!r} must be bridged by the host.")
    raise WorkerProtocolError(f"Unknown worker method: {method!r}")
