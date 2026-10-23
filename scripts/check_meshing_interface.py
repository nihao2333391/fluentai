"""Real Fluent Meshing interface gate: connect, enumerate, read, write, restore."""

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
    MeshingArgumentReference,
    MeshingPresetDocument,
    MeshingPresetItem,
    MeshingReadRequest,
    MeshingWriteRequest,
)
from app.meshing.pyfluent_adapter import PyFluentMeshingAdapter

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_GEOMETRY = Path(
    r"D:\Fluent AI\wql.meshed_files\dp0\FFF\Fluent\FM_ComputerOfWeiJiabao_9648\wenqiuli.dsco.pmdb"
)
DEFAULT_REPORT = (
    PROJECT_ROOT / "docs" / "poc" / "reports" / "meshing-interface-check.json"
)


def _references() -> list[MeshingArgumentReference]:
    return [
        MeshingArgumentReference(
            task_path=["import_geometry"],
            argument_path=["file_format"],
        ),
        MeshingArgumentReference(
            task_path=["import_geometry"],
            argument_path=["length_unit"],
        ),
        MeshingArgumentReference(
            task_path=["add_local_sizing"],
            argument_path=["add_child"],
        ),
        MeshingArgumentReference(
            task_path=["create_surface_mesh"],
            argument_path=["cfd_surface_mesh_controls", "min_size"],
        ),
        MeshingArgumentReference(
            task_path=["create_surface_mesh"],
            argument_path=["cfd_surface_mesh_controls", "max_size"],
        ),
        MeshingArgumentReference(
            task_path=["create_volume_mesh"],
            argument_path=["volume_fill"],
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--geometry", default=str(DEFAULT_GEOMETRY))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--ui-mode", default="no_gui")
    parser.add_argument("--test-attach", action="store_true")
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

        summary["connection"] = adapter.connect(
            FluentConnectionConfig(
                mode="launch",
                fluent_path=str(Path(args.fluent_exe)),
                product_version="25.2.0",
                processor_count=1,
                ui_mode=args.ui_mode,
                start_timeout=300,
                cleanup_on_exit=True,
            )
        ).model_dump(mode="json")
        if not adapter.status().connected:
            raise AssertionError("Adapter did not report a connected session.")

        all_read = adapter.read_arguments(
            MeshingReadRequest(workflow_type="watertight")
        )
        summary["all_read"] = {
            "status": all_read.status,
            "task_count": len(all_read.task_names),
            "item_count": len(all_read.items),
            "found_count": sum(item.found for item in all_read.items),
            "errors": [item.error for item in all_read.items if item.error][:20],
        }
        if len(all_read.task_names) != 11:
            raise AssertionError(
                f"Expected 11 watertight tasks, got {all_read.task_names!r}."
            )
        if len(all_read.items) < 400:
            raise AssertionError(
                f"Only {len(all_read.items)} option references were enumerated."
            )

        direct = adapter.read_arguments(
            MeshingReadRequest(workflow_type="watertight", items=_references())
        )
        summary["direct_read"] = direct.model_dump(mode="json")
        sample = next(
            item
            for item in direct.items
            if item.task_path == ["import_geometry"]
            and item.argument_path == ["length_unit"]
            and item.found
        )
        if sample.value is None:
            raise AssertionError("Direct read did not return the import length unit.")

        direct_write = adapter.write_arguments(
            MeshingWriteRequest(
                workflow_type="watertight",
                verify=True,
                items=[
                    MeshingPresetItem(
                        task_path=sample.task_path,
                        argument_path=sample.argument_path,
                        value=sample.value,
                    )
                ],
            )
        )
        summary["direct_write"] = direct_write.model_dump(mode="json")
        if direct_write.status != "success":
            raise AssertionError(direct_write.error or "Direct Meshing write failed.")

        preset = MeshingPresetDocument(
            workflow_type="watertight",
            items=[
                MeshingPresetItem(
                    task_path=["import_geometry"],
                    argument_path=["length_unit"],
                    value="m",
                ),
                MeshingPresetItem(
                    task_path=["create_surface_mesh"],
                    argument_path=["cfd_surface_mesh_controls", "min_size"],
                    value=0.0005,
                ),
                MeshingPresetItem(
                    task_path=["create_surface_mesh"],
                    argument_path=["cfd_surface_mesh_controls", "max_size"],
                    value=0.002,
                ),
            ],
        )
        apply_report = adapter.apply_preset(preset, str(geometry), import_geometry=True)
        summary["apply_after_import"] = apply_report.model_dump(mode="json")
        if apply_report.status != "success":
            raise AssertionError(apply_report.error or "Meshing import/apply failed.")
        if not all(result.success for result in apply_report.results):
            raise AssertionError("Meshing apply readback verification failed.")

        if args.test_attach:
            properties = adapter._session.connection_properties  # type: ignore[attr-defined]
            host = str(getattr(properties, "ip", None) or "127.0.0.1")
            port = getattr(properties, "port", None)
            password = getattr(properties, "password", None)
            if port is None:
                raise AssertionError(
                    "Launched Fluent session did not expose an attach port."
                )
            attach_adapter = PyFluentMeshingAdapter()
            try:
                attach_status = attach_adapter.connect(
                    FluentConnectionConfig(
                        mode="attach",
                        host=host,
                        port=int(port),
                        password=str(password) if password is not None else None,
                        product_version="25.2.0",
                        ui_mode=args.ui_mode,
                    )
                )
                attach_read = attach_adapter.read_arguments(
                    MeshingReadRequest(
                        workflow_type="watertight",
                        items=[
                            MeshingArgumentReference(
                                task_path=["import_geometry"],
                                argument_path=["length_unit"],
                            )
                        ],
                    )
                )
                summary["attach"] = {
                    "status": attach_status.model_dump(mode="json"),
                    "read": attach_read.model_dump(mode="json"),
                    "read_write_supported": attach_read.status == "success",
                }
                if not attach_status.connected:
                    raise AssertionError(
                        "Fluent Meshing attach-mode connection failed."
                    )
                if attach_read.status != "success":
                    summary["attach"]["limitation"] = attach_read.error
            finally:
                attach_adapter.disconnect()

        summary["status"] = "passed"
        summary["marker"] = "MESHING_INTERFACE_CHECK_PASSED"
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
