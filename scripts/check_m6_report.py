"""Validate the saved M6 real-Fluent adapter report."""

from __future__ import annotations

import json
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
        "catalog_size": report.get("catalog_size") == 27,
        "read_count": report.get("read_count") == 27,
        "apply_verified": report.get("apply_verified") is True,
        "restored": report.get("restored") is True,
        "dynamic_material": report.get("dynamic_material", {}).get("verified") is True,
        "dynamic_material_restored": report.get("dynamic_material", {}).get("restored")
        is True,
        "dynamic_boundary": report.get("dynamic_boundary", {}).get("verified") is True,
        "dynamic_boundary_restored": report.get("dynamic_boundary", {}).get("restored")
        is True,
        "disconnect": report.get("disconnect") == "success",
        "no_password": "password" not in json.dumps(report).lower(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("M6_GATE_FAILED: " + ", ".join(failed))
        return 1
    print("M6_GATE_PASSED")
    print(" - catalog: 27 settings")
    print(" - real Fluent read: 27 settings")
    print(" - apply readback: verified")
    print(" - original values: restored")
    print(" - dynamic material density/viscosity: verified and restored")
    print(" - named boundary velocity/roughness: verified and restored")
    print(" - disconnect: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
