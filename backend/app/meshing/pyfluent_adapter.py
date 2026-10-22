"""PyFluent implementation of the dedicated Meshing workflow adapter."""

from __future__ import annotations

import ast
import math
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, cast

from ansys.fluent.core.workflow import camel_to_snake_case  # type: ignore[import-untyped]

from app.domain import (
    FluentConnectionConfig,
    FluentStatus,
    MeshingApplyReport,
    MeshingArgumentWriteResult,
    MeshingNameCheck,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingPresetValue,
)
from app.meshing.schema_index import MESHING_SCHEMA_INDEX
from app.meshing.workflow_inventory import describe_task_arguments

SELECTOR_ARGUMENT_PATTERN = re.compile(
    r"(_label_list|_zone_list|_region_list|_selection_list|_object_selection_list|"
    r"_object_list|_dead_regions_list|_region_scope)$"
)
STOP_TASKS = ["Generate the Surface Mesh", "Generate the Volume Mesh"]


def _debug(message: str) -> None:
    if os.environ.get("FLUENT_AI_DEBUG") == "1":
        print(f"[meshing-debug] {message}", file=sys.stderr, flush=True)


def _safe_call(value: Any, default: Any = None) -> Any:
    try:
        return value() if callable(value) else value
    except Exception:
        return default


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


def _normalize_state(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            camel_to_snake_case(str(key)): _normalize_state(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_state(item) for item in value]
    return value


def _read_state_path(state: Any, path: list[str]) -> Any:
    current = state
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


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

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        if self._session is not None and self._is_active():
            self.disconnect()

        pyfluent = self._pyfluent_module or self._load_pyfluent()
        if config.mode == "launch":
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
                "start_transcript": False,
            }
            if config.fluent_path:
                launch_kwargs["fluent_path"] = config.fluent_path
            self._session = pyfluent.launch_fluent(**launch_kwargs)
        else:
            if config.server_info_file:
                self._session = pyfluent.connect_to_fluent(
                    server_info_file_name=config.server_info_file,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=False,
                )
            else:
                if config.port is None:
                    raise ValueError("Attach mode requires a port or server-info file.")
                self._session = pyfluent.connect_to_fluent(
                    ip=config.host,
                    port=config.port,
                    password=config.password,
                    cleanup_on_exit=False,
                    start_transcript=False,
                )
        self._connection_mode = config.mode
        return self.status()

    def disconnect(self) -> None:
        session = self._session
        mode = self._connection_mode
        self._session = None
        self._connection_mode = None
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

    def apply_preset(
        self,
        preset: MeshingPresetDocument,
        model_path: str,
        *,
        import_geometry: bool = True,
    ) -> MeshingApplyReport:
        session = self._ensure_session()
        workflow = (
            session.watertight()
            if preset.workflow_type == "watertight"
            else session.fault_tolerant()
        )
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

            _debug("collecting name catalog")
            catalog = _collect_name_catalog(workflow)
            _debug(f"name catalog ready size={len(catalog)}")
            name_checks, missing_names = _validate_names(preset, catalog)
            report.name_checks = name_checks
            report.missing_names = missing_names
            if missing_names:
                report.error = "Missing required Meshing names: " + ", ".join(missing_names)
                return report

            grouped: dict[tuple[tuple[str, ...], str | None], list[MeshingPresetItem]] = {}
            for item in preset.items:
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
            return report

    def _ensure_session(self) -> Any:
        if self._session is None or not self._is_active():
            raise RuntimeError("Fluent Meshing is not connected.")
        return self._session

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
