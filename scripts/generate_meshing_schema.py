"""Generate Watertight and Fault-tolerant workflow schemas without meshing."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import ansys.fluent.core as pyfluent
from app.meshing.workflow_inventory import describe_task, extract_workflow_schema

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "meshing"


def _count_arguments(tasks: list[dict]) -> int:
    count = 0
    for task in tasks:
        count += _count_argument_tree(task.get("arguments") or [])
        count += _count_arguments(task.get("children") or [])
        template = task.get("child_template")
        if isinstance(template, dict):
            count += _count_argument_tree(template.get("arguments") or [])
    return count


def _count_argument_tree(arguments: list[dict]) -> int:
    count = 0
    for argument in arguments:
        count += 1
        count += _count_argument_tree(argument.get("children") or [])
    return count


def _walk_schema_tasks(
    tasks: list[dict], parent_path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], dict]]:
    entries: list[tuple[tuple[str, ...], dict]] = []
    for task in tasks:
        path = (*parent_path, str(task.get("python_name", "")))
        entries.append((path, task))
        entries.extend(_walk_schema_tasks(task.get("children") or [], path))
    return entries


def _find_live_task(workflow, task_path: tuple[str, ...]):
    candidates = list(workflow.tasks())
    task = None
    for part in task_path:
        task = next(
            (candidate for candidate in candidates if candidate.python_name() == part),
            None,
        )
        if task is None:
            raise LookupError(f"Task path not found: {'.'.join(task_path)}")
        candidates = list(task.tasks())
    return task


def _compound_template_state(task: dict) -> dict | None:
    command_name = str(task.get("command_name") or "")
    if command_name == "Capping":
        return {"cap_labels": []}
    if command_name in {
        "AddLocalSizingFTM",
        "IdentifyConstructionSurfaces",
        "CreateLocalRefinementRegions",
        "AddThickness",
        "IdentifyRegions",
        "ExtractEdges",
    }:
        return {"object_selection_list": []}
    if command_name == "DefineLeakageThreshold":
        return {"dead_regions_list": []}
    return None


def _parent_argument_child_template(
    task_path: tuple[str, ...], schema_task: dict
) -> dict | None:
    arguments = schema_task.get("arguments") or []
    if not arguments or any(
        argument.get("name") == "<arguments>" for argument in arguments
    ):
        return None
    return {
        "python_name": "<compound-child-template>",
        "display_name": f"{schema_task.get('display_name')} Child",
        "command_name": schema_task.get("command_name"),
        "task_type": "Compound Child",
        "check_point": None,
        "state": None,
        "task_list": None,
        "inactive_task_list": None,
        "inactive_tasks": [],
        "insertable_tasks": [],
        "arguments": copy.deepcopy(arguments),
        "children": [],
        "template": True,
        "template_task_path": list(task_path),
        "template_source": "parent_command_arguments",
    }


def _attach_compound_child_templates(factory, schema: dict) -> None:
    """Create one official child template for every compound workflow task."""
    for task_path, schema_task in _walk_schema_tasks(schema.get("tasks") or []):
        if schema_task.get("task_type") != "Compound":
            continue
        schema_task["supports_child_template"] = False
        try:
            workflow = factory()
            live_task = _find_live_task(workflow, task_path)
            before_names = {task.python_name() for task in live_task.tasks()}
            try:
                returned = live_task.add_child_and_update(
                    state=_compound_template_state(schema_task)
                )
            except Exception:  # noqa: BLE001 - fall back to the other official API
                returned = live_task.add_child_to_task()
            added = [
                task
                for task in live_task.tasks()
                if task.python_name() not in before_names
            ]
            child = added[-1] if added else returned
            if child is None:
                raise RuntimeError("Fluent did not return a new compound child task.")
            child = describe_task(child)
            child["template"] = True
            child["template_task_path"] = list(task_path)
            child["template_source"] = "fluent_add_child_and_update"
            schema_task["child_template"] = child
            schema_task["supports_child_template"] = True
        except Exception as exc:  # noqa: BLE001
            fallback = _parent_argument_child_template(task_path, schema_task)
            if fallback is None:
                schema_task["child_template_error"] = f"{type(exc).__name__}: {exc}"
                continue
            schema_task["child_template"] = fallback
            schema_task["supports_child_template"] = True
            schema_task["child_template_warning"] = (
                "Fluent refused child creation before geometry import; the template "
                "uses the task's official command arguments. "
                f"{type(exc).__name__}: {exc}"
            )


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
            _attach_compound_child_templates(factory, schema)
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
