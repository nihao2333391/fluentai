import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import IO, cast

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TOKEN = "integration-sidecar-token"


def _pump(stream: IO[str] | None, queue: Queue[str], prefix: str) -> None:
    if stream is None:
        return
    for line in stream:
        queue.put(f"{prefix}{line.rstrip()}")


def _start_sidecar(
    *, parent_pipe: bool = False
) -> tuple[subprocess.Popen[str], Queue[str], list[str]]:
    env = os.environ.copy()
    env.update(
        {
            "FLUENT_AI_SIDECAR_TOKEN": TOKEN,
            "PYTHONPATH": str(BACKEND_ROOT),
            "PYTHONUNBUFFERED": "1",
        }
    )
    if parent_pipe:
        env["FLUENT_AI_PARENT_PIPE"] = "1"

    process = subprocess.Popen(
        [sys.executable, "-m", "app.sidecar"],
        cwd=BACKEND_ROOT,
        env=env,
        stdin=subprocess.PIPE if parent_pipe else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    messages: Queue[str] = Queue()
    transcript: list[str] = []
    threads = [
        threading.Thread(target=_pump, args=(process.stdout, messages, "OUT "), daemon=True),
        threading.Thread(target=_pump, args=(process.stderr, messages, "ERR "), daemon=True),
    ]
    for thread in threads:
        thread.start()
    return process, messages, transcript


def _wait_for_handshake(
    process: subprocess.Popen[str],
    messages: Queue[str],
    transcript: list[str],
) -> dict[str, object]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            message = messages.get(timeout=0.2)
        except Empty:
            if process.poll() is not None:
                break
            continue
        transcript.append(message)
        if message.startswith("OUT "):
            raw = message.removeprefix("OUT ")
            try:
                payload_raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload_raw, dict):
                continue
            payload = cast(dict[str, object], payload_raw)
            if payload.get("event") == "sidecar_ready":
                return payload
            if payload.get("event") == "sidecar_error":
                raise AssertionError(f"Sidecar reported startup error: {payload}")

    raise AssertionError("Sidecar did not emit a ready handshake:\n" + "\n".join(transcript))


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_sidecar_process_handshake_readiness_and_shutdown() -> None:
    process, messages, transcript = _start_sidecar()
    try:
        handshake = _wait_for_handshake(process, messages, transcript)
        assert handshake["event"] == "sidecar_ready"
        port_value = handshake["port"]
        pid_value = handshake["pid"]
        assert isinstance(port_value, int)
        assert isinstance(pid_value, int)
        assert port_value > 0
        assert pid_value > 0
        port = port_value

        base_url = f"http://127.0.0.1:{port}"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with httpx.Client(timeout=5.0, trust_env=False) as client:
            health = client.get(f"{base_url}/health")
            assert health.status_code == 200

            unauthenticated = client.get(f"{base_url}/api/system/ready")
            assert unauthenticated.status_code == 401

            ready = client.get(f"{base_url}/api/system/ready", headers=headers)
            assert ready.status_code == 200
            assert ready.json()["status"] == "ready"

            shutdown = client.post(f"{base_url}/api/system/shutdown", headers=headers)
            assert shutdown.status_code == 202

        assert process.wait(timeout=10) == 0
    finally:
        _stop_process(process)


def test_sidecar_exits_when_parent_pipe_closes() -> None:
    process, messages, transcript = _start_sidecar(parent_pipe=True)
    try:
        _wait_for_handshake(process, messages, transcript)
        assert process.stdin is not None
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        _stop_process(process)
