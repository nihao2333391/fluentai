"""Extract a machine-readable Fluent Meshing workflow schema."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from typing import Any

from ansys.fluent.core.workflow import camel_to_snake_case  # type: ignore[import-untyped]


def _safe_call(value: Any, default: Any = None) -> Any:
    try:
        return value() if callable(value) else value
    except Exception:
        return default


def _normalize_allowed_values(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [value]
        return list(parsed) if isinstance(parsed, (list, tuple, set)) else [parsed]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _child_names(obj: Any) -> list[str]:
    try:
        return [str(row[0]) for row in obj.get_completer_info()]
    except Exception:
        return []


def _describe_argument(
    name: str,
    obj: Any,
    current: Any,
    edit_path: str,
    *,
    depth: int = 0,
) -> dict[str, Any]:
    allowed = _normalize_allowed_values(_safe_call(getattr(obj, "allowed_values", None)))
    default = _safe_call(getattr(obj, "default_value", None))
    read_only = _safe_call(getattr(obj, "is_read_only", None))
    active = _safe_call(getattr(obj, "is_active", None))
    result: dict[str, Any] = {
        "name": name,
        "edit_path": edit_path,
        "value_type": _value_type(current),
        "current_value": current,
        "allowed_values": allowed,
        "default_value": default,
        "read_only": read_only,
        "editable": not bool(read_only),
        "active": active,
        "children": [],
    }
    if isinstance(current, dict) and depth < 6:
        state_by_snake = {camel_to_snake_case(str(key)): value for key, value in current.items()}
        for child_name in _child_names(obj):
            try:
                child = getattr(obj, child_name)
            except Exception:
                continue
            if callable(child) and child_name not in state_by_snake:
                continue
            if child_name not in state_by_snake and not hasattr(child, "get_state"):
                continue
            child_current = state_by_snake.get(
                child_name, _safe_call(getattr(child, "get_state", None))
            )
            result["children"].append(
                _describe_argument(
                    child_name,
                    child,
                    child_current,
                    f"{edit_path}.{child_name}",
                    depth=depth + 1,
                )
            )
    return result


def describe_task_arguments(task: Any, task_python_name: str) -> list[dict[str, Any]]:
    arguments = None
    state = None
    errors: list[str] = []
    for accessor_name in ("command_arguments", "arguments"):
        try:
            candidate = getattr(task, accessor_name)
            candidate_state = candidate.get_state()
            arguments = candidate
            state = candidate_state
            break
        except Exception as exc:
            errors.append(f"{accessor_name}: {type(exc).__name__}: {exc}")

    if arguments is None or state is None:
        return [
            {
                "name": "<arguments>",
                "edit_path": f"workflow.task({task_python_name!r}).arguments",
                "error": " | ".join(errors),
                "children": [],
            }
        ]

    state_by_snake = {camel_to_snake_case(str(key)): value for key, value in state.items()}
    described: list[dict[str, Any]] = []
    matched: set[str] = set()
    for source_child_name in _child_names(arguments):
        child_name = camel_to_snake_case(source_child_name)
        if child_name not in state_by_snake:
            continue
        try:
            child = getattr(arguments, source_child_name)
        except Exception:
            continue
        if callable(child) and child_name not in state_by_snake:
            continue
        matched.add(child_name)
        described.append(
            _describe_argument(
                child_name,
                child,
                state_by_snake[child_name],
                f"workflow.task({task_python_name!r}).command_arguments.{child_name}",
            )
        )

    for key, value in state.items():
        snake_key = camel_to_snake_case(str(key))
        if snake_key in matched:
            continue
        described.append(
            {
                "name": snake_key,
                "source_name": str(key),
                "edit_path": f"workflow.task({task_python_name!r}).command_arguments.{snake_key}",
                "value_type": _value_type(value),
                "current_value": value,
                "allowed_values": None,
                "default_value": None,
                "read_only": None,
                "active": None,
                "children": [],
                "editable": False,
                "note": "Value is exposed in task state but no public child object was resolved.",
            }
        )
    return described


def _task_python_name(task: Any) -> str:
    value = _safe_call(getattr(task, "python_name", None), "")
    return str(value)


def describe_task(task: Any, *, depth: int = 0) -> dict[str, Any]:
    python_name = str(_safe_call(getattr(task, "python_name", None), ""))
    state = _safe_call(getattr(task, "get_state", None), {}) or {}
    children = []
    if depth < 5:
        try:
            children = [describe_task(child, depth=depth + 1) for child in task.tasks()]
        except Exception:
            children = []
    insertable = _safe_call(getattr(task, "insertable_tasks", None), [])
    inactive = _safe_call(getattr(task, "inactive_tasks", None), [])
    return {
        "python_name": python_name,
        "display_name": state.get("_name_"),
        "command_name": state.get("CommandName"),
        "task_type": state.get("TaskType"),
        "check_point": state.get("CheckPoint"),
        "state": state.get("State"),
        "task_list": state.get("TaskList"),
        "inactive_task_list": state.get("InactiveTaskList"),
        "inactive_tasks": [_task_python_name(item) for item in inactive],
        "insertable_tasks": list(insertable) if isinstance(insertable, (list, tuple)) else [],
        "arguments": describe_task_arguments(task, python_name),
        "children": children,
    }


def extract_workflow_schema(workflow: Any, workflow_type: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "fluent_version": "25.2.0",
        "workflow_type": workflow_type,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "tasks": [describe_task(task) for task in workflow.tasks()],
    }
