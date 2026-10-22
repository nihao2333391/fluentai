"""Validate the saved M7 real sidecar workflow report."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "m7_workflow.json"


def main() -> int:
    if not REPORT.is_file():
        print(f"M7_GATE_FAILED: missing report {REPORT}")
        return 1
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    workflow = report.get("workflow") or {}
    jobs = report.get("jobs") or []
    logs = report.get("sync_logs") or []
    checks = {
        "status": report.get("status") == "passed",
        "catalog": report.get("catalog_size") == 20,
        "model_open": (report.get("model_open") or {}).get("status") == "success",
        "workflow": workflow.get("status") == "success",
        "apply_readback": (workflow.get("apply_report") or {}).get("status")
        == "success",
        "applied_value": report.get("applied_area") == 1.05,
        "restored_value": report.get("final_area") == 1.0,
        "job": bool(jobs) and jobs[0].get("status") == "succeeded",
        "sync_log": bool(logs) and logs[0].get("status") == "success",
        "disconnect": (report.get("disconnect") or {}).get("connected") is False,
        "sidecar_exit": report.get("sidecar_exit_code") == 0,
        "no_password": "password" not in json.dumps(report).lower(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("M7_GATE_FAILED: " + ", ".join(failed))
        return 1
    print("M7_GATE_PASSED")
    print(" - model loaded into real Fluent")
    print(" - automation applied and read back")
    print(" - original value restored")
    print(" - job succeeded")
    print(" - sync log recorded")
    print(" - Fluent disconnected cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
