"""Validate the saved real live-Meshing verification report."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "meshing-live-check.json"


def main() -> int:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    started = report.get("started_session") or {}
    imported = report.get("imported_geometry") or {}
    imported_snapshot = imported.get("snapshot") or {}
    entered = report.get("entered_surface_step") or {}
    executed = report.get("executed_surface_step") or {}
    snapshot = executed.get("snapshot") or {}
    steps = snapshot.get("steps") or []
    log_messages = [
        str(entry.get("message") or "") for entry in started.get("logs") or []
    ]
    checks = {
        "status": report.get("status") == "passed",
        "marker": report.get("marker") == "MESHING_LIVE_CHECK_PASSED",
        "import_executed": imported.get("status") == "success",
        "geometry_imported": imported_snapshot.get("steps", [{}])[0].get("status")
        == "completed",
        "console_streamed": any(
            "Import" in message or "Reading" in message for message in log_messages
        ),
        "preset_written": (entered.get("write_report") or {}).get("status")
        == "success",
        "values_read": (entered.get("read_report") or {}).get("status") == "success",
        "surface_executed": executed.get("status") == "success",
        "next_step_active": snapshot.get("current_step_index") == 3,
        "surface_completed": len(steps) > 2 and steps[2].get("status") == "completed",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("MESHING_LIVE_REPORT_FAILED")
        for name in failed:
            print(f" - {name}")
        return 1
    print("MESHING_LIVE_REPORT_PASSED")
    for name in checks:
        print(f" - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
