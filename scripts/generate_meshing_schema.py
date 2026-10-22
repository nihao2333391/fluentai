"""Generate Watertight and Fault-tolerant workflow schemas without meshing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import ansys.fluent.core as pyfluent
from app.meshing.workflow_inventory import extract_workflow_schema

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "meshing"


def _count_arguments(tasks: list[dict]) -> int:
    count = 0
    for task in tasks:
        count += len(task.get("arguments") or [])
        count += _count_arguments(task.get("children") or [])
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Fluent Meshing workflow schemas"
    )
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    session = None
    summary: dict[str, object] = {
        "status": "failed",
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    try:
        session = pyfluent.launch_fluent(
            fluent_path=str(Path(args.fluent_exe).resolve()),
            product_version="25.2.0",
            dimension=3,
            precision="double",
            processor_count=1,
            mode="meshing",
            ui_mode="no_gui",
            py=False,
            start_timeout=300,
            cleanup_on_exit=True,
            start_watchdog=False,
            start_transcript=False,
        )
        generated = {}
        for workflow_type, factory in (
            ("watertight", session.watertight),
            ("fault-tolerant", session.fault_tolerant),
        ):
            workflow = factory()
            schema = extract_workflow_schema(workflow, workflow_type)
            schema["display_name"] = (
                "Watertight Geometry"
                if workflow_type == "watertight"
                else "Fault-tolerant Meshing"
            )
            path = output / f"fluent-meshing-25.2-{workflow_type}.schema.json"
            path.write_text(
                json.dumps(schema, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            tasks = schema["tasks"]
            generated[workflow_type] = {
                "path": str(path),
                "task_count": len(tasks),
                "argument_count": _count_arguments(tasks),
                "bytes": path.stat().st_size,
            }
        summary.update({"status": "passed", "schemas": generated})
        return 0
    except Exception as exc:  # noqa: BLE001
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        if session is not None:
            try:
                session.exit()
            except Exception:  # noqa: BLE001
                try:
                    session.force_exit()
                except Exception:  # noqa: BLE001, S110
                    pass
        summary["finished_at_utc"] = datetime.now(UTC).isoformat()
        (output / "schema-generation-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
