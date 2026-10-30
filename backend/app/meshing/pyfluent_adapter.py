"""PyFluent implementation of the dedicated Meshing workflow adapter."""

from __future__ import annotations

import ast
import contextlib
import math
import os
import re
import sys
import traceback
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any, Literal, cast

from ansys.fluent.core.workflow import camel_to_snake_case  # type: ignore[import-untyped]

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingArgumentReference,
    MeshingArgumentWriteResult,
    MeshingNameCheck,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingPresetValue,
    MeshingReadItemResult,
    MeshingReadReport,
    MeshingReadRequest,
    MeshingTaskExecutionReport,
    MeshingWorkflowType,
    MeshingWriteReport,
    MeshingWriteRequest,
)
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_inventory import describe_task_arguments

SELECTOR_ARGUMENT_PATTERN = re.compile(
    r"(_label_list|_zone_list|_region_list|_selection_list|_object_selection_list|"
    r"_object_list|_dead_regions_list|_region_scope)$"
)
STOP_TASKS = ["Generate the Surface Mesh", "Generate the Volume Mesh"]
LOCAL_FLUENT_STARTUP_ARGUMENTS = (
    '-setenv="FLUENT_HOST_IP=-127.0.0.1" -setenv="REMOTING_SERVER_ADDRESS=127.0.0.1"'
)


def _awp_root_environment_key(product_version: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{2})[.]?(\d)", str(product_version))
    if match is None:
        return None
    return f"AWP_ROOT{match.group(1)}{match.group(2)}"


def _configured_awp_root(config: FluentConnectionConfig) -> Path | None:
    if not config.fluent_path:
        return None
    root_key = _awp_root_environment_key(config.product_version)
    if root_key is None:
        return None
    expected_directory = f"v{root_key.removeprefix('AWP_ROOT')}".casefold()
    fluent_path = Path(config.fluent_path).expanduser()
    candidates = fluent_path.parents if fluent_path.suffix else (fluent_path, *fluent_path.parents)
    for candidate in candidates:
        if candidate.name.casefold() == expected_directory:
            return candidate
    return None


def _debug(message: str) -> None:
    if os.environ.get("FLUENT_AI_DEBUG") == "1":
        print(f"[meshing-debug] {message}", file=sys.stderr, flush=True)


def _safe_call(value: Any, default: Any = None) -> Any:
    try:
        return value() if callable(value) else value
    except Exception:
        return default


def _read_arguments_error(items: list[MeshingReadItemResult]) -> str:
    """Summarize read failures so the live workflow can show the failing path."""
    read_errors: list[str] = []
    missing_paths: list[str] = []
    seen_errors: set[str] = set()
    seen_missing: set[str] = set()
    for item in items:
        if item.found and item.error is None:
            continue
        task_name = "/".join(item.task_path)
        if item.compound_child_name:
            task_name += f"[{item.compound_child_name}]"
        if item.error == "Argument path was not found.":
            path = ".".join([*item.task_path, *item.argument_path])
            if item.compound_child_name:
                path += f"[{item.compound_child_name}]"
            if path not in seen_missing:
                missing_paths.append(path)
                seen_missing.add(path)
            continue
        cause = item.error or "Argument was not returned."
        detail = f"{task_name}: {cause}"
        if detail not in seen_errors:
            read_errors.append(detail)
            seen_errors.add(detail)

    details = read_errors
    if missing_paths:
        details.append("missing argument paths: " + ", ".join(missing_paths))
    message = "One or more Meshing arguments could not be read."
    if details:
        detail_text = "; ".join(details)
        if len(detail_text) > 1200:
            detail_text = detail_text[:1197] + "..."
        message += f" Details: {detail_text}"
    return message


def _read_argument_state(target: Any, *, fresh: bool = False) -> dict[str, Any]:
    """Read task arguments, bypassing PyFluent's cache when freshness matters."""
    arguments = getattr(target, "arguments", None)
    getter = getattr(arguments, "get_remote_state" if fresh else "get_state", None)
    if not callable(getter):
        if fresh:
            raise RuntimeError(
                "PyFluent does not expose get_remote_state(); "
                "a fresh Update Boundaries readback is unavailable."
            )
        raise RuntimeError("PyFluent task arguments do not expose get_state().")
    state = _normalize_state(getter())
    if not isinstance(state, dict):
        raise RuntimeError("PyFluent returned task arguments in an unsupported format.")
    return state


def _read_remote_argument(target: Any, argument_name: str) -> Any:
    """Read one dynamic workflow argument directly instead of the task snapshot."""
    arguments = getattr(target, "arguments", None)
    argument = getattr(arguments, argument_name, None)
    getter = getattr(argument, "get_remote_state", None)
    if not callable(getter):
        raise RuntimeError(f"PyFluent does not expose a remote reader for {argument_name}.")
    value = _normalize_state(getter())
    if argument_name.endswith("_list") and isinstance(value, str):
        value = _parse_list_literal(value)
    return value


def _find_task(workflow: Any, task_path: list[str]) -> Any:
    candidates = list(workflow.tasks())
    task: Any = None
    for part in task_path:
        task = next(
            (candidate for candidate in candidates if candidate.python_name() == part),
            None,
        )
        if task is None:
            raise LookupError(f"Meshing task path was not found: {'.'.join(task_path)}")
        candidates = list(task.tasks())
    return task


def _walk_live_tasks(tasks: list[Any]) -> Iterator[Any]:
    for task in tasks:
        yield task
        try:
            yield from _walk_live_tasks(list(task.tasks()))
        except Exception:
            continue


def _merge_state(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for part in path[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[path[-1]] = value


def _parse_list_literal(value: str) -> Any:
    """Parse Fluent's Python-literal list strings, returning None on failure."""
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None
    if isinstance(parsed, (list, tuple, set)):
        return _normalize_state(parsed)
    return None


def _normalize_state(value: Any) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = camel_to_snake_case(str(key))
            normalized_item = _normalize_state(item)
            # Fluent 2025 R2's legacy workflow API returns some list arguments
            # as Python-literal strings, for example "['inlet-hot', 'outlet']".
            # Normalize only fields named as lists; ordinary text may itself
            # happen to look like a Python list.
            if normalized_key.endswith("_list") and isinstance(normalized_item, str):
                parsed = _parse_list_literal(normalized_item)
                if parsed is not None:
                    normalized_item = parsed
            normalized[normalized_key] = normalized_item
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_state(item) for item in value]
    return value


def _read_state_path(state: Any, path: list[str]) -> Any:
    current = state
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _state_path_exists(state: Any, path: list[str]) -> bool:
    current = state
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _find_compound_child(task: Any, child_name: str) -> Any | None:
    try:
        children = list(task.tasks())
    except Exception:
        return None
    for child in children:
        try:
            if str(child.python_name()) == child_name:
                return child
        except Exception:
            continue
        state = _safe_call(getattr(child, "get_state", None), {}) or {}
        if str(state.get("_name_", "")) == child_name:
            return child
    return None


def _schema_argument_references(
    workflow_type: MeshingWorkflowType,
) -> list[tuple[list[str], list[str]]]:
    schema = MESHING_SCHEMA_INDEX.schemas.get(workflow_type) or {}
    references: list[tuple[list[str], list[str]]] = []

    def visit_arguments(
        arguments: list[dict[str, Any]],
        task_path: list[str],
        prefix: list[str],
    ) -> None:
        for argument in arguments:
            path = [*prefix, str(argument.get("name"))]
            children = argument.get("children") or []
            if children:
                visit_arguments(children, task_path, path)
            else:
                references.append((list(task_path), path))

    def visit_tasks(tasks: list[dict[str, Any]], parent_path: list[str]) -> None:
        for task in tasks:
            task_path = [*parent_path, str(task.get("python_name"))]
            visit_arguments(task.get("arguments") or [], task_path, [])
            visit_tasks(task.get("children") or [], task_path)

    visit_tasks(schema.get("tasks") or [], [])
    return references


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _values_equal(expected: Any, actual: Any, value_type: str | None = None) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return type(actual) is bool and expected is actual
    if isinstance(expected, (int, float)):
        actual_number = _numeric(actual)
        return actual_number is not None and math.isclose(
            float(expected), actual_number, rel_tol=1e-6, abs_tol=1e-12
        )
    if isinstance(expected, list):
        if isinstance(actual, (str, bytes, bytearray)) or actual is None:
            return False
        try:
            actual_values = list(actual)
        except TypeError:
            return False
        return len(expected) == len(actual_values) and all(
            _values_equal(left, right) for left, right in zip(expected, actual_values, strict=False)
        )
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(expected) != set(actual):
            return False
        return all(_values_equal(value, actual[key]) for key, value in expected.items())
    if value_type in ("int", "float") and _numeric(actual) is not None:
        return _numeric(actual) == _numeric(expected)
    return str(expected) == str(actual)


def _literal_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return [value]
        if isinstance(parsed, (list, tuple, set)):
            return list(parsed)
    return [] if value in (None, "") else [value]


def _name_values(value: Any) -> list[str]:
    return [str(item) for item in _literal_list(value) if str(item).strip()]


def _selector_kind(
    argument_name: str,
) -> Literal["label", "zone", "region", "object", "selection"] | None:
    if not SELECTOR_ARGUMENT_PATTERN.search(argument_name):
        return None
    if "label" in argument_name:
        return "label"
    if "zone" in argument_name:
        return "zone"
    if "region" in argument_name:
        return "region"
    if "object" in argument_name:
        return "object"
    return "selection"


def _collect_catalog_from_arguments(arguments: list[dict[str, Any]], catalog: set[str]) -> None:
    for argument in arguments:
        if SELECTOR_ARGUMENT_PATTERN.search(str(argument.get("name") or "")):
            for allowed in argument.get("allowed_values") or []:
                catalog.update(_name_values(allowed))
            catalog.update(_name_values(argument.get("current_value")))
        _collect_catalog_from_arguments(argument.get("children") or [], catalog)


def _collect_name_catalog(workflow: Any) -> set[str]:
    catalog: set[str] = set()
    for task in _walk_live_tasks(list(workflow.tasks())):
        python_name = str(_safe_call(getattr(task, "python_name", None), ""))
        try:
            arguments = describe_task_arguments(task, python_name)
        except Exception:
            continue
        _collect_catalog_from_arguments(arguments, catalog)
    return catalog


def _has_name_selectors(items: list[MeshingPresetItem]) -> bool:
    return any(
        item.value_mode == "fixed" and _selector_kind(item.argument_path[-1]) is not None
        for item in items
    )


def _validate_preset_names(
    workflow: Any, preset: MeshingPresetDocument
) -> tuple[list[MeshingNameCheck], list[str]]:
    # Reading every task state is a costly sequence of Fluent RPCs. Imports and
    # mesh-control writes without selectors have no geometry names to validate.
    catalog = _collect_name_catalog(workflow) if _has_name_selectors(preset.items) else set()
    return _validate_names(preset, catalog)


def _validate_names(
    preset: MeshingPresetDocument, catalog: set[str]
) -> tuple[list[MeshingNameCheck], list[str]]:
    checks: list[MeshingNameCheck] = []
    seen: set[tuple[str, str]] = set()
    for item in preset.items:
        argument_name = item.argument_path[-1]
        kind = _selector_kind(argument_name)
        if kind is None:
            continue
        for name in _name_values(item.value):
            key = (kind, name)
            if key in seen:
                continue
            seen.add(key)
            checks.append(MeshingNameCheck(kind=kind, name=name, found=name in catalog))
    missing = [f"{check.kind}:{check.name}" for check in checks if not check.found]
    return checks, missing


def _write_argument_state(task: Any, state: dict[str, Any]) -> None:
    arguments = task.arguments
    remaining: dict[str, Any] = {}
    for key, value in state.items():
        if isinstance(value, dict):
            remaining[key] = value
            continue
        try:
            getattr(arguments, key).set_state(value)
        except Exception:
            remaining[key] = value
    if not remaining:
        return
    update_dict = getattr(arguments, "update_dict", None)
    if callable(update_dict):
        try:
            update_dict(remaining, recursive=True)
            return
        except TypeError:
            update_dict(remaining)
            return
    arguments.set_state(remaining)


def _write_boundary_argument_state(task: Any, state: dict[str, Any]) -> None:
    """Submit Update Boundaries' old/new values as one command-argument state."""
    arguments = task.arguments
    set_state = getattr(arguments, "set_state", None)
    if callable(set_state):
        set_state(state)
        return
    _write_argument_state(task, state)


def _boundary_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    names = (
        "selection_type",
        "boundary_label_list",
        "boundary_label_type_list",
        "old_boundary_label_list",
        "old_boundary_label_type_list",
        "boundary_zone_list",
        "boundary_zone_type_list",
        "old_boundary_zone_list",
        "old_boundary_zone_type_list",
        "boundary_current_list",
        "boundary_current_type_list",
    )
    return {name: state[name] for name in names if name in state}


def _update_boundary_previous_state(task: Any, state: dict[str, Any]) -> dict[str, Any]:
    """Capture Fluent's current boundary types before writing template targets.

    Fluent's Update Boundaries task tracks edits as old/new parallel lists. The
    template stores only the desired values, so derive the old side from the
    live task state immediately before replacing the editable lists.
    """
    selection_type = state.get("selection_type")
    if selection_type not in {"label", "zone"}:
        if {"boundary_label_list", "boundary_label_type_list"}.intersection(state):
            selection_type = "label"
        elif {"boundary_zone_list", "boundary_zone_type_list"}.intersection(state):
            selection_type = "zone"
    if selection_type not in {"label", "zone"}:
        return {}

    if selection_type == "label":
        names_argument = "boundary_label_list"
        types_argument = "boundary_label_type_list"
        old_names_argument = "old_boundary_label_list"
        old_types_argument = "old_boundary_label_type_list"
    else:
        names_argument = "boundary_zone_list"
        types_argument = "boundary_zone_type_list"
        old_names_argument = "old_boundary_zone_list"
        old_types_argument = "old_boundary_zone_type_list"

    if names_argument not in state and types_argument not in state:
        return {}
    target_names = state.get(names_argument)
    target_types = state.get(types_argument)
    if not isinstance(target_names, list) or not isinstance(target_types, list):
        raise ValueError(f"{names_argument} and {types_argument} must both be lists.")
    if len(target_names) != len(target_types):
        raise ValueError(f"{names_argument} and {types_argument} must contain paired values.")
    if not target_names:
        return {}
    if any(not isinstance(name, str) for name in target_names):
        raise ValueError(f"{names_argument} must contain only names.")

    # The current table follows Selection Type. Read the existing selection
    # from a fresh remote snapshot, then switch only when needed so an
    # unnecessary RPC cannot clear Fluent's dynamically-populated table.
    initial_state = _read_argument_state(task, fresh=True)
    if initial_state.get("selection_type") != selection_type:
        task.arguments.selection_type.set_state(selection_type)
        initial_state = _read_argument_state(task, fresh=True)

    # PyFluent's task-level remote snapshot can omit dynamically-populated
    # arguments. Read each live table field directly first, then use complete
    # task snapshots as compatibility fallbacks for PyFluent versions where
    # the per-field remote reader is unavailable.
    current_names: Any = None
    current_types: Any = None
    read_errors: list[str] = []
    try:
        current_names = _read_remote_argument(task, "boundary_current_list")
    except Exception as exc:
        read_errors.append(f"boundary_current_list field read: {type(exc).__name__}: {exc}")
    try:
        current_types = _read_remote_argument(task, "boundary_current_type_list")
    except Exception as exc:
        read_errors.append(f"boundary_current_type_list field read: {type(exc).__name__}: {exc}")

    def has_target_table(names: Any, types: Any) -> bool:
        return (
            isinstance(names, list)
            and isinstance(types, list)
            and len(names) == len(types)
            and all(name in names for name in target_names)
        )

    if not has_target_table(current_names, current_types):
        # The fresh snapshot already reflects the current Selection Type, so
        # reuse it before falling back to PyFluent's cached state.
        remote_names = _read_state_path(initial_state, ["boundary_current_list"])
        remote_types = _read_state_path(initial_state, ["boundary_current_type_list"])
        if has_target_table(remote_names, remote_types):
            current_names, current_types = remote_names, remote_types
        else:
            if not isinstance(current_names, list):
                current_names = remote_names
            if not isinstance(current_types, list):
                current_types = remote_types
    if not has_target_table(current_names, current_types):
        cached_state = _read_argument_state(task)
        cached_names = _read_state_path(cached_state, ["boundary_current_list"])
        cached_types = _read_state_path(cached_state, ["boundary_current_type_list"])
        if has_target_table(cached_names, cached_types):
            current_names, current_types = cached_names, cached_types
        else:
            if not isinstance(current_names, list):
                current_names = cached_names
            if not isinstance(current_types, list):
                current_types = cached_types
    if not isinstance(current_names, list) or not isinstance(current_types, list):
        detail = " " + "; ".join(read_errors) if read_errors else ""
        raise LookupError("Fluent did not return its current boundary table." + detail)
    if len(current_names) != len(current_types):
        raise ValueError("Fluent's current boundary table has unpaired names and types.")
    current_pairs: dict[str, str] = {}
    for current_name, current_type in zip(current_names, current_types, strict=False):
        if isinstance(current_name, str) and isinstance(current_type, str):
            current_pairs.setdefault(current_name, current_type)

    missing = [name for name in target_names if name not in current_pairs]
    if missing:
        raise LookupError(
            "Fluent did not return current boundary types for: " + ", ".join(map(str, missing))
        )

    return {
        old_names_argument: list(target_names),
        old_types_argument: [current_pairs[name] for name in target_names],
    }


def _create_child(task: Any, state: dict[str, Any]) -> Any:
    try:
        child = task.add_child_and_update(state=state or None)
    except Exception as add_error:
        try:
            child = task.add_child_to_task()
        except Exception as fallback_error:
            raise RuntimeError(
                f"Could not create compound child for {task.python_name()}: "
                f"{type(add_error).__name__}: {add_error}; "
                f"{type(fallback_error).__name__}: {fallback_error}"
            ) from fallback_error
    if child is None:
        children = list(task.tasks())
        if not children:
            raise RuntimeError(f"Fluent did not create a child task for {task.python_name()}.")
        child = children[-1]
    return child


class PyFluentMeshingAdapter:
    """Manage a Fluent Meshing session without executing mesh generation."""

    def __init__(
        self,
        *,
        pyfluent_module: Any | None = None,
        session: Any | None = None,
        connection_mode: Literal["launch", "attach"] | None = None,
    ) -> None:
        self._pyfluent_module = pyfluent_module
        self._session = session
        self._connection_mode = connection_mode
        self._workflow: Any | None = None
        self._workflow_type: str | None = None
        self._transcript_callback_id: str | None = None
        self._current_task_subscription: Any | None = None

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        if self._session is not None:
            if self._is_active():
                self.disconnect()
            else:
                self.unregister_current_task_callback()
                self._session = None
                self._connection_mode = None
                self._workflow = None
                self._workflow_type = None
                self._transcript_callback_id = None

        pyfluent = self._pyfluent_module or self._load_pyfluent()
        if config.mode == "launch":
            awp_root = _configured_awp_root(config)
            awp_root_key = _awp_root_environment_key(config.product_version)
            if awp_root is not None and awp_root_key is not None:
                # PyFluent resolves the installation root from this variable before
                # starting Fluent, even when fluent_path points at fluent.exe.
                os.environ[awp_root_key] = str(awp_root)
            # Fluent 2025 R2 may bind its gRPC server to a LAN interface even when
            # REMOTING_SERVER_ADDRESS is inherited by the launcher process. Set both
            # variables through Fluent's own startup parser so its server-info file
            # advertises a local-only address that PyFluent accepts safely.
            _debug(
                "launching local Fluent with loopback startup settings, "
                f"path={config.fluent_path!r}, version={config.product_version}, "
                f"ui_mode={config.ui_mode}"
            )
            launch_kwargs: dict[str, Any] = {
                "product_version": config.product_version,
                "dimension": 3,
                "precision": "double",
                "processor_count": config.processor_count,
                "mode": "meshing",
                "ui_mode": config.ui_mode,
                "py": False,
                "start_timeout": config.start_timeout,
                "cleanup_on_exit": config.cleanup_on_exit,
                "start_watchdog": False,
                "start_transcript": True,
                "additional_arguments": LOCAL_FLUENT_STARTUP_ARGUMENTS,
            }
            if config.fluent_path:
                launch_kwargs["fluent_path"] = config.fluent_path
            if awp_root is not None and awp_root_key is not None:
                launch_kwargs["env"] = {awp_root_key: str(awp_root)}
            try:
                self._session = pyfluent.launch_fluent(**launch_kwargs)
            except Exception as exc:
                _debug(
                    f"local Fluent launch or session handshake failed: {type(exc).__name__}: {exc}"
                )
                raise
        else:
            if config.server_info_file:
                self._session = pyfluent.connect_to_fluent(
                    server_info_file_name=config.server_info_file,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=True,
                )
            else:
                if config.port is None:
                    raise ValueError("Attach mode requires a port or server-info file.")
                self._session = pyfluent.connect_to_fluent(
                    ip=config.host,
                    port=config.port,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=True,
                )
        self._connection_mode = config.mode
        return self.status()

    def disconnect(self) -> None:
        self.unregister_current_task_callback()
        session = self._session
        mode = self._connection_mode
        self._session = None
        self._connection_mode = None
        self._workflow = None
        self._workflow_type = None
        self._transcript_callback_id = None
        if session is not None and mode == "launch":
            session.exit()

    def status(self) -> FluentStatus:
        session = self._session
        if session is None or not self._is_active():
            return FluentStatus(connected=False, mode=self._connection_mode)
        version: str | None = None
        try:
            version = str(session.get_fluent_version())
        except Exception:
            version = None
        properties = getattr(session, "connection_properties", None)
        host: str | None = None
        port: int | None = None
        pid: int | None = None
        if properties is not None:
            host = getattr(properties, "ip", None) or getattr(properties, "cortex_host", None)
            raw_port = getattr(properties, "port", None)
            port = int(raw_port) if raw_port is not None else None
            raw_pid = getattr(properties, "fluent_host_pid", None) or getattr(
                properties, "cortex_pid", None
            )
            pid = int(raw_pid) if raw_pid is not None else None
        return FluentStatus(
            connected=True,
            mode=self._connection_mode,
            version=version,
            pid=pid,
            host=host,
            port=port,
        )

    def read_arguments(self, request: MeshingReadRequest) -> MeshingReadReport:
        report = MeshingReadReport(
            workflow_type=request.workflow_type,
            status="failed",
        )
        try:
            workflow = self._get_workflow(request.workflow_type)
            report.task_names = [str(task.python_name()) for task in workflow.tasks()]
            references = request.items or [
                MeshingArgumentReference(task_path=task_path, argument_path=argument_path)
                for task_path, argument_path in _schema_argument_references(request.workflow_type)
            ]
            grouped: dict[
                tuple[tuple[str, ...], str | None], list[tuple[int, MeshingArgumentReference]]
            ] = {}
            for index, reference in enumerate(references):
                key = (tuple(reference.task_path), reference.compound_child_name)
                grouped.setdefault(key, []).append((index, reference))

            results: list[MeshingReadItemResult | None] = [None] * len(references)
            for (task_path, child_name), group in grouped.items():
                try:
                    task = _find_task(workflow, list(task_path))
                    target = task
                    if child_name:
                        child = _find_compound_child(task, child_name)
                        if child is None:
                            raise LookupError(f"Compound child was not found: {child_name}")
                        target = child
                    # Update Boundaries populates its live table dynamically and
                    # PyFluent's cached snapshot can lag behind Fluent, so always
                    # read this task from a fresh remote snapshot. Per-field
                    # remote reads are even fresher, but may be unavailable or
                    # return no list value; only then fall back to the snapshot,
                    # and mark the field unreadable when neither source yields
                    # a list so the caller can treat the table as unavailable.
                    fresh_boundary_read = task_path == ("update_boundaries",) and child_name is None
                    state = _read_argument_state(target, fresh=fresh_boundary_read)
                    dynamic_read_errors: dict[str, str] = {}
                    if fresh_boundary_read:
                        for argument_name in (
                            "boundary_current_list",
                            "boundary_current_type_list",
                        ):
                            try:
                                value = _read_remote_argument(target, argument_name)
                            except Exception as exc:
                                if not isinstance(state.get(argument_name), list):
                                    state.pop(argument_name, None)
                                    dynamic_read_errors[argument_name] = (
                                        f"{type(exc).__name__}: {exc}"
                                    )
                                continue
                            if isinstance(value, list):
                                state[argument_name] = value
                            elif not isinstance(state.get(argument_name), list):
                                state.pop(argument_name, None)
                                dynamic_read_errors[argument_name] = (
                                    "Fluent returned a non-list value for "
                                    f"{argument_name}: {str(value)[:120]!r}"
                                )
                    for index, reference in group:
                        found = _state_path_exists(state, reference.argument_path)
                        argument_name = reference.argument_path[-1]
                        results[index] = MeshingReadItemResult(
                            task_path=reference.task_path,
                            argument_path=reference.argument_path,
                            compound_child_name=reference.compound_child_name,
                            found=found,
                            value=cast(
                                MeshingPresetValue | None,
                                _read_state_path(state, reference.argument_path),
                            ),
                            error=(
                                None
                                if found
                                else dynamic_read_errors.get(
                                    argument_name, "Argument path was not found."
                                )
                            ),
                        )
                except Exception as exc:
                    for index, reference in group:
                        results[index] = MeshingReadItemResult(
                            task_path=reference.task_path,
                            argument_path=reference.argument_path,
                            compound_child_name=reference.compound_child_name,
                            found=False,
                            error=f"{type(exc).__name__}: {exc}",
                        )
            report.items = [result for result in results if result is not None]
            report.status = (
                "success"
                if report.items and all(item.found and item.error is None for item in report.items)
                else "failed"
            )
            if report.status == "failed":
                report.error = _read_arguments_error(report.items)
            return report
        except Exception as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            if repr(exc) != str(exc):
                report.error += f" (diagnostic: {exc!r})"
            report.error += "\n" + "\n".join(traceback.format_exc().strip().splitlines()[-12:])
            return report

    def write_arguments(self, request: MeshingWriteRequest) -> MeshingWriteReport:
        report = MeshingWriteReport(
            workflow_type=request.workflow_type,
            status="failed",
            verified=request.verify,
        )
        try:
            workflow = self._get_workflow(request.workflow_type)
            # Group reads by task so each task is fetched once. Update Boundaries
            # is verified from its staged command arguments here; the live table
            # is verified by a fresh remote read after the task executes.
            grouped: dict[tuple[tuple[str, ...], str | None], list[MeshingPresetItem]] = {}
            for item in request.items:
                if item.value_mode == "at_use":
                    continue
                key = (tuple(item.task_path), item.compound_child_name)
                grouped.setdefault(key, []).append(item)

            for (task_path_tuple, child_name), items in grouped.items():
                try:
                    task = _find_task(workflow, list(task_path_tuple))
                    state: dict[str, Any] = {}
                    for item in items:
                        _merge_state(state, item.argument_path, item.value)
                    target = task
                    if child_name:
                        child = _find_compound_child(task, child_name)
                        if child is None:
                            if request.create_compound_child:
                                child = _create_child(task, state)
                            else:
                                raise LookupError(f"Compound child was not found: {child_name}")
                        target = child
                    internal_state = (
                        _update_boundary_previous_state(target, state)
                        if task_path_tuple == ("update_boundaries",) and child_name is None
                        else {}
                    )
                    state.update(internal_state)
                    if task_path_tuple == ("update_boundaries",) and child_name is None:
                        _write_boundary_argument_state(target, state)
                    else:
                        _write_argument_state(target, state)
                    defer_boundary_verification = (
                        task_path_tuple == ("update_boundaries",) and child_name is None
                    )
                    if defer_boundary_verification:
                        report.verified = False
                        actual_state: dict[str, Any] = {}
                    else:
                        actual_state = _read_argument_state(target)
                    for item in items:
                        if defer_boundary_verification:
                            actual = None
                            success = True
                            message = (
                                "Boundary mapping will be checked after Update Boundaries executes."
                            )
                        else:
                            actual = _read_state_path(actual_state, item.argument_path)
                            schema_argument = MESHING_SCHEMA_INDEX.get_argument(
                                request.workflow_type,
                                item.task_path,
                                item.argument_path,
                                item.compound_child_name,
                            )
                            value_type = (
                                str(schema_argument.get("value_type")) if schema_argument else None
                            )
                            success = not request.verify or _values_equal(
                                item.value, actual, value_type
                            )
                            message = "" if success else "Meshing readback did not match."
                        report.results.append(
                            MeshingArgumentWriteResult(
                                task_path=item.task_path,
                                argument_path=item.argument_path,
                                compound_child_name=item.compound_child_name,
                                expected=item.value,
                                actual=cast(MeshingPresetValue | None, actual),
                                success=success,
                                message=message,
                            )
                        )
                    for argument_name, expected in internal_state.items():
                        if defer_boundary_verification:
                            continue
                        actual = _read_state_path(actual_state, [argument_name])
                        success = not request.verify or _values_equal(expected, actual)
                        report.results.append(
                            MeshingArgumentWriteResult(
                                task_path=list(task_path_tuple),
                                argument_path=[argument_name],
                                compound_child_name=child_name,
                                expected=cast(MeshingPresetValue, expected),
                                actual=cast(MeshingPresetValue | None, actual),
                                success=success,
                                message=(
                                    ""
                                    if success
                                    else "Fluent's previous boundary state did not match."
                                ),
                            )
                        )
                except Exception as exc:
                    for item in items:
                        report.results.append(
                            MeshingArgumentWriteResult(
                                task_path=item.task_path,
                                argument_path=item.argument_path,
                                compound_child_name=item.compound_child_name,
                                expected=item.value,
                                actual=None,
                                success=False,
                                message=f"{type(exc).__name__}: {exc}",
                            )
                        )
            report.status = (
                "success"
                if report.results and all(result.success for result in report.results)
                else "failed"
            )
            if report.status == "failed":
                report.error = "One or more Meshing arguments failed to write or verify."
            return report
        except Exception as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            return report

    def apply_preset(
        self,
        preset: MeshingPresetDocument,
        model_path: str,
        *,
        import_geometry: bool = True,
    ) -> MeshingApplyReport:
        workflow = self._get_workflow(preset.workflow_type)
        _debug(f"workflow ready type={preset.workflow_type}")
        report = MeshingApplyReport(
            workflow_type=preset.workflow_type,
            status="failed",
            stopped_before=list(STOP_TASKS),
        )

        try:
            if import_geometry:
                path = Path(model_path).expanduser().resolve()
                if not path.is_file():
                    raise FileNotFoundError(f"Meshing geometry file does not exist: {path}")
                if preset.workflow_type == "watertight":
                    import_task = _find_task(workflow, ["import_geometry"])
                    import_options: dict[str, Any] = {}
                    for item in preset.items:
                        if (
                            item.task_path == ["import_geometry"]
                            and item.value_mode == "fixed"
                            and item.argument_path[-1]
                            not in {"file_name", "file_names", "mesh_file_name"}
                        ):
                            _merge_state(import_options, item.argument_path, item.value)
                    if import_options:
                        _write_argument_state(import_task, import_options)
                    _write_argument_state(import_task, {"file_name": str(path)})
                    import_state = _normalize_state(import_task.arguments.get_state())
                    _debug(f"import file_name={import_state.get('file_name')}")
                    _debug(f"importing geometry {path}")
                    import_task()
                else:
                    part_management = getattr(workflow, "part_management", None)
                    if part_management is None:
                        raise RuntimeError("Fault-tolerant workflow has no part management API.")
                    _debug(f"loading FTM geometry {path}")
                    part_management.LoadFmdFile(FilePath=str(path), FileUnit="m")
                    import_task = _find_task(workflow, ["import_cad_and_part_management"])
                    _write_argument_state(import_task, {"file_loaded": "yes"})
                    import_task()
                _debug("geometry import complete")
                report.imported_model = str(path)

            _debug("validating geometry names")
            name_checks, missing_names = _validate_preset_names(workflow, preset)
            report.name_checks = name_checks
            report.missing_names = missing_names
            if missing_names:
                report.error = "Missing required Meshing names: " + ", ".join(missing_names)
                return report

            grouped: dict[tuple[tuple[str, ...], str | None], list[MeshingPresetItem]] = {}
            for item in preset.items:
                if item.value_mode == "at_use" or (
                    item.task_path == ["import_geometry"]
                    and (
                        import_geometry
                        or item.argument_path[-1] in {"file_name", "file_names", "mesh_file_name"}
                    )
                ):
                    continue
                key = (tuple(item.task_path), item.compound_child_name)
                grouped.setdefault(key, []).append(item)

            for (task_path_tuple, child_name), items in grouped.items():
                task_path = list(task_path_tuple)
                task = _find_task(workflow, task_path)
                _debug(f"applying task={'.'.join(task_path)} child={child_name}")
                state: dict[str, Any] = {}
                for item in items:
                    _merge_state(state, item.argument_path, item.value)

                target_task = task
                if child_name:
                    target_task = _create_child(task, state)
                    _debug(f"compound child created for {task_path[-1]}")
                    report.created_children.append(f"{'.'.join(task_path)}[{child_name}]")
                _write_argument_state(target_task, state)

                raw_state = _normalize_state(target_task.arguments.get_state())
                _debug(f"readback task={'.'.join(task_path)} child={child_name}")
                for item in items:
                    actual = _read_state_path(raw_state, item.argument_path)
                    schema_argument = MESHING_SCHEMA_INDEX.get_argument(
                        preset.workflow_type,
                        item.task_path,
                        item.argument_path,
                        item.compound_child_name,
                    )
                    value_type = str(schema_argument.get("value_type")) if schema_argument else None
                    success = _values_equal(item.value, actual, value_type)
                    report.results.append(
                        MeshingArgumentWriteResult(
                            task_path=item.task_path,
                            argument_path=item.argument_path,
                            compound_child_name=item.compound_child_name,
                            expected=item.value,
                            actual=cast(MeshingPresetValue | None, actual),
                            success=success,
                            message="" if success else "Meshing readback did not match.",
                        )
                    )

            report.status = (
                "success" if all(result.success for result in report.results) else "failed"
            )
            if report.status == "failed":
                report.error = "One or more Meshing arguments failed readback verification."
            return report
        except Exception as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            if repr(exc) != str(exc):
                report.error += f" (diagnostic: {exc!r})"
            report.error += "\n" + "\n".join(traceback.format_exc().strip().splitlines()[-12:])
            return report

    def execute_task(
        self,
        workflow_type: str,
        task_path: list[str],
    ) -> MeshingTaskExecutionReport:
        """Execute one workflow task and return its console-facing result."""
        report = MeshingTaskExecutionReport(
            status="failed",
            task_path=task_path,
            output=[f"execute {'/'.join(task_path)}"],
        )
        try:
            workflow = self._get_workflow(workflow_type)
            task = _find_task(workflow, task_path)
            if task_path == ["update_boundaries"]:
                before = _boundary_state_summary(_read_argument_state(task))
                report.output.append(
                    "Update Boundaries arguments before execution (cached): " + repr(before)
                )
                fresh_before = _boundary_state_summary(_read_argument_state(task, fresh=True))
                report.output.append(
                    "Update Boundaries arguments before execution (fresh Fluent readback): "
                    + repr(fresh_before)
                )
            result = task()
            if task_path == ["update_boundaries"]:
                cached_after = _boundary_state_summary(_read_argument_state(task))
                report.output.append(
                    "Update Boundaries state after execution (cached): " + repr(cached_after)
                )
                fresh_after = _boundary_state_summary(_read_argument_state(task, fresh=True))
                report.output.append(
                    "Update Boundaries state after execution (fresh Fluent readback): "
                    + repr(fresh_after)
                )
            report.output.append("Task completed." if result is None else str(result))
            if result is False:
                report.message = f"{'/'.join(task_path)} returned False."
                report.output.append(report.message)
                return report
            report.status = "success"
            report.message = f"{'/'.join(task_path)} completed."
        except Exception as exc:
            report.message = f"{type(exc).__name__}: {exc}"
            diagnostic = repr(exc)
            if diagnostic != str(exc):
                report.message += f" (diagnostic: {diagnostic})"
            report.output.append(report.message)
            report.output.extend(traceback.format_exc().strip().splitlines()[-12:])
        return report

    def reset_workflow(self, workflow_type: str) -> None:
        """Drop the cached workflow wrapper so the next model starts from a clean tree."""
        self._workflow = None
        self._workflow_type = None
        self._get_workflow(workflow_type)

    def available_task_names(self, workflow_type: str) -> list[str]:
        workflow = self._get_workflow(workflow_type)
        return [
            str(_safe_call(getattr(task, "python_name", None), "")) for task in workflow.tasks()
        ]

    def inspect_reference_labels(self, model_path: str) -> list[str]:
        """Import reference geometry and read label selectors from the live workflow."""
        report = self.apply_preset(
            MeshingPresetDocument(
                schema_version=2, fluent_version="25.2.0", workflow_type="watertight", items=[]
            ),
            model_path,
        )
        if report.status != "success":
            raise RuntimeError(report.error or "Reference geometry import failed.")
        labels: set[str] = set()
        workflow = self._get_workflow("watertight")
        for task in _walk_live_tasks(list(workflow.tasks())):
            python_name = str(_safe_call(getattr(task, "python_name", None), ""))
            try:
                arguments = describe_task_arguments(task, python_name)
            except Exception:
                continue
            stack = list(arguments)
            while stack:
                argument = stack.pop()
                name = str(argument.get("name") or "")
                if _selector_kind(name) == "label":
                    for value in argument.get("allowed_values") or []:
                        labels.update(_name_values(value))
                    labels.update(_name_values(argument.get("current_value")))
                stack.extend(argument.get("children") or [])
        return sorted(labels)

    def register_transcript_callback(self, callback: Callable[[str], None]) -> str | None:
        session = self._ensure_session()
        transcript = getattr(session, "transcript", None)
        if transcript is None:
            return None
        self._transcript_callback_id = transcript.register_callback(callback)
        return str(self._transcript_callback_id)

    def unregister_transcript_callback(self) -> None:
        if self._transcript_callback_id is None or self._session is None:
            return
        transcript = getattr(self._session, "transcript", None)
        if transcript is not None:
            transcript.unregister_callback(self._transcript_callback_id)
        self._transcript_callback_id = None

    def read_current_task(self) -> str | None:
        parameter = self._ensure_session().workflow.Workflow.CurrentTask
        value = parameter.get_state()
        return str(value).strip() if value is not None else None

    def register_current_task_callback(self, callback: Callable[[str], None]) -> bool:
        self.unregister_current_task_callback()
        try:
            parameter = self._ensure_session().workflow.Workflow.CurrentTask
            self._current_task_subscription = parameter.add_on_changed(
                lambda changed: callback(str(changed.get_state()).strip())
            )
            return True
        except Exception:
            self._current_task_subscription = None
            return False

    def unregister_current_task_callback(self) -> None:
        subscription = self._current_task_subscription
        self._current_task_subscription = None
        if subscription is not None:
            with contextlib.suppress(Exception):
                subscription.unsubscribe()

    def _ensure_session(self) -> Any:
        if self._session is None or not self._is_active():
            raise RuntimeError("Fluent Meshing is not connected.")
        return self._session

    def _get_workflow(self, workflow_type: str) -> Any:
        session = self._ensure_session()
        if self._workflow is not None and self._workflow_type == workflow_type:
            return self._workflow
        try:
            workflow = (
                session.watertight() if workflow_type == "watertight" else session.fault_tolerant()
            )
        except TypeError as exc:
            if self._connection_mode == "attach" and "StringVector" in str(exc):
                raise RuntimeError(
                    "Fluent Meshing attach mode is connected, but PyFluent cannot read the "
                    "Fluent 2025 R2 legacy workflow arguments. Use launch mode for read/write."
                ) from exc
            raise
        self._workflow = workflow
        self._workflow_type = workflow_type
        return workflow

    def _is_active(self) -> bool:
        if self._session is None:
            return False
        try:
            return bool(self._session.is_active())
        except Exception:
            return True

    @staticmethod
    def _load_pyfluent() -> Any:
        import ansys.fluent.core as pyfluent  # type: ignore[import-untyped]

        return pyfluent
