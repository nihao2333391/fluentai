"""Validate the saved M6 real-Fluent adapter report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "m6_fluent_adapter.json"


def main() -> int:
    if not REPORT.is_file():
        print(f"M6_GATE_FAILED: missing report {REPORT}")
        return 1
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    checks = {
        "status": report.get("status") == "passed",
        "catalog_size": report.get("catalog_size") == 20,
        "read_count": report.get("read_count") == 20,
        "apply_verified": report.get("apply_verified") is True,
        "restored": report.get("restored") is True,
        "disconnect": report.get("disconnect") == "success",
        "no_password": "password" not in json.dumps(report).lower(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("M6_GATE_FAILED: " + ", ".join(failed))
        return 1
    print("M6_GATE_PASSED")
    print(" - catalog: 20 settings")
    print(" - real Fluent read: 20 settings")
    print(" - apply readback: verified")
    print(" - original values: restored")
    print(" - disconnect: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())