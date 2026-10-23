"""Attach reviewed Fluent FDL UI metadata to captured Meshing schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_ROOT / "docs" / "meshing"
INVENTORY = SCHEMA_DIR / "ui-audit" / "meshing-ui-inventory.json"


def _ui_index(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(node.get("name")): node for node in nodes}


def _annotate_argument(
    argument: dict[str, Any], ui_node: dict[str, Any] | None
) -> None:
    if not ui_node:
        return
    argument["display_name"] = ui_node.get("display_name") or argument.get(
        "display_name"
    )
    argument["ui_section"] = ui_node.get("ui_section") or "常规"
    argument["display_condition"] = ui_node.get("display_condition")
    argument["display_text_expression"] = ui_node.get("display_text_expression")
    argument["ui_kind"] = ui_node.get("kind")
    if ui_node.get("display_unit"):
        argument["display_unit"] = ui_node["display_unit"]


def _merge_ui_tree(
    arguments: list[dict[str, Any]],
    ui_nodes: list[dict[str, Any]],
    *,
    prefix: str = "",
) -> tuple[int, list[str]]:
    ui_by_name = _ui_index(ui_nodes)
    ui_order = {name: index for index, name in enumerate(ui_by_name)}
    matched = 0
    missing: list[str] = []

    for argument in arguments:
        name = str(argument.get("name"))
        ui_node = ui_by_name.get(name)
        if ui_node:
            _annotate_argument(argument, ui_node)
            matched += 1
        else:
            missing.append(f"{prefix}{name}")
        children = argument.get("children") or []
        if children:
            child_matched, child_missing = _merge_ui_tree(
                children,
                (ui_node or {}).get("children") or [],
                prefix=f"{prefix}{name}.",
            )
            matched += child_matched
            missing.extend(child_missing)

    arguments.sort(key=lambda item: ui_order.get(str(item.get("name")), len(ui_order)))
    return matched, missing


def _count_leaves(arguments: list[dict[str, Any]]) -> int:
    return sum(
        1 if not argument.get("children") else _count_leaves(argument["children"])
        for argument in arguments
    )


def enrich(workflow_type: str, ui_workflow: dict[str, Any]) -> dict[str, Any]:
    schema_path = SCHEMA_DIR / f"fluent-meshing-25.2-{workflow_type}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tasks_by_name = {
        str(task.get("display_name")): task for task in schema.get("tasks") or []
    }
    ordered_tasks: list[dict[str, Any]] = []
    task_audit: list[dict[str, Any]] = []

    for ui_task in ui_workflow.get("tasks") or []:
        schema_task = tasks_by_name.get(str(ui_task.get("display_name")))
        if schema_task is None:
            raise RuntimeError(
                f"{workflow_type}: no schema task matched {ui_task.get('display_name')!r}"
            )
        schema_task["ui_sequence"] = ui_task.get("sequence")
        schema_task["ui_display_condition"] = ui_task.get("display_condition")
        schema_task["ui_help_string"] = ui_task.get("help_string")
        schema_task["ui_source_line"] = ui_task.get("source_line")

        ui_options = ui_task.get("children") or []
        matched, missing = _merge_ui_tree(
            schema_task.get("arguments") or [], ui_options
        )
        child_template = schema_task.get("child_template") or {}
        child_matched = 0
        child_missing: list[str] = []
        if child_template.get("arguments"):
            child_matched, child_missing = _merge_ui_tree(
                child_template["arguments"],
                ui_options,
                prefix="<child>.",
            )
        schema_leaf_count = _count_leaves(schema_task.get("arguments") or [])
        if child_template.get("arguments"):
            schema_leaf_count += _count_leaves(child_template["arguments"])
        ui_leaf_count = sum(_count_leaves([node]) for node in ui_options)
        task_audit.append(
            {
                "python_name": schema_task.get("python_name"),
                "display_name": ui_task.get("display_name"),
                "sequence": ui_task.get("sequence"),
                "schema_leaf_count": schema_leaf_count,
                "ui_leaf_count": ui_leaf_count,
                "matched_root_or_nested_arguments": matched + child_matched,
                "unmatched_schema_arguments": missing + child_missing,
            }
        )
        ordered_tasks.append(schema_task)

    schema["tasks"] = ordered_tasks
    schema["ui_metadata"] = {
        "schema_version": 1,
        "source": "D:\\Ansys2025R2\\ANSYS Inc\\v252\\fluent\\fluent25.2.0\\cortex\\resources\\Meshing.fdl",
        "task_order": [str(task.get("python_name")) for task in ordered_tasks],
        "task_audit": task_audit,
    }
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "workflow_type": workflow_type,
        "task_count": len(ordered_tasks),
        "task_audit": task_audit,
    }


def main() -> int:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    workflows = {str(item["workflow_type"]): item for item in inventory}
    results = [
        enrich(workflow_type, workflows[workflow_type])
        for workflow_type in ("watertight", "fault-tolerant")
    ]
    (SCHEMA_DIR / "ui-metadata-summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for result in results:
        unmatched = sum(
            len(task["unmatched_schema_arguments"]) for task in result["task_audit"]
        )
        print(
            f"{result['workflow_type']}: tasks={result['task_count']} "
            f"unmatched_arguments={unmatched}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
