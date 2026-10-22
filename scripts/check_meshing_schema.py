"""Validate generated Fluent Meshing workflow schemas."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "docs" / "meshing"
SUMMARY = OUTPUT / "schema-generation-summary.json"


def _load(name: str) -> dict:
    path = OUTPUT / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _walk(tasks: list[dict]):
    for task in tasks:
        yield task
        yield from _walk(task.get("children") or [])


def _argument_tree(arguments: list[dict]):
    for argument in arguments:
        yield argument
        yield from _argument_tree(argument.get("children") or [])


def _counts(schema: dict) -> tuple[int, int, int, int]:
    tasks = list(_walk(schema.get("tasks") or []))
    arguments = [
        argument
        for task in tasks
        for argument in [
            *_argument_tree(task.get("arguments") or []),
            *_argument_tree((task.get("child_template") or {}).get("arguments") or []),
        ]
    ]
    editable = [
        argument for argument in arguments if argument.get("editable") is not False
    ]
    allowed = [
        argument for argument in arguments if argument.get("allowed_values") is not None
    ]
    return len(schema.get("tasks") or []), len(arguments), len(editable), len(allowed)


def main() -> int:
    failures: list[str] = []
    try:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        if summary.get("status") != "passed":
            failures.append("schema generation summary is not passed")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"summary: {type(exc).__name__}: {exc}")

    expected = {
        "watertight": {
            "tasks": 11,
            "min_arguments": 500,
            "min_editable": 450,
            "min_allowed": 40,
            "unsupported_compound": set(),
        },
        "fault-tolerant": {
            "tasks": 25,
            "min_arguments": 550,
            "min_editable": 500,
            "min_allowed": 60,
            "unsupported_compound": {
                "Identify Construction Surfaces",
                "Create Local Refinement Regions",
            },
        },
    }
    for workflow_type, requirement in expected.items():
        try:
            schema = _load(f"fluent-meshing-25.2-{workflow_type}.schema.json")
            task_count, argument_count, editable_count, allowed_count = _counts(schema)
            if task_count != requirement["tasks"]:
                failures.append(
                    f"{workflow_type}: expected {requirement['tasks']} top-level tasks, got {task_count}"
                )
            if argument_count < requirement["min_arguments"]:
                failures.append(f"{workflow_type}: only {argument_count} arguments")
            if editable_count < requirement["min_editable"]:
                failures.append(
                    f"{workflow_type}: only {editable_count} editable arguments"
                )
            if allowed_count < requirement["min_allowed"]:
                failures.append(
                    f"{workflow_type}: only {allowed_count} arguments with allowed values"
                )
            unsupported_compound: set[str] = set()
            for task in _walk(schema.get("tasks") or []):
                for argument in task.get("arguments") or []:
                    if argument.get("name") == "<arguments>" and argument.get("error"):
                        continue
                    if not argument.get("edit_path") or not argument.get("value_type"):
                        failures.append(
                            f"{workflow_type}: incomplete argument {task.get('display_name')} / {argument.get('name')}"
                        )
                        break
                if task.get("task_type") != "Compound":
                    continue
                if task.get("supports_child_template") is True:
                    template_arguments = (task.get("child_template") or {}).get(
                        "arguments"
                    ) or []
                    if not template_arguments:
                        failures.append(
                            f"{workflow_type}: empty compound template for {task.get('display_name')}"
                        )
                else:
                    unsupported_compound.add(str(task.get("display_name")))
                    if not task.get("child_template_error"):
                        failures.append(
                            f"{workflow_type}: missing compound template reason for "
                            f"{task.get('display_name')}"
                        )
            if unsupported_compound != requirement["unsupported_compound"]:
                failures.append(
                    f"{workflow_type}: unsupported compound tasks changed: "
                    f"{sorted(unsupported_compound)}"
                )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{workflow_type}: {type(exc).__name__}: {exc}")

    try:
        watertight = _load("fluent-meshing-25.2-watertight.schema.json")
        task_names = {
            task.get("display_name") for task in watertight.get("tasks") or []
        }
        required_names = {
            "Import Geometry",
            "Add Local Sizing",
            "Generate the Surface Mesh",
            "Describe Geometry",
            "Update Boundaries",
            "Update Regions",
            "Add Boundary Layers",
            "Generate the Volume Mesh",
        }
        missing = required_names - task_names
        if missing:
            failures.append("watertight missing tasks: " + ", ".join(sorted(missing)))
    except Exception:  # noqa: BLE001, S110
        pass

    if failures:
        print("M8_SCHEMA_CHECK_FAILED")
        for failure in failures:
            print(" - " + failure)
        return 1

    print("M8_SCHEMA_CHECK_PASSED")
    for workflow_type in ("watertight", "fault-tolerant"):
        schema = _load(f"fluent-meshing-25.2-{workflow_type}.schema.json")
        task_count, argument_count, _, _ = _counts(schema)
        print(f" - {workflow_type}: {task_count} tasks, {argument_count} arguments")
    print(" - task and argument edit paths present")
    print(" - allowed-value metadata present")
    print(" - consecutive compound child templates captured or explicitly blocked")
    print(" - nested argument trees preserved")
    print(" - conditional and compound task tree preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
