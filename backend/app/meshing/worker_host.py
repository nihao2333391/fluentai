"""Child-side RPC host that owns one Fluent Meshing adapter instance.

The host reads JSON-line requests from stdin, executes them on a single
worker lane (one Fluent call at a time, mirroring the legacy adapter
executor), and writes responses and callback events back to stdout.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, TextIO

from app.meshing.worker_protocol import (
    PROTOCOL_VERSION,
    encode_error,
    encode_result,
    invoke_adapter,
)


class WorkerHost:
    """Serve one adapter instance over stdio JSON-line RPC."""

    def __init__(self, adapter: Any, *, input_stream: TextIO, output_stream: TextIO) -> None:
        self._adapter = adapter
        self._input = input_stream
        self._output = output_stream
        self._write_lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meshing-worker")

    def run(self) -> int:
        self._send({"event": "ready", "pid": os.getpid(), "version": PROTOCOL_VERSION})
        try:
            for message in self._read_messages():
                self._dispatch(message)
        finally:
            self._executor.shutdown(wait=True)
            with contextlib.suppress(Exception):
                self._adapter.disconnect()
        return 0

    def _read_messages(self) -> Iterator[dict[str, Any]]:
        for line in self._input:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                yield message

    def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            return
        request_id = message.get("id")
        params = message.get("params")
        self._executor.submit(
            self._run_request,
            request_id,
            method,
            params if isinstance(params, dict) else {},
        )

    def _run_request(self, request_id: Any, method: str, params: dict[str, Any]) -> None:
        try:
            result = self._invoke(method, params)
        except BaseException as exc:
            self._send({"id": request_id, "error": encode_error(exc)})
        else:
            self._send({"id": request_id, "result": encode_result(method, result)})

    def _invoke(self, method: str, params: dict[str, Any]) -> Any:
        if method == "register_transcript_callback":
            return self._adapter.register_transcript_callback(
                lambda text: self._send({"event": "transcript", "text": text})
            )
        if method == "register_current_task_callback":
            return self._adapter.register_current_task_callback(
                lambda name: self._send({"event": "current_task", "name": name})
            )
        if method == "unregister_transcript_callback":
            self._adapter.unregister_transcript_callback()
            return None
        if method == "unregister_current_task_callback":
            self._adapter.unregister_current_task_callback()
            return None
        return invoke_adapter(self._adapter, method, params)

    def _send(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        with self._write_lock:
            try:
                self._output.write(payload + "\n")
                self._output.flush()
            except (BrokenPipeError, OSError):
                pass


def run_worker(
    adapter: Any, *, input_stream: TextIO | None = None, output_stream: TextIO | None = None
) -> int:
    """Run the RPC host until stdin reaches EOF."""
    host = WorkerHost(
        adapter,
        input_stream=input_stream if input_stream is not None else sys.stdin,
        output_stream=output_stream if output_stream is not None else sys.stdout,
    )
    return host.run()
