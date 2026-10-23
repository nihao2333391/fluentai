"""Inspect Fluent 2025 R2 solver branches used by catalog expansion."""

from __future__ import annotations

import json
from pathlib import Path

import ansys.fluent.core as pyfluent

CASE = Path(r"D:\Fluent AI\ansys-runs\compat-smoke-20261021-170520\01_mesh.cas.h5")
FLUENT = Path(r"D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe")


def compact(value: object, depth: int = 0) -> object:
    if depth >= 3:
        return str(value)
    if isinstance(value, dict):
        return {str(key): compact(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [compact(item, depth + 1) for item in value[:20]]
    return value


def main() -> int:
    session = pyfluent.launch_fluent(
        fluent_path=str(FLUENT),
        product_version="25.2.0",
        dimension=3,
        precision="double",
        processor_count=1,
        mode="solver",
        ui_mode="no_gui",
        py=False,
        start_timeout=300,
        cleanup_on_exit=True,
        start_watchdog=False,
        start_transcript=False,
    )
    try:
        session.settings.file.read_case(file_name=str(CASE))
        output: dict[str, object] = {}
        for name in ("methods", "controls", "initialization", "run_calculation"):
            node = getattr(session.settings.solution, name)
            output[name] = {
                "state": compact(node.get_state()),
                "attributes": [item for item in dir(node) if not item.startswith("_")],
            }
        boundaries = session.settings.setup.boundary_conditions
        boundary_names = list(boundaries.get_state().keys())
        output["boundary_names"] = boundary_names
        if boundary_names:
            output["boundary_first"] = compact(
                boundaries[boundary_names[0]].get_state()
            )
        output["boundary_state"] = compact(boundaries.get_state())
        materials = session.settings.setup.materials
        output["material_attributes"] = [
            item for item in dir(materials) if not item.startswith("_")
        ]
        if hasattr(materials, "fluid"):
            output["fluid_materials"] = list(materials.fluid.get_state().keys())
            output["fluid_states"] = {
                name: compact(materials.fluid[name].get_state())
                for name in materials.fluid.get_state().keys()
            }
        candidates = {
            "flow_scheme": session.settings.solution.methods.p_v_coupling.flow_scheme,
            "gradient_scheme": session.settings.solution.methods.spatial_discretization.gradient_scheme,
            "initialization_type": session.settings.solution.initialization.initialization_type,
            "reference_frame": session.settings.solution.initialization.reference_frame,
        }
        output["enum_candidates"] = {
            name: {
                "state": node.get_state(),
                "allowed": node.allowed_values(),
            }
            for name, node in candidates.items()
        }
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        session.exit()


if __name__ == "__main__":
    raise SystemExit(main())
