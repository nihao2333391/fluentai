"""Extract Fluent Meshing UI metadata from the native FDL definition.

The pyFluent schema is excellent for edit paths and live values, but it does
not preserve the ordering, display labels, visibility conditions, or advanced
option groups used by the Fluent Meshing workflow panel. This script combines
the native ``Meshing.fdl`` definition with the captured 25.2 schema.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FDL = (
    PROJECT_ROOT
    / ".."
    / ".."
    / "Ansys2025R2"
    / "ANSYS Inc"
    / "v252"
    / "fluent"
    / "fluent25.2.0"
    / "cortex"
    / "resources"
    / "Meshing.fdl"
)

WATERTIGHT_TASK_ORDER = [
    "ImportGeometry",
    "AddLocalSizingWTM",
    "GenerateTheSurfaceMeshWTM",
    "GeometrySetup",
    "ShareTopology",
    "Capping",
    "UpdateBoundaries",
    "CreateRegions",
    "UpdateRegions",
    "AddBoundaryLayers",
    "GenerateTheVolumeMeshWTM",
]

EXCLUDED_TASK_TYPES = {"COMMAND", "SINGLETON"}

DISPLAY_TEXT_OVERRIDES = {
    "boi_size": "Target Mesh Size",
    "selection_type": "Selection Type",
    "boundary_layer_height": "Boundary Layer Height",
}

ADVANCED_CONDITION_TOKENS = (
    "ShowImportCadPreferences",
    "ShowSurfaceMeshPreferences",
    "ShowShareTopologyPreferences",
    "ShowVolumeMeshPreferences",
    "ShowPrismPreferences",
    "AdvancedOptions",
)


@dataclass
class FdlNode:
    kind: str
    name: str
    line: int
    indent: int
    meta: dict[str, str] = field(default_factory=dict)
    children: list["FdlNode"] = field(default_factory=list)

    def child(self, name: str) -> "FdlNode | None":
        normalized = name.strip().lower()
        return next((item for item in self.children if item.name.lower() == normalized), None)


def _logical_lines(path: Path) -> list[tuple[int, str, int]]:
    """Join FDL backslash continuations while retaining the starting line."""
    logical: list[tuple[int, str, int]] = []
    pending = ""
    pending_indent = 0
    pending_line = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for number, raw in enumerate(text.splitlines(), start=1):
        expanded = raw.expandtabs(8).rstrip()
        stripped = expanded.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not pending:
            pending = stripped
            pending_indent = len(expanded) - len(expanded.lstrip())
            pending_line = number
        else:
            pending = f"{pending} {stripped}"
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical.append((pending_indent, pending, pending_line))
        pending = ""
    if pending:
        logical.append((pending_indent, pending, pending_line))
    return logical


def parse_fdl(path: Path) -> FdlNode:
    root = FdlNode(kind="FILE", name=path.name, line=0, indent=-1)
    stack = [root]
    block_pattern = re.compile(r"^([A-Z][A-Z ]*):\s*(.*)$")
    property_pattern = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*)$")
    for indent, text, line in _logical_lines(path):
        if text == "END":
            if len(stack) > 1:
                stack.pop()
            continue
        match = block_pattern.match(text)
        if match:
            kind, name = match.group(1).strip(), match.group(2).strip()
            if kind in {"RULES"}:
                continue
            while len(stack) > 1 and stack[-1].indent >= indent:
                stack.pop()
            node = FdlNode(kind=kind, name=name, line=line, indent=indent)
            stack[-1].children.append(node)
            stack.append(node)
            continue
        match = property_pattern.match(text)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        stack[-1].meta[key] = value
    return root


def split_fdl_list(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    for char in value:
        if char in {'"', "'"}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            current.append(char)
            continue
        if quote is None:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            elif char == "," and depth == 0:
                items.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    if current:
        items.append("".join(current).strip())
    cleaned = [item.lstrip("\\").strip() for item in items if item]
    return [item for item in cleaned if item]


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"([A-Za-z])([0-9])", r"\1_\2", value)
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def _walk_nodes(node: FdlNode):
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


def _index_nodes(root: FdlNode) -> tuple[dict[str, FdlNode], dict[str, FdlNode]]:
    commands: dict[str, FdlNode] = {}
    singletons: dict[str, FdlNode] = {}
    for node in _walk_nodes(root):
        if node.kind == "COMMAND":
            commands.setdefault(node.name.strip(), node)
        elif node.kind == "SINGLETON":
            singletons.setdefault(node.name.strip(), node)
    return commands, singletons


def _global_declarations(root: FdlNode) -> dict[str, FdlNode]:
    declarations: dict[str, FdlNode] = {}
    for node in root.children:
        if node.kind not in EXCLUDED_TASK_TYPES:
            declarations.setdefault(node.name.strip(), node)
    return declarations


def _allowed_values(raw: str | None) -> tuple[list[Any] | None, bool]:
    if raw is None:
        return None, False
    value = raw.strip()
    if not value:
        return [], False
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", value) or "$" in value:
        return None, True
    return [_unquote(item) for item in split_fdl_list(value)], False


def _schema_arguments(arguments: list[dict[str, Any]], prefix: tuple[str, ...] = ()):
    for argument in arguments:
        path = (*prefix, str(argument.get("name")))
        yield path, argument
        yield from _schema_arguments(argument.get("children") or [], path)


def build_schema_index(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for task in schema.get("tasks") or []:
        command_name = str(task.get("command_name") or "")
        if not command_name:
            continue
        command_index = index.setdefault(command_name, {})
        argument_groups = [task.get("arguments") or []]
        child_template = task.get("child_template") or {}
        if child_template.get("arguments"):
            argument_groups.append(child_template["arguments"])
        for arguments in argument_groups:
            for path, argument in _schema_arguments(arguments):
                command_index.setdefault(".".join(path), argument)
    return index


def _find_declaration(
    name: str,
    scope: FdlNode,
    singletons: dict[str, FdlNode],
    globals_: dict[str, FdlNode],
) -> FdlNode | None:
    return scope.child(name) or globals_.get(name) or singletons.get(name)


def _is_expandable(node: FdlNode | None) -> bool:
    return bool(node and (node.kind == "SINGLETON" or node.meta.get("members")))


def _display_text(node: FdlNode | None, fallback: str) -> str:
    if not node:
        return fallback
    return _unquote(node.meta.get("displayText", fallback))


def _resolved_display_text(node: FdlNode | None, fallback: str) -> tuple[str, str | None]:
    raw = node.meta.get("displayText") if node else None
    if not raw:
        return fallback, None
    dynamic = bool(re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*\(", raw) or "$" in raw)
    if dynamic:
        technical_name = _camel_to_snake(node.name if node else fallback)
        return DISPLAY_TEXT_OVERRIDES.get(technical_name, fallback), raw
    return _unquote(raw), None


def _ui_section(
    label: str,
    condition: str | None,
    exposure: str | None,
    inherited: str | None,
) -> str:
    if exposure and "developer" in exposure.lower():
        return "开发者/内部"
    advanced_condition = bool(
        re.search(r"Show[A-Za-z0-9_]*Preferences|AdvancedOptions", condition or "")
    )
    if label.lower().startswith("advanced options") or advanced_condition or any(
        token in (condition or "") for token in ADVANCED_CONDITION_TOKENS
    ):
        return "高级选项"
    return inherited or "常规"


def resolve_arguments(
    command: FdlNode,
    schema_arguments: dict[str, Any],
    singletons: dict[str, FdlNode],
    globals_: dict[str, FdlNode],
) -> list[dict[str, Any]]:
    def resolve(
        name: str,
        scope: FdlNode,
        parent_names: tuple[str, ...],
        advanced_section: str | None,
        ancestors: frozenset[str],
    ) -> dict[str, Any]:
        node = _find_declaration(name, scope, singletons, globals_)
        path = (*parent_names, name)
        schema_path = ".".join(_camel_to_snake(part) for part in path)
        schema_arg = schema_arguments.get(schema_path) or {}
        label, display_text_expression = _resolved_display_text(node, name)
        exposure = node.meta.get("exposureLevel") if node else None
        is_toggle = bool(node and node.meta.get("APIName") == "show_in_gui")
        condition = node.meta.get("isActive") if node else None
        current_section = _ui_section(
            label,
            condition,
            exposure,
            advanced_section,
        )
        expandable = _is_expandable(node) and name not in ancestors and len(path) < 9

        if expandable:
            member_names = split_fdl_list(node.meta.get("members", "")) if node else []
            if not member_names and node:
                member_names = [child.name for child in node.children]
            children = [
                resolve(
                    member,
                    node,
                    path,
                    current_section,
                    ancestors | {name},
                )
                for member in member_names
            ]
            return {
                "name": _camel_to_snake(name),
                "source_name": name,
                "display_name": label,
                "display_text_expression": display_text_expression,
                "kind": "object",
                "source_line": node.line if node else None,
                "display_condition": condition,
                "exposure_level": exposure,
                "ui_section": current_section,
                "children": children,
                "current_value": schema_arg.get("current_value"),
                "edit_path": schema_arg.get("edit_path"),
            }

        allowed, allowed_dynamic = _allowed_values(node.meta.get("allowedValues") if node else None)
        return {
            "name": _camel_to_snake(name),
            "source_name": name,
            "display_name": label,
            "display_text_expression": display_text_expression,
            "kind": node.kind if node else "UNRESOLVED",
            "source_line": node.line if node else None,
            "value_type": schema_arg.get("value_type"),
            "default_value": node.meta.get("default") if node else None,
            "allowed_values": allowed,
            "allowed_values_dynamic_expression": (
                node.meta.get("allowedValues") if allowed_dynamic else None
            ),
            "display_condition": condition,
            "is_editable_expression": node.meta.get("isEditable") if node else None,
            "display_unit": node.meta.get("displayUnit") if node else None,
            "exposure_level": exposure,
            "api_name": node.meta.get("APIName") if node else None,
            "ui_section": current_section,
            "current_value": schema_arg.get("current_value"),
            "edit_path": schema_arg.get("edit_path"),
            "read_only": schema_arg.get("read_only"),
            "active": schema_arg.get("active"),
            "children": [],
        }

    argument_names = split_fdl_list(command.meta.get("arguments", ""))
    return [
        resolve(name, command, (), None, frozenset())
        for name in argument_names
    ]


def _task_display_name(task: dict[str, Any] | None, command: FdlNode) -> str:
    if task and task.get("display_name"):
        return str(task["display_name"])
    return _display_text(command, command.name)


def _resolved_leaf_paths(nodes: list[dict[str, Any]], prefix: tuple[str, ...] = ()):
    for node in nodes:
        path = (*prefix, str(node.get("name") or ""))
        children = node.get("children") or []
        if children:
            yield from _resolved_leaf_paths(children, path)
        else:
            yield ".".join(path)


def _schema_leaf_paths(task: dict[str, Any] | None):
    if not task:
        return set()
    arguments = list(task.get("arguments") or [])
    arguments.extend((task.get("child_template") or {}).get("arguments") or [])
    return {
        ".".join(_camel_to_snake(part) for part in path)
        for path, argument in _schema_arguments(arguments)
        if not argument.get("children")
    }


def build_workflow(
    workflow_type: str,
    schema: dict[str, Any],
    commands: dict[str, FdlNode],
    singletons: dict[str, FdlNode],
    globals_: dict[str, FdlNode],
) -> dict[str, Any]:
    tasks_by_command: dict[str, dict[str, Any]] = {}
    for task in schema.get("tasks") or []:
        tasks_by_command.setdefault(str(task.get("command_name") or ""), task)
    if workflow_type == "watertight":
        command_order = WATERTIGHT_TASK_ORDER
    else:
        command_order = [
            str(task.get("command_name") or "")
            for task in schema.get("tasks") or []
            if task.get("command_name")
        ]

    workflow_tasks: list[dict[str, Any]] = []
    for sequence, command_name in enumerate(command_order, start=1):
        command = commands.get(command_name)
        if command is None:
            continue
        task = tasks_by_command.get(command_name)
        children = resolve_arguments(
            command,
            build_schema_index(schema).get(command_name, {}),
            singletons,
            globals_,
        )
        fdl_paths = set(_resolved_leaf_paths(children))
        schema_paths = _schema_leaf_paths(task)
        workflow_tasks.append(
            {
                "sequence": sequence,
                "command_name": command_name,
                "display_name": _task_display_name(task, command),
                "task_type": (task or {}).get("task_type")
                or _unquote(command.meta.get("taskType", "")),
                "priority_index": command.meta.get("priorityIndex"),
                "display_condition": command.meta.get("IsCommandActive"),
                "help_string": command.meta.get("helpString"),
                "source_line": command.line,
                "schema_leaf_count": len(schema_paths),
                "fdl_leaf_count": len(fdl_paths),
                "paths_match_schema": schema_paths == fdl_paths,
                "schema_only_paths": sorted(schema_paths - fdl_paths),
                "fdl_only_paths": sorted(fdl_paths - schema_paths),
                "children": children,
            }
        )
    return {
        "workflow_type": workflow_type,
        "fluent_version": schema.get("fluent_version"),
        "task_count": len(workflow_tasks),
        "validated_task_count": sum(1 for task in workflow_tasks if task["paths_match_schema"]),
        "tasks": workflow_tasks,
    }


def _json_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flatten_options(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def visit(
        nodes: list[dict[str, Any]],
        task: dict[str, Any],
        parent_labels: tuple[str, ...] = (),
        parent_names: tuple[str, ...] = (),
        level: int = 1,
    ) -> None:
        for node in nodes:
            labels = (*parent_labels, str(node.get("display_name") or node.get("source_name")))
            names = (*parent_names, str(node.get("source_name") or node.get("name")))
            children = node.get("children") or []
            rows.append(
                {
                    "workflow": workflow["workflow_type"],
                    "task_sequence": task["sequence"],
                    "task_display_name": task["display_name"],
                    "task_command": task["command_name"],
                    "task_type": task.get("task_type"),
                    "task_condition": task.get("display_condition"),
                    "level": level,
                    "row_kind": "分组" if children else "选项",
                    "option_path": " > ".join(labels),
                    "parameter_path": ".".join(names),
                    "display_name": node.get("display_name"),
                    "display_text_expression": node.get("display_text_expression") or "",
                    "parameter_name": node.get("name"),
                    "kind": node.get("kind"),
                    "value_type": node.get("value_type"),
                    "default_value": _json_cell(node.get("default_value")),
                    "current_value": _json_cell(node.get("current_value")),
                    "allowed_values": _json_cell(node.get("allowed_values")),
                    "allowed_values_dynamic": node.get("allowed_values_dynamic_expression") or "",
                    "display_condition": node.get("display_condition") or "",
                    "ui_section": node.get("ui_section"),
                    "exposure_level": node.get("exposure_level") or "",
                    "api_name": node.get("api_name") or "",
                    "display_unit": node.get("display_unit") or "",
                    "edit_path": node.get("edit_path") or "",
                    "source_line": node.get("source_line"),
                    "read_only": node.get("read_only"),
                    "active": node.get("active"),
                }
            )
            visit(children, task, labels, names, level + 1)

    for task in workflow.get("tasks") or []:
        visit(task.get("children") or [], task)
    return rows


def _markdown_cell(value: Any) -> str:
    return _json_cell(value).replace("|", "\\|").replace("\n", " ")


def write_markdown(
    path: Path,
    workflows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# Ansys Fluent Meshing 原版选项审计报告",
        "",
        "## 结论",
        "",
        "本报告不是根据当前 Fluent AI 页面反推，而是直接解析 Fluent 2025 R2 安装目录中的原生 `Meshing.fdl`，再与真实 Fluent 会话采集的 pyFluent Schema 合并。",
        "",
        "- 原生 FDL：`D:\\Ansys2025R2\\ANSYS Inc\\v252\\fluent\\fluent25.2.0\\cortex\\resources\\Meshing.fdl`",
        "- 实时 Schema：`docs/meshing/fluent-meshing-25.2-watertight.schema.json`",
        "- 当前 Fluent AI 的主要差异：使用 Schema 返回顺序、显示 API 参数名、按自定义规则折叠高级项，尚未保存 FDL 的 `displayText`、`isActive`、`exposureLevel` 和 `members` 顺序。",
        "",
        "因此，要达到“和原版设置一模一样”，界面必须改为数据驱动：任务顺序、选项顺序、标签、默认值、显示条件和高级分组全部读取本报告对应的元数据。",
        "",
        "## 统计",
        "",
        "| 工作流 | 任务数 | 分组数 | 选项行 | 条件显示选项 | 开发者级选项 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for workflow in workflows:
        rows = [row for row in all_rows if row["workflow"] == workflow["workflow_type"]]
        leaves = [row for row in rows if row["row_kind"] == "选项"]
        groups = [row for row in rows if row["row_kind"] == "分组"]
        conditional = [
            row for row in leaves if row.get("display_condition") or row.get("task_condition")
        ]
        developer = [row for row in leaves if row.get("ui_section") == "开发者/内部"]
        lines.append(
            f"| {workflow['workflow_type']} | {workflow['task_count']} | {len(groups)} | "
            f"{len(leaves)} | {len(conditional)} | {len(developer)} |"
        )

    lines.extend(["", "## 完整性校验", ""])
    lines.append("| 工作流 | FDL/Schema 逐任务路径一致 | 说明 |")
    lines.append("|---|---:|---|")
    for workflow in workflows:
        mismatches = [
            task["display_name"]
            for task in workflow.get("tasks") or []
            if not task.get("paths_match_schema")
        ]
        note = "全部任务参数路径一一对应" if not mismatches else "已知限制：" + "、".join(mismatches)
        lines.append(
            f"| {workflow['workflow_type']} | {workflow.get('validated_task_count', 0)}/"
            f"{workflow['task_count']} | {note} |"
        )

    lines.extend(["", "## 工作流任务顺序", ""])
    for workflow in workflows:
        lines.append(f"### {workflow['workflow_type']}")
        lines.append("")
        lines.append("| 顺序 | Fluent 原版显示名 | 任务类型 | 显示/插入条件 | FDL 行 |")
        lines.append("|---:|---|---|---|---:|")
        for task in workflow.get("tasks") or []:
            lines.append(
                f"| {task['sequence']} | {_markdown_cell(task['display_name'])} | "
                f"{_markdown_cell(task.get('task_type'))} | "
                f"{_markdown_cell(task.get('display_condition'))} | {task.get('source_line')} |"
            )
        lines.append("")

    for workflow in workflows:
        lines.extend([f"## {workflow['workflow_type']} 全部选项", ""])
        workflow_rows = [row for row in all_rows if row["workflow"] == workflow["workflow_type"]]
        for task in workflow.get("tasks") or []:
            task_rows = [row for row in workflow_rows if row["task_sequence"] == task["sequence"]]
            if not task_rows:
                continue
            lines.extend(
                [
                    f"### {task['sequence']}. {task['display_name']}",
                    "",
                    f"- 命令：`{task['command_name']}`",
                    f"- 类型：{task.get('task_type') or ''}",
                    f"- 显示条件：`{task.get('display_condition') or '无'}`",
                    "",
                    "| 层级 | 原始显示名/路径 | 参数名 | 类型 | 默认值/表达式 | 可选值 | 显示条件 | 可见级别 | 高级分组 |",
                    "|---:|---|---|---|---|---|---|---|---|",
                ]
            )
            for row in task_rows:
                lines.append(
                    f"| {row['level']} | {_markdown_cell(row['option_path'])} | "
                    f"`{_markdown_cell(row['parameter_name'])}` | "
                    f"{_markdown_cell(row['kind'])} | {_markdown_cell(row['default_value'])} | "
                    f"{_markdown_cell(row['allowed_values'] or row['allowed_values_dynamic'])} | "
                    f"{_markdown_cell(row['display_condition'])} | "
                    f"{_markdown_cell(row['exposure_level'])} | "
                    f"{_markdown_cell(row['ui_section'])} |"
                )
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "workflow",
        "task_sequence",
        "task_display_name",
        "task_command",
        "task_type",
        "task_condition",
        "level",
        "row_kind",
        "option_path",
        "parameter_path",
        "display_name",
        "display_text_expression",
        "parameter_name",
        "kind",
        "value_type",
        "default_value",
        "current_value",
        "allowed_values",
        "allowed_values_dynamic",
        "display_condition",
        "ui_section",
        "exposure_level",
        "api_name",
        "display_unit",
        "edit_path",
        "source_line",
        "read_only",
        "active",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fdl", type=Path, default=DEFAULT_FDL)
    parser.add_argument("--schema-dir", type=Path, default=PROJECT_ROOT / "docs" / "meshing")
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "docs" / "meshing" / "ui-audit"
    )
    args = parser.parse_args()
    root = parse_fdl(args.fdl)
    commands, singletons = _index_nodes(root)
    globals_ = _global_declarations(root)
    workflows: list[dict[str, Any]] = []
    for workflow_type in ("watertight", "fault-tolerant"):
        schema_path = args.schema_dir / f"fluent-meshing-25.2-{workflow_type}.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        workflows.append(build_workflow(workflow_type, schema, commands, singletons, globals_))
    all_rows = [row for workflow in workflows for row in flatten_options(workflow)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "meshing-ui-inventory.json").write_text(
        json.dumps(workflows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(args.output_dir / "meshing-ui-options.csv", all_rows)
    write_markdown(args.output_dir / "MESHING_UI_FULL_AUDIT.md", workflows, all_rows)
    for workflow in workflows:
        rows = [row for row in all_rows if row["workflow"] == workflow["workflow_type"]]
        leaves = [row for row in rows if row["row_kind"] == "选项"]
        groups = [row for row in rows if row["row_kind"] == "分组"]
        print(
            f"{workflow['workflow_type']}: tasks={workflow['task_count']} "
            f"groups={len(groups)} options={len(leaves)} "
            f"validated={workflow.get('validated_task_count', 0)}/{workflow['task_count']}"
        )
    print(f"report={args.output_dir / 'MESHING_UI_FULL_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
