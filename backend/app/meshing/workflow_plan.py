"""Watertight task order shared through the public workflow contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain import MeshingPresetItem

CONTRACT = json.loads(Path(__file__).with_name("workflow_schema.json").read_text(encoding="utf-8"))
DEFAULT_GEOMETRY = "The geometry consists of only solid regions"


def watertight_steps(items: list[MeshingPresetItem]) -> list[str]:
    values: dict[str, Any] = {
        item.argument_path[0]: item.value
        for item in items
        if item.task_path == ["describe_geometry"] and len(item.argument_path) == 1
        and item.value_mode == "fixed"
    }
    geometry = values.get("setup_type", DEFAULT_GEOMETRY)
    if values.get("multizone") == "Yes":
        raise ValueError(
            "当前 Fluent 25.2 静态任务定义尚未包含多区域控制和生成任务；"
            "请先采集该分支后再应用此模板。"
        )
    result: list[str] = []
    for name in CONTRACT["step_order"]:
        rule = CONTRACT.get("conditional_tasks", {}).get(name)
        if rule:
            if "geometry" in rule and geometry not in rule["geometry"]:
                continue
            if "argument" in rule and values.get(rule["argument"], rule.get("default", "No")) != rule["equals"]:
                continue
        result.append(name)
    return result
