"""Validate the M6 PyFluent adapter against a real Fluent 2025 R2 session."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.domain import (
    FluentConnectionConfig,
    PresetDocument,
    PresetItem,
)
from app.fluent.catalog import FLUENT_252_CATALOG
from app.fluent.comparison import preset_values_equal
from app.fluent.pyfluent_adapter import PyFluentAdapter

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_CASE = Path(
    r"D:\Fluent AI\ansys-runs\compat-smoke-20261021-170520\01_mesh.cas.h5"
)
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "m6_fluent_adapter.json"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate FluentAdapter and SettingCatalog"
    )
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--case", default=str(DEFAULT_CASE))
    parser.add_argument(
        "--ui-mode",
        default="no_gui",
        choices=["no_gui", "no_graphics", "hidden_gui", "gui"],
    )
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    case_path = Path(args.case).expanduser().resolve()
    fluent_exe = Path(args.fluent_exe).expanduser().resolve()
    report: dict[str, Any] = {
        "status": "failed",
        "started_at_utc": utc_now(),
        "case": str(case_path),
        "fluent_executable": str(fluent_exe),
        "catalog_version": FLUENT_252_CATALOG.version,
        "catalog_size": len(FLUENT_252_CATALOG.list()),
    }
    adapter = PyFluentAdapter()
    try:
        if not case_path.is_file():
            raise FileNotFoundError(f"Case file does not exist: {case_path}")
        if not fluent_exe.is_file():
            raise FileNotFoundError(f"Fluent executable does not exist: {fluent_exe}")

        report["connection_status"] = adapter.connect(
            FluentConnectionConfig(
                mode="launch",
                fluent_path=str(fluent_exe),
                product_version="25.2.0",
                ui_mode=args.ui_mode,
                processor_count=1,
                cleanup_on_exit=True,
            )
        ).model_dump(mode="json")
        adapter.load_case(str(case_path))

        setting_ids = [
            definition.setting_id for definition in FLUENT_252_CATALOG.list()
        ]
        initial = adapter.read_settings(setting_ids)
        report["initial_values"] = initial
        report["read_count"] = len(initial)

        dynamic_ids = [
            definition.setting_id
            for definition in adapter.catalog.list()
            if definition.setting_id.startswith("material.fluid.")
        ]
        dynamic_initial = adapter.read_settings(dynamic_ids)
        density_ids = [item for item in dynamic_ids if item.endswith(".density")]
        viscosity_ids = [item for item in dynamic_ids if item.endswith(".viscosity")]
        if not density_ids or not viscosity_ids:
            raise RuntimeError("Dynamic fluid material properties were not discovered.")
        dynamic_desired = {
            density_ids[0]: float(dynamic_initial[density_ids[0]]) * 1.01,
            viscosity_ids[0]: float(dynamic_initial[viscosity_ids[0]]) * 1.01,
        }
        dynamic_apply = adapter.apply_preset(
            PresetDocument(
                fluent_version="25.2.0",
                items=[
                    PresetItem(
                        setting_id=setting_id,
                        type="float",
                        value=value,
                    )
                    for setting_id, value in dynamic_desired.items()
                ],
            )
        )
        dynamic_after = adapter.read_settings(list(dynamic_desired))
        dynamic_verified = dynamic_apply.status == "success" and all(
            preset_values_equal(dynamic_desired[setting_id], dynamic_after[setting_id])
            for setting_id in dynamic_desired
        )
        dynamic_restore = adapter.write_settings(
            [
                PresetItem(
                    setting_id=setting_id,
                    type="float",
                    value=dynamic_initial[setting_id],
                )
                for setting_id in dynamic_desired
            ]
        )
        dynamic_restored_values = adapter.read_settings(list(dynamic_desired))
        dynamic_restored = dynamic_restore.status == "success" and all(
            preset_values_equal(
                dynamic_initial[setting_id], dynamic_restored_values[setting_id]
            )
            for setting_id in dynamic_desired
        )
        report["dynamic_material"] = {
            "setting_ids": dynamic_ids,
            "apply_report": dynamic_apply.model_dump(mode="json"),
            "verified": dynamic_verified,
            "restored": dynamic_restored,
        }

        continuity = float(initial["residual.continuity"])
        area = float(initial["reference.area"])
        density = float(initial["reference.density"])
        desired = {
            "residual.continuity": continuity + 0.0001,
            "reference.area": area * 1.05,
            "reference.density": density * 1.05,
            "methods.flow_scheme": "SIMPLE"
            if initial["methods.flow_scheme"] != "SIMPLE"
            else "SIMPLEC",
            "methods.gradient_scheme": "green-gauss-cell-based"
            if initial["methods.gradient_scheme"] != "green-gauss-cell-based"
            else "least-square-cell-based",
            "controls.flow_equations": bool(initial["controls.flow_equations"]),
            "initialization.type": "standard"
            if initial["initialization.type"] != "standard"
            else "hybrid",
            "initialization.reference_frame": "absolute"
            if initial["initialization.reference_frame"] != "absolute"
            else "relative",
            "run_calculation.iterations": int(initial["run_calculation.iterations"])
            + 1,
            "run_calculation.reporting_interval": int(
                initial["run_calculation.reporting_interval"]
            )
            + 1,
        }
        apply_report = adapter.apply_preset(
            PresetDocument(
                fluent_version="25.2.0",
                items=[
                    PresetItem(
                        setting_id=setting_id,
                        type=FLUENT_252_CATALOG.get(setting_id).value_type,
                        value=value,
                    )
                    for setting_id, value in desired.items()
                ],
            )
        )
        report["apply_report"] = apply_report.model_dump(mode="json")
        if apply_report.status != "success":
            raise RuntimeError("Apply report did not succeed.")

        after_apply = adapter.read_settings(list(desired))
        report["after_apply"] = after_apply
        apply_verified = all(
            preset_values_equal(desired[setting_id], after_apply[setting_id])
            for setting_id in desired
        )

        restore_report = adapter.write_settings(
            [
                PresetItem(
                    setting_id=setting_id,
                    type=FLUENT_252_CATALOG.get(setting_id).value_type,
                    value=initial[setting_id],
                )
                for setting_id in desired
            ]
        )
        report["restore_report"] = restore_report.model_dump(mode="json")
        if restore_report.status != "success":
            raise RuntimeError("Restore report did not succeed.")

        final = adapter.read_settings(setting_ids)
        report["final_values"] = final
        restored = all(
            preset_values_equal(initial[setting_id], final[setting_id])
            for setting_id in setting_ids
        )
        passed = (
            len(initial) == 27
            and apply_verified
            and restored
            and dynamic_verified
            and dynamic_restored
        )
        report.update(
            {
                "status": "passed" if passed else "failed",
                "apply_verified": apply_verified,
                "restored": restored,
            }
        )
        return 0 if passed else 1
    except Exception as exc:  # noqa: BLE001
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        return 1
    finally:
        try:
            adapter.disconnect()
            report["disconnect"] = "success"
        except Exception as exc:  # noqa: BLE001
            report["disconnect"] = f"{type(exc).__name__}: {exc}"
        report["finished_at_utc"] = utc_now()
        write_json(Path(args.report), report)
        print(json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
