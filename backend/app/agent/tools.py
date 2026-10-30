"""Deterministic boundary-layer calculations exposed to Agno as approved tools."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import math
from typing import Any

from agno.tools.websearch import WebSearchTools

from app.agent.retrieval import SOURCE_FILES, create_scoped_boundary_layer_search


def _as_json(value: dict[str, Any]) -> str:
    """Serialize tool output for Agno, which stringifies non-string results via str().

    Returning a JSON string keeps the payload parseable by downstream consumers
    (a plain dict would become a single-quoted Python repr that json.loads rejects).
    """
    return json.dumps(value, ensure_ascii=False)


class BoundaryLayerConfirmationRequired(Exception):
    """Raised when the Uniform estimate requires explicit range confirmation."""


def calculate_smooth_layers(
    first_cell_y_plus: float,
    target_outer_y_plus: float,
    growth_rate: float,
) -> dict[str, Any]:
    """Calculate the Smooth Transition layer count from y+ targets and growth rate."""
    y1, outer, ratio = map(float, (first_cell_y_plus, target_outer_y_plus, growth_rate))
    if not all(math.isfinite(value) for value in (y1, outer, ratio)):
        raise ValueError("所有输入必须是有限数值。")
    if y1 <= 0 or outer <= 0 or ratio < 1:
        raise ValueError("y+ 必须大于 0，增长率必须大于或等于 1。")
    if ratio == 1:
        continuous = outer / (2 * y1)
        layers = max(1, math.ceil(continuous - 1e-12))
        achieved = 2 * y1 * layers
    else:
        log_ratio = math.log(ratio)
        continuous = math.log1p((ratio - 1) * outer / (2 * y1)) / log_ratio
        layers = max(1, math.ceil(continuous - 1e-12))
        achieved = 2 * y1 * math.expm1(layers * log_ratio) / (ratio - 1)
    return {
        "status": "INITIAL_DESIGN_NOT_VALIDATED",
        "algorithm": "wall-unit-coverage-layer-count-v1",
        "recommended_layers": layers,
        "continuous_layers_before_rounding": round(continuous, 6),
        "nominal_outer_y_plus": round(achieved, 6),
        "target_outer_y_plus": outer,
        "first_cell_y_plus": y1,
        "growth_rate": ratio,
        "assumptions": [
            "首层近似正交，首层中心位于首层厚度中点。",
            "短距离内壁面摩擦速度近似不变，层厚按等比增长。",
            "这是层数初步估算；实际网格质量与 Wall Yplus 需要 Fluent 求解验证。",
        ],
    }


def uniform_reynolds_number(
    density_kg_m3: float,
    characteristic_velocity_m_s: float,
    hydraulic_diameter_mm: float,
    dynamic_viscosity_pa_s: float,
) -> float:
    values = tuple(
        float(value)
        for value in (
            density_kg_m3,
            characteristic_velocity_m_s,
            hydraulic_diameter_mm,
            dynamic_viscosity_pa_s,
        )
    )
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise ValueError("密度、速度、直径和动力黏度必须是大于 0 的有限数值。")
    rho, velocity, diameter_mm, viscosity = values
    return rho * velocity * (diameter_mm / 1000.0) / viscosity


def calculate_uniform_first_height(
    *,
    density_kg_m3: float,
    dynamic_viscosity_pa_s: float,
    characteristic_velocity_m_s: float,
    hydraulic_diameter_mm: float,
    target_first_cell_y_plus: float = 1.0,
    allow_out_of_range: bool = False,
) -> dict[str, Any]:
    """Estimate Uniform First Height using the source algorithm's default Cf model."""
    rho = float(density_kg_m3)
    viscosity = float(dynamic_viscosity_pa_s)
    velocity = float(characteristic_velocity_m_s)
    diameter = float(hydraulic_diameter_mm)
    y_plus = float(target_first_cell_y_plus)
    if not all(
        math.isfinite(value) and value > 0 for value in (rho, viscosity, velocity, diameter, y_plus)
    ):
        raise ValueError("Uniform 输入必须是大于 0 的有限数值。")

    reynolds = uniform_reynolds_number(rho, velocity, diameter, viscosity)
    if (reynolds < 4000 or reynolds > 100_000) and not allow_out_of_range:
        return {
            "status": "CONFIRMATION_REQUIRED",
            "reynolds_number": reynolds,
            "confirmation_required": True,
            "warnings": [
                "Reynolds 数超出本估算的常用范围。",
                "请确认摩擦关联式假设后再查看首层高度。",
            ],
        }

    coefficient = 0.079 * reynolds ** (-0.25)
    wall_shear = 0.5 * coefficient * rho * velocity**2
    friction_velocity = math.sqrt(wall_shear / rho)
    centroid_distance_m = y_plus * viscosity / (rho * friction_velocity)
    height_m = 2 * centroid_distance_m
    warnings = [
        "使用估算壁面摩擦速度；Venturi 沿程及支管处的壁面剪切会变化。",
        "首层全厚度按 2 × 首层中心距估算，要求近壁单元近似正交。",
        "求解后需要检查实际 Wall Yplus；此结果不是求解器验证值。",
    ]
    if reynolds > 100_000:
        warnings.append("Re 超过常用 Blasius 关联式范围，结果仅作初步工程估算。")
    return {
        "status": "INITIAL_ESTIMATE_NOT_SOLVER_VALIDATED",
        "algorithm": "ansys-internal-cf-first-height-v1",
        "model": {
            "friction_model": "ansys_internal_cf",
            "skin_friction_coefficient_cf": coefficient,
        },
        "input": {
            "density_kg_m3": rho,
            "dynamic_viscosity_pa_s": viscosity,
            "characteristic_velocity_m_s": velocity,
            "hydraulic_diameter_mm": diameter,
            "target_first_cell_y_plus": y_plus,
        },
        "reynolds_number": reynolds,
        "wall_shear_estimate_pa": wall_shear,
        "friction_velocity_m_s": friction_velocity,
        "first_cell_centroid_distance_m": centroid_distance_m,
        "first_cell_centroid_distance_mm": centroid_distance_m * 1000,
        "recommended_first_height_m": height_m,
        "recommended_first_height_mm": height_m * 1000,
        "fluent_mapping_status": "unverified",
        "warnings": warnings,
    }


def create_tools(
    *,
    allow_out_of_range: bool = False,
    allowed_knowledge_files: tuple[str, ...] = SOURCE_FILES,
    allowed_tool_names: tuple[str, ...] = (
        "calculate_smooth_layers",
        "calculate_uniform_first_height",
    ),
) -> list[Any]:
    """Return the two whitelisted V1 tools for an Agno Agent run."""

    def smooth_tool(
        first_cell_y_plus: float,
        target_outer_y_plus: float,
        growth_rate: float,
    ) -> str:
        """Calculate the Smooth Transition layer count from y+ targets and growth rate."""
        return _as_json(
            calculate_smooth_layers(
                first_cell_y_plus=first_cell_y_plus,
                target_outer_y_plus=target_outer_y_plus,
                growth_rate=growth_rate,
            )
        )

    def uniform_tool(
        density_kg_m3: float,
        dynamic_viscosity_pa_s: float,
        characteristic_velocity_m_s: float,
        hydraulic_diameter_mm: float,
        target_first_cell_y_plus: float = 1.0,
    ) -> str:
        """Estimate Uniform First Height from density, viscosity, speed, diameter and y+."""
        return _as_json(
            calculate_uniform_first_height(
                density_kg_m3=density_kg_m3,
                dynamic_viscosity_pa_s=dynamic_viscosity_pa_s,
                characteristic_velocity_m_s=characteristic_velocity_m_s,
                hydraulic_diameter_mm=hydraulic_diameter_mm,
                target_first_cell_y_plus=target_first_cell_y_plus,
                allow_out_of_range=allow_out_of_range,
            )
        )

    tools: list[Any] = []
    if allowed_knowledge_files:
        tools.append(create_scoped_boundary_layer_search(allowed_knowledge_files))
    web_search = WebSearchTools(
        enable_search=True,
        enable_news=False,
        backend="auto",
        fixed_max_results=5,
        timeout=15,
    )
    tools.append(web_search)
    if "calculate_smooth_layers" in allowed_tool_names:
        smooth_tool.__name__ = "calculate_smooth_layers"
        smooth_tool.__qualname__ = "calculate_smooth_layers"
        tools.append(smooth_tool)
    if "calculate_uniform_first_height" in allowed_tool_names:
        uniform_tool.__name__ = "calculate_uniform_first_height"
        uniform_tool.__qualname__ = "calculate_uniform_first_height"
        tools.append(uniform_tool)
    return tools
