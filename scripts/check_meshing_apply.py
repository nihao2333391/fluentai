"""Real Fluent Meshing apply gate: names, child creation, readback, no meshing."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.domain import (
    FluentConnectionConfig,
    MeshingPresetDocument,
    MeshingPresetItem,
)
from app.meshing.pyfluent_adapter import PyFluentMeshingAdapter
from app.meshing.schema_index import MESHING_SCHEMA_INDEX

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_GEOMETRY = Path(
    r"D:\Fluent AI\wql.meshed_files\dp0\FFF\Fluent\FM_ComputerOfWeiJiabao_9648\wenqiuli.dsco.pmdb"
)
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "meshing-m8.4.json"


def _preset(*, missing_name: bool = False) -> MeshingPresetDocument:
    items = [
        MeshingPresetItem(
            task_path=["import_geometry"],
            argument_path=["length_unit"],
            value="m",
        ),
        MeshingPresetItem(
            task_path=["create_surface_mesh"],
            argument_path=["cfd_surface_mesh_controls", "max_size"],
            value=0.002,
        ),
    ]
    controls = (
        [("wall-big-missing", "wall-big-missing", 0.001)]
        if missing_name
        else [("wall-big", "wall-big", 0.001), ("wall-small", "wall-small", 0.0005)]
    )
    for child_name, label, size in controls:
        items.extend(
            [
                MeshingPresetItem(
                    task_path=["add_local_sizing"],
                    argument_path=["boi_control_name"],
                    value=child_name,
                    compound_child_name=child_name,
                ),
                MeshingPresetItem(
                    task_path=["add_local_sizing"],
                    argument_path=["boi_execution"],
                    value="Face Size",
                    compound_child_name=child_name,
                ),
                MeshingPresetItem(
                    task_path=["add_local_sizing"],
                    argument_path=["boi_face_label_list"],
                    value=[label],
                    compound_child_name=child_name,
                ),
                MeshingPresetItem(
                    task_path=["add_local_sizing"],
                    argument_path=["boi_size"],
                    value=size,
                    compound_child_name=child_name,
                ),
            ]
        )
    if not missing_name:
        items.extend(
            [
                MeshingPresetItem(
                    task_path=["add_boundary_layer"],
                    argument_path=["bl_control_name"],
                    value="smooth-transition_1",
                    compound_child_name="smooth-transition_1",
                ),
                MeshingPresetItem(
                    task_path=["add_boundary_layer"],
                    argument_path=["bl_label_list"],
                    value=["wall-big", "wall-small"],
                    compound_child_name="smooth-transition_1",
                ),
                MeshingPresetItem(
                    task_path=["add_boundary_layer"],
                    argument_path=["offset_method_type"],
                    value="smooth-transition",
                    compound_child_name="smooth-transition_1",
                ),
                MeshingPresetItem(
                    task_path=["add_boundary_layer"],
                    argument_path=["number_of_layers"],
                    value=3,
                    compound_child_name="smooth-transition_1",
                ),
            ]
        )
    return MeshingPresetDocument(workflow_type="watertight", items=items)


def _ftm_preset() -> MeshingPresetDocument:
    return MeshingPresetDocument(
        workflow_type="fault-tolerant",
        items=[
            MeshingPresetItem(
                task_path=["mesh_controls_table"],
                argument_path=["global_max"],
                value=1.0,
            ),
            MeshingPresetItem(
                task_path=["mesh_controls_table"],
                argument_path=["target_growth_rate"],
                value=1.2,
            ),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--geometry", default=str(DEFAULT_GEOMETRY))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--ui-mode", default="no_gui")
    args = parser.parse_args()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "status": "failed",
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    adapter = PyFluentMeshingAdapter()
    try:
        geometry = Path(args.geometry)
        if not geometry.is_file():
            raise FileNotFoundError(geometry)
        for label, preset in (
            ("missing_name", _preset(missing_name=True)),
            ("valid", _preset()),
            ("fault_tolerant", _ftm_preset()),
        ):
            validation = MESHING_SCHEMA_INDEX.validate(preset)
            if not validation.valid:
                raise ValueError(f"Generated preset is invalid: {validation.errors}")

        connection = adapter.connect(
            FluentConnectionConfig(
                mode="launch",
                fluent_path=str(Path(args.fluent_exe)),
                product_version="25.2.0",
                processor_count=1,
                ui_mode=args.ui_mode,
                start_timeout=300,
                cleanup_on_exit=True,
            )
        )
        summary["connection"] = connection.model_dump(mode="json")

        missing_report = adapter.apply_preset(
            _preset(missing_name=True), str(geometry), import_geometry=True
        )
        summary["missing_name_report"] = missing_report.model_dump(mode="json")
        if missing_report.status != "failed" or not missing_report.missing_names:
            raise AssertionError("Missing-name preset was not rejected.")

        report = adapter.apply_preset(_preset(), str(geometry), import_geometry=True)
        summary["apply_report"] = report.model_dump(mode="json")
        if report.status != "success":
            raise AssertionError(report.error or "Meshing apply failed.")
        if report.stopped_before != [
            "Generate the Surface Mesh",
            "Generate the Volume Mesh",
        ]:
            raise AssertionError("Apply report did not stop before mesh generation.")
        if len(report.created_children) != 3:
            raise AssertionError(
                f"Expected 3 compound child tasks, got {report.created_children!r}."
            )
        if not all(result.success for result in report.results):
            raise AssertionError("One or more Meshing values failed readback.")

        fault_tolerant_report = adapter.apply_preset(
            _ftm_preset(), str(geometry), import_geometry=True
        )
        summary["fault_tolerant_report"] = fault_tolerant_report.model_dump(mode="json")
        if fault_tolerant_report.status != "success":
            raise AssertionError(
                fault_tolerant_report.error or "Fault-tolerant Meshing apply failed."
            )
        if not all(result.success for result in fault_tolerant_report.results):
            raise AssertionError("Fault-tolerant Meshing readback failed.")
        summary["status"] = "passed"
        summary["marker"] = "M8_APPLY_CHECK_PASSED"
        return 0
    except Exception as exc:  # noqa: BLE001
        summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        try:
            adapter.disconnect()
        except Exception as exc:  # noqa: BLE001
            summary.setdefault("cleanup_error", f"{type(exc).__name__}: {exc}")
        summary["finished_at_utc"] = datetime.now(UTC).isoformat()
        report_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
