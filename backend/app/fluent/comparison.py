"""Value comparison helpers for Fluent readback verification."""

import math

from app.domain import PresetValue


def preset_values_equal(expected: PresetValue, actual: PresetValue) -> bool:
    """Compare typed Fluent values with numeric tolerance."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-12)
    return expected == actual
