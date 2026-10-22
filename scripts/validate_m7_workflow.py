"""Validate the M7 vertical slice through the real sidecar HTTP API."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from queue import Empty, Queue
from typing import IO, Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
CASE_PATH = Path(r"D:\Fluent AI\ansys-runs\compat-smoke-20261021-170520\01_mesh.cas.h5")
FLUENT_EXE = Path(r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe")
REPORT_PATH = PROJECT_ROOT / "docs" / "poc" / "reports" / "m7_workflow.json"
TOKEN = "m7-workflow-validation-token"


def _pump(stream: IO[str] | None, queue: Queue[str], prefix: str) -> None:
    if stream is None:
        return
    for line in stream:
        queue.put(prefix + line.rstrip())


def _write_report(value: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    report: dict[str, Any] = {"status": "failed"}
    stage = "startup"
    data_dir = Path(tempfile.mkdtemp(prefix="fluent-ai-m7-"))
    env = os.environ.copy()
    env.update(
        {
            "FLUENT_AI_SIDECAR_TOKEN": TOKEN,
            "FLUENT_AI_DATA_DIR": str(data_dir),
            "FLUENT_AI_PARENT_PIPE": "1",
            "PYTHONPATH": str(BACKEND_ROOT),
            "PYTHONUNBUFFERED": "1",
            "FLUENT_AI_DEBUG": "1",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "app.sidecar"],
        cwd=BACKEND_ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    messages: Queue[str] = Queue()
    transcript: list[str] = []
    threads = [
        threading.Thread(
            target=_pump, args=(process.stdout, messages, "OUT "), daemon=True
        ),
        threading.Thread(
            target=_pump, args=(process.stderr, messages, "ERR "), daemon=True
        ),
    ]
    for thread in threads:
        thread.start()

    port: int | None = None
    try:
        if not CASE_PATH.is_file() or not FLUENT_EXE.is_file():
            raise FileNotFoundError(
                "Required Fluent executable or case file is missing."
            )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=0.2)
            except Empty:
                if process.poll() is not None:
                    break
                continue
            transcript.append(message)
            if message.startswith("OUT "):
                try:
                    payload = json.loads(message.removeprefix("OUT "))
                except json.JSONDecodeError:
                    continue
                if payload.get("event") == "sidecar_error":
                    raise RuntimeError(str(payload))
                if payload.get("event") == "sidecar_ready":
                    port = int(payload["port"])
                    break
        if port is None:
            raise RuntimeError(
                "Sidecar did not become ready:\n" + "\n".join(transcript)
            )

        base_url = f"http://127.0.0.1:{port}"
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=30.0), trust_env=False
        ) as client:
            stage = "catalog"
            catalog = client.get(f"{base_url}/api/fluent/catalog", headers=headers)
            catalog.raise_for_status()
            report["catalog_size"] = len(catalog.json())

            stage = "connect"
            connected = client.post(
                f"{base_url}/api/fluent/connect",
                headers=headers,
                json={
                    "mode": "launch",
                    "fluent_path": str(FLUENT_EXE),
                    "product_version": "25.2.0",
                    "processor_count": 1,
                    "ui_mode": "no_gui",
                    "start_timeout": 300,
                    "cleanup_on_exit": True,
                    "host": "127.0.0.1",
                    "port": None,
                    "password": None,
                    "server_info_file": None,
                },
            )
            connected.raise_for_status()
            report["connection"] = connected.json()

            stage = "model_create"
            model = client.post(
                f"{base_url}/api/models",
                headers=headers,
                json={
                    "name": "M7 validation case",
                    "file_path": str(CASE_PATH),
                    "description": "Real Fluent vertical-slice validation",
                    "tags": ["m7", "validation"],
                },
            )
            model.raise_for_status()
            model_id = int(model.json()["id"])
            report["model_id"] = model_id

            stage = "model_open"
            opened = client.post(
                f"{base_url}/api/models/{model_id}/open",
                headers=headers,
                json={"load_case": True},
            )
            opened.raise_for_status()
            report["model_open"] = opened.json()
            if opened.json()["status"] != "success":
                raise RuntimeError(str(opened.json()))

            stage = "initial_read"
            initial = client.post(
                f"{base_url}/api/fluent/settings/read",
                headers=headers,
                json={"setting_ids": ["reference.area"]},
            )
            initial.raise_for_status()
            original_area = float(initial.json()["reference.area"])
            report["original_area"] = original_area

            stage = "automation_create"
            automation = client.post(
                f"{base_url}/api/automations",
                headers=headers,
                json={
                    "name": "M7 reference area update",
                    "description": "Vertical slice validation preset",
                    "status": "active",
                    "preset": {
                        "schema_version": 1,
                        "fluent_version": "25.2.0",
                        "items": [
                            {
                                "setting_id": "reference.area",
                                "type": "float",
                                "value": original_area * 1.05,
                                "required": True,
                            }
                        ],
                    },
                },
            )
            automation.raise_for_status()
            automation_id = int(automation.json()["id"])
            report["automation_id"] = automation_id

            stage = "workflow_apply"
            workflow = client.post(
                f"{base_url}/api/automations/{automation_id}/apply",
                headers=headers,
                json={"model_id": model_id, "load_case": True},
            )
            workflow.raise_for_status()
            workflow_payload = workflow.json()
            report["workflow"] = workflow_payload

            stage = "applied_read"
            applied = client.post(
                f"{base_url}/api/fluent/settings/read",
                headers=headers,
                json={"setting_ids": ["reference.area"]},
            )
            applied.raise_for_status()
            applied_area = float(applied.json()["reference.area"])
            report["applied_area"] = applied_area

            stage = "restore"
            restore = client.post(
                f"{base_url}/api/fluent/settings/write",
                headers=headers,
                json={
                    "items": [
                        {
                            "setting_id": "reference.area",
                            "type": "float",
                            "value": original_area,
                            "required": True,
                        }
                    ]
                },
            )
            restore.raise_for_status()
            report["restore_report"] = restore.json()

            stage = "final_read"
            final = client.post(
                f"{base_url}/api/fluent/settings/read",
                headers=headers,
                json={"setting_ids": ["reference.area"]},
            )
            final.raise_for_status()
            final_area = float(final.json()["reference.area"])
            report["final_area"] = final_area

            stage = "jobs"
            jobs = client.get(f"{base_url}/api/jobs", headers=headers)
            jobs.raise_for_status()
            report["jobs"] = jobs.json()
            stage = "sync_logs"
            logs = client.get(f"{base_url}/api/sync-logs", headers=headers)
            logs.raise_for_status()
            report["sync_logs"] = logs.json()

            stage = "disconnect"
            disconnect = client.post(
                f"{base_url}/api/fluent/disconnect", headers=headers
            )
            disconnect.raise_for_status()
            report["disconnect"] = disconnect.json()

            passed = (
                report["catalog_size"] == 20
                and workflow_payload["status"] == "success"
                and abs(applied_area - original_area * 1.05) < 1e-9
                and abs(final_area - original_area) < 1e-9
                and report["jobs"][0]["status"] == "succeeded"
                and report["sync_logs"][0]["status"] == "success"
            )
            report["status"] = "passed" if passed else "failed"
            return 0 if passed else 1
    except Exception as exc:  # noqa: BLE001
        while True:
            try:
                transcript.append(messages.get_nowait())
            except Empty:
                break
        report["stage"] = stage
        report["sidecar_transcript"] = transcript[-80:]
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        try:
            if port is not None:
                httpx.post(
                    f"http://127.0.0.1:{port}/api/system/shutdown",
                    headers={"Authorization": f"Bearer {TOKEN}"},
                    timeout=5.0,
                    trust_env=False,
                )
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        report["sidecar_exit_code"] = process.returncode
        shutil.rmtree(data_dir, ignore_errors=True)
        _write_report(report)
        print(json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
