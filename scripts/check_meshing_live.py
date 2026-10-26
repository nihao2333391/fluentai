"""Validate a real live Meshing session through import, preset write, and execution."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.database import Database
from app.domain import (
    FluentConnectionConfig,
    MeshingAutomationCreate,
    MeshingLiveSessionStart,
    MeshingLiveStepRequest,
    MeshingPresetDocument,
    MeshingPresetItem,
    ModelCreate,
)
from app.meshing.pyfluent_adapter import PyFluentMeshingAdapter
from app.repositories.meshing_automations import MeshingAutomationRepository
from app.repositories.models import ModelRepository
from app.services.meshing_service import MeshingService

DEFAULT_FLUENT_EXE = Path(
    r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe"
)
DEFAULT_GEOMETRY = Path(
    r"D:\Fluent AI\wql.meshed_files\dp0\FFF\Fluent\FM_ComputerOfWeiJiabao_9648\wenqiuli.dsco.pmdb"
)
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "poc" / "reports" / "meshing-live-check.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fluent-exe", default=str(DEFAULT_FLUENT_EXE))
    parser.add_argument("--geometry", default=str(DEFAULT_GEOMETRY))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--ui-mode", default="no_gui")
    parser.add_argument("--start-only", action="store_true")
    args = parser.parse_args()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary: dict[str, object] = {
        "status": "failed",
        "started_at_utc": datetime.now(UTC).isoformat(),
    }
    adapter = PyFluentMeshingAdapter()
    with tempfile.TemporaryDirectory(prefix="fluent-ai-live-") as directory:
        database = Database(Path(directory) / "live.db")
        database.initialize()
        service = MeshingService(database, adapter)
        try:
            geometry = Path(args.geometry)
            if not geometry.is_file():
                raise FileNotFoundError(geometry)
            model = ModelRepository(database).create(
                ModelCreate(
                    name=geometry.stem, file_path=str(geometry), tags=["meshing-live"]
                )
            )
            automation = MeshingAutomationRepository(database).create(
                MeshingAutomationCreate(
                    name="Live Meshing verification",
                    model_family="Venturi",
                    reference_model_id=model.id,
                    preset=MeshingPresetDocument(
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
                    ),
                )
            )
            snapshot = service.start_live_session(
                MeshingLiveSessionStart(
                    automation_id=automation.id,
                    model_ids=[model.id],
                    connection=FluentConnectionConfig(
                        mode="launch",
                        fluent_path=str(Path(args.fluent_exe)),
                        product_version="25.2.0",
                        processor_count=1,
                        ui_mode=args.ui_mode,
                        start_timeout=300,
                        cleanup_on_exit=True,
                    ),
                )
            )
            summary["started_session"] = snapshot.model_dump(mode="json")
            if snapshot.status == "starting":
                for _ in range(240):
                    time.sleep(0.25)
                    snapshot = service.get_live_session(snapshot.session_id)
                    if snapshot.status in {"waiting", "failed", "completed", "stopped"}:
                        break
                summary["started_session"] = snapshot.model_dump(mode="json")
            if snapshot.status != "waiting":
                raise AssertionError(
                    snapshot.message or "Live session did not connect."
                )
            service.enter_live_step(
                snapshot.session_id, MeshingLiveStepRequest(step_index=0)
            )
            imported = service.execute_live_step(
                snapshot.session_id, MeshingLiveStepRequest(step_index=0)
            )
            summary["imported_geometry"] = imported.model_dump(mode="json")
            if imported.status != "success":
                raise AssertionError(imported.message or "Geometry import failed.")
            snapshot = imported.snapshot
            summary["started_session"] = snapshot.model_dump(mode="json")
            if args.start_only:
                summary["status"] = "passed"
                summary["marker"] = "MESHING_LIVE_START_PASSED"
                return 0
            entered = service.enter_live_step(
                snapshot.session_id, MeshingLiveStepRequest(step_index=2)
            )
            summary["entered_surface_step"] = entered.model_dump(mode="json")
            if entered.status != "success" or entered.read_report is None:
                raise AssertionError(
                    entered.message or "Surface step preset write failed."
                )
            executed = service.execute_live_step(
                snapshot.session_id, MeshingLiveStepRequest(step_index=2)
            )
            summary["executed_surface_step"] = executed.model_dump(mode="json")
            if executed.status != "success":
                raise AssertionError(
                    executed.message or "Surface mesh task execution failed."
                )
            summary["status"] = "passed"
            summary["marker"] = "MESHING_LIVE_CHECK_PASSED"
            return 0
        except Exception as exc:  # noqa: BLE001
            summary["error"] = {"type": type(exc).__name__, "message": str(exc)}
            return 1
        finally:
            try:
                service.disconnect()
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
