"""Build the seven-step Watertight workflow contract from the enriched schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "meshing" / "fluent-meshing-25.2-watertight.schema.json"
OUTPUT = ROOT / "backend" / "app" / "meshing" / "workflow_schema.json"

STEP_ORDER = [
    "import_geometry",
    "add_local_sizing",
    "create_surface_mesh",
    "describe_geometry",
    "update_regions",
    "add_boundary_layer",
    "create_volume_mesh",
]

STEP_LABELS = {
    "import_geometry": ("Import Geometry", "导入几何结构"),
    "add_local_sizing": ("Add Local Sizing", "添加局部尺寸"),
    "create_surface_mesh": ("Generate the Surface Mesh", "生成表面网格"),
    "describe_geometry": ("Describe Geometry", "描述几何结构"),
    "update_regions": ("Update Regions", "更新区域类型设定"),
    "add_boundary_layer": ("Add Boundary Layers", "添加边界层"),
    "create_volume_mesh": ("Generate the Volume Mesh", "生成体网格"),
}


def _find_argument(
    arguments: list[dict[str, Any]], path: list[str]
) -> dict[str, Any] | None:
    current = arguments
    argument: dict[str, Any] | None = None
    for part in path:
        argument = next((item for item in current if item.get("name") == part), None)
        if argument is None:
            return None
        current = argument.get("children") or []
    return argument


def _flatten(
    arguments: list[dict[str, Any]], prefix: list[str] | None = None
) -> list[dict[str, Any]]:
    prefix = prefix or []
    result: list[dict[str, Any]] = []
    for argument in arguments:
        path = [*prefix, str(argument.get("name"))]
        children = argument.get("children") or []
        if children:
            result.extend(_flatten(children, path))
            continue
        value_type = str(argument.get("value_type") or "string")
        allowed = argument.get("allowed_values")
        if value_type == "bool":
            control = "switch"
        elif allowed:
            control = "select" if value_type == "string" else "multi_select"
        elif value_type == "list" or value_type == "RepeatedScalarContainer":
            control = "tag_select"
        elif value_type in ("int", "float"):
            control = "number"
        else:
            control = "text"
        result.append(
            {
                "path": path,
                "label": argument.get("display_name") or argument.get("name"),
                "type": value_type,
                "control": control,
                "enum": allowed,
                "default": argument.get("default_value"),
                "advanced": argument.get("ui_section") == "高级选项",
                "developer": argument.get("ui_section") == "开发者/内部",
                "display_condition": argument.get("display_condition"),
            }
        )
    return result


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    tasks = {str(task["python_name"]): task for task in schema.get("tasks") or []}
    steps: list[dict[str, Any]] = []
    for sequence, task_name in enumerate(STEP_ORDER, start=1):
        task = tasks[task_name]
        english, chinese = STEP_LABELS[task_name]
        step: dict[str, Any] = {
            "sequence": sequence,
            "task_path": [task_name],
            "english_name": english,
            "label": chinese,
            "task_type": task.get("task_type"),
            "fields": _flatten(task.get("arguments") or []),
        }
        if task_name in {"add_local_sizing", "add_boundary_layer"}:
            child = task.get("child_template") or {}
            toggle = _find_argument(task.get("arguments") or [], ["add_child"])
            step["mode"] = "collection"
            step["toggle_field"] = (
                {
                    "path": ["add_child"],
                    "label": toggle.get("display_name"),
                    "type": toggle.get("value_type"),
                    "enum": toggle.get("allowed_values"),
                    "advanced": False,
                    "developer": False,
                }
                if toggle
                else None
            )
            step["collection"] = {
                "child_name_field": next(
                    (
                        item.get("name")
                        for item in child.get("arguments") or []
                        if item.get("name")
                        in {
                            "boi_control_name",
                            "bl_control_name",
                            "local_settings_name",
                        }
                    ),
                    None,
                ),
                "fields": _flatten(child.get("arguments") or []),
            }
        if task_name == "update_regions":
            step["mode"] = "region_table"
            step["region_name_field"] = ["region_name_list"]
            step["region_type_field"] = ["region_type_list"]
            step["region_type_enum"] = ["fluid", "solid"]
        if task_name == "import_geometry":
            step["file_field"] = ["file_name"]
        if task_name == "create_volume_mesh":
            step["primary_field"] = ["volume_fill"]
        steps.append(step)

    for step in steps:
        if step["task_path"] == ["import_geometry"]:
            for field in step["fields"]:
                if field["path"] == ["length_unit"]:
                    field["ui_default_override"] = "m"
        if step["task_path"] == ["describe_geometry"]:
            for field in step["fields"]:
                if field["path"] == ["setup_type"]:
                    field["ui_default_override"] = (
                        "The geometry consists of only fluid regions with no voids"
                    )

    contract = {
        "schema_version": 1,
        "fluent_version": schema.get("fluent_version"),
        "workflow_type": "watertight",
        "source_schema": "docs/meshing/fluent-meshing-25.2-watertight.schema.json",
        "step_order": STEP_ORDER,
        "steps": steps,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"workflow_contract={OUTPUT}")
    print(f"steps={len(steps)} fields={sum(len(step['fields']) for step in steps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
