"""Load generated Fluent Meshing schemas and validate presets against them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain import (
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingPresetValidationReport,
    MeshingSchemaSummary,
    MeshingWorkflowType,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_DIR = PROJECT_ROOT / "docs" / "meshing"


class MeshingSchemaIndex:
    def __init__(self, schemas: dict[MeshingWorkflowType, dict[str, Any]]) -> None:
        self.schemas = schemas
        self._task_index: dict[MeshingWorkflowType, dict[tuple[str, ...], dict[str, Any]]] = {}
        for workflow_type, schema in schemas.items():
            self._task_index[workflow_type] = {}
            self._index_tasks(workflow_type, schema.get("tasks") or [], ())

    @classmethod
    def from_directory(cls, directory: Path | str = DEFAULT_SCHEMA_DIR) -> MeshingSchemaIndex:
        root = Path(directory)
        schemas: dict[MeshingWorkflowType, dict[str, Any]] = {}
        for workflow_type in ("watertight", "fault-tolerant"):
            path = root / f"fluent-meshing-25.2-{workflow_type}.schema.json"
            schemas[workflow_type] = json.loads(path.read_text(encoding="utf-8"))
        return cls(schemas)

    def _index_tasks(
        self,
        workflow_type: MeshingWorkflowType,
        tasks: list[dict[str, Any]],
        parent_path: tuple[str, ...],
    ) -> None:
        for task in tasks:
            python_name = task.get("python_name")
            if not isinstance(python_name, str) or not python_name:
                continue
            path = (*parent_path, python_name)
            self._task_index[workflow_type][path] = task
            self._index_tasks(workflow_type, task.get("children") or [], path)

    def summaries(self) -> list[MeshingSchemaSummary]:
        summaries: list[MeshingSchemaSummary] = []
        for workflow_type, schema in self.schemas.items():
            tasks = list(self._task_index[workflow_type].values())
            argument_count = sum(
                _count_arguments(task.get("arguments") or [])
                + _count_arguments((task.get("child_template") or {}).get("arguments") or [])
                for task in tasks
            )
            summaries.append(
                MeshingSchemaSummary(
                    workflow_type=workflow_type,
                    schema_id=(
                        f"fluent-meshing-{schema.get('fluent_version', '25.2.0')[:4]}-"
                        f"{workflow_type}"
                    ),
                    fluent_version=str(schema.get("fluent_version", "25.2.0")),
                    task_count=len(schema.get("tasks") or []),
                    argument_count=argument_count,
                )
            )
        return summaries

    def get_argument(
        self,
        workflow_type: MeshingWorkflowType,
        task_path: list[str],
        argument_path: list[str],
        compound_child_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the schema entry for one task or compound-child argument."""
        task = self._task_index.get(workflow_type, {}).get(tuple(task_path))
        if task is None:
            return None
        if compound_child_name:
            template = task.get("child_template")
            if not isinstance(template, dict):
                return None
            candidates = list(template.get("arguments") or [])
        else:
            candidates = list(task.get("arguments") or [])
        argument: dict[str, Any] | None = None
        for part in argument_path:
            argument = next((entry for entry in candidates if entry.get("name") == part), None)
            if argument is None:
                return None
            candidates = list(argument.get("children") or [])
        return argument

    def get_task(
        self,
        workflow_type: MeshingWorkflowType,
        task_path: list[str],
    ) -> dict[str, Any] | None:
        """Return one schema task by its full workflow path."""
        return self._task_index.get(workflow_type, {}).get(tuple(task_path))

    def validate(self, preset: MeshingPresetDocument) -> MeshingPresetValidationReport:
        schema_id = f"fluent-meshing-25.2-{preset.workflow_type}"
        errors: list[str] = []
        task_index = self._task_index.get(preset.workflow_type, {})
        if not task_index:
            errors.append(f"No schema is available for workflow type {preset.workflow_type!r}.")

        seen: set[tuple[tuple[str, ...], tuple[str, ...], str | None]] = set()
        for item in preset.items:
            try:
                self._validate_item(item, task_index, seen)
            except ValueError as exc:
                errors.append(str(exc))
        return MeshingPresetValidationReport(
            valid=not errors,
            errors=errors,
            schema_id=schema_id,
            item_count=len(preset.items),
        )

    @staticmethod
    def _validate_item(
        item: MeshingPresetItem,
        task_index: dict[tuple[str, ...], dict[str, Any]],
        seen: set[tuple[tuple[str, ...], tuple[str, ...], str | None]],
    ) -> None:
        task_path = tuple(item.task_path)
        argument_path = tuple(item.argument_path)
        child_key = (item.compound_child_name or "").strip() or None
        key = (task_path, argument_path, child_key)
        if key in seen:
            owner = f"[{child_key}]" if child_key else ""
            raise ValueError(
                "Duplicate Meshing preset item: "
                f"{'.'.join(task_path)}{owner}.{'.'.join(argument_path)}"
            )
        seen.add(key)

        task = task_index.get(task_path)
        if task is None:
            raise ValueError(f"Unknown Meshing task path: {'.'.join(task_path)}")

        compound_child_name = (item.compound_child_name or "").strip()
        if item.compound_child_name is not None and not compound_child_name:
            raise ValueError(f"Compound child name cannot be empty for task {'.'.join(task_path)}")

        template = task.get("child_template")
        if compound_child_name:
            if task.get("task_type") != "Compound" or not isinstance(template, dict):
                raise ValueError(
                    f"Task {'.'.join(task_path)} does not support compound child presets"
                )
            candidates = list(template.get("arguments") or [])
        else:
            candidates = list(task.get("arguments") or [])

        argument: dict[str, Any] | None = None
        for part in argument_path:
            argument = next((entry for entry in candidates if entry.get("name") == part), None)
            if argument is None:
                scope = "compound child" if compound_child_name else "task"
                raise ValueError(
                    f"Unknown Meshing {scope} argument path: "
                    f"{'.'.join(task_path)}.{'.'.join(argument_path)}"
                )
            candidates = list(argument.get("children") or [])

        if argument is None:
            raise ValueError(f"Empty Meshing argument path for task {'.'.join(task_path)}")
        if argument.get("editable") is False or argument.get("read_only") is True:
            owner = (
                f"{'.'.join(task_path)}[{compound_child_name}]"
                if compound_child_name
                else ".".join(task_path)
            )
            raise ValueError(f"Meshing argument is read-only: {owner}.{'.'.join(argument_path)}")

        allowed = argument.get("allowed_values")
        if allowed is not None and item.value not in allowed:
            raise ValueError(
                f"Value for {'.'.join(argument_path)} must be one of {allowed!r}; "
                f"got {item.value!r}"
            )

        expected_type = argument.get("value_type")
        if not _matches_type(item.value, expected_type):
            raise ValueError(
                f"Value for {'.'.join(argument_path)} has type "
                f"{type(item.value).__name__}; expected {expected_type}"
            )


def _matches_type(value: Any, expected_type: Any) -> bool:
    if expected_type in (None, "null"):
        return True
    if expected_type == "bool":
        return isinstance(value, bool)
    if expected_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type in ("list", "RepeatedScalarContainer"):
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _count_arguments(arguments: list[dict[str, Any]]) -> int:
    return sum(1 + _count_arguments(argument.get("children") or []) for argument in arguments)


MESHING_SCHEMA_INDEX = MeshingSchemaIndex.from_directory()
