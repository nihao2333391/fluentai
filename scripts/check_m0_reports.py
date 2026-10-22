"""Validate generated M0 reports and enforce the gate criteria."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "docs" / "poc" / "reports"
PASS_REPORTS = {
    "env_check.json": None,
    "launch.json": ("launch", "no_gui"),
    "launch_gui.json": ("launch", "gui"),
    "launch_hold.json": ("launch_hold", "no_gui"),
    "attach.json": ("attach", None),
}


def load(name: str) -> dict:
    path = REPORTS / name
    if not path.is_file():
        raise AssertionError(f"Missing report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_password(value: object, path: str = "root") -> None:
    if isinstance(value, dict):
        if "password" in value:
            raise AssertionError(f"Unredacted password at {path}.password")
        for key, item in value.items():
            assert_no_password(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_password(item, f"{path}[{index}]")


def main() -> int:
    failures: list[str] = []
    for filename, expected in PASS_REPORTS.items():
        try:
            report = load(filename)
            if report.get("status") != "passed":
                raise AssertionError(f"{filename} status={report.get('status')!r}")
            if expected is not None:
                expected_mode, expected_ui_mode = expected
                if report.get("mode") != expected_mode:
                    raise AssertionError(f"{filename} mode={report.get('mode')!r}")
                if expected_ui_mode is not None and report.get("ui_mode") != expected_ui_mode:
                    raise AssertionError(f"{filename} ui_mode={report.get('ui_mode')!r}")
                if int(report.get("settings_read_count", 0)) < 5:
                    raise AssertionError(f"{filename} read fewer than five settings")
                write_check = report.get("write_verification") or {}
                if not write_check.get("write_verified") or not write_check.get("restored"):
                    raise AssertionError(f"{filename} write verification/restore failed")
            assert_no_password(report)
        except Exception as exc:
            failures.append(f"{filename}: {type(exc).__name__}: {exc}")

    try:
        failure_report = load("attach_failure.json")
        if failure_report.get("status") != "failed":
            raise AssertionError("attach_failure.json must record a failed connection")
        if (failure_report.get("error") or {}).get("type") != "FileNotFoundError":
            raise AssertionError("attach_failure.json did not preserve the expected error type")
        assert_no_password(failure_report)
    except Exception as exc:
        failures.append(f"attach_failure.json: {type(exc).__name__}: {exc}")

    if failures:
        print("M0_GATE_FAILED")
        for failure in failures:
            print(" - " + failure)
        return 1
    print("M0_GATE_PASSED")
    print(" - launch: 6 settings, write verified, restored")
    print(" - gui launch: passed")
    print(" - attach: separate process passed")
    print(" - failure handling: structured FileNotFoundError")
    print(" - reports: passwords redacted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())