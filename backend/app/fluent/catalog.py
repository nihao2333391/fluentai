"""Versioned Fluent setting catalog and value validation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal, cast

from app.domain import PresetValue

SettingValueType = Literal["int", "float", "bool", "string", "enum"]
SettingGetter = Callable[[Any], PresetValue]
SettingSetter = Callable[[Any, PresetValue], None]


@dataclass(frozen=True)
class SettingDefinition:
    """One validated Fluent setting exposed to the application."""

    setting_id: str
    display_name: str
    value_type: SettingValueType
    getter: SettingGetter
    setter: SettingSetter
    allowed_values: tuple[PresetValue, ...] | None = None
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def validate(self, value: PresetValue) -> PresetValue:
        if value is None:
            raise ValueError(f"Setting {self.setting_id!r} does not accept null.")

        if self.value_type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Setting {self.setting_id!r} requires an integer.")
            normalized: PresetValue = value
        elif self.value_type == "float":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Setting {self.setting_id!r} requires a number.")
            normalized = float(value)
        elif self.value_type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"Setting {self.setting_id!r} requires a boolean.")
            normalized = value
        else:
            if not isinstance(value, str):
                raise ValueError(f"Setting {self.setting_id!r} requires a string.")
            normalized = value

        if self.allowed_values is not None and normalized not in self.allowed_values:
            allowed = ", ".join(repr(item) for item in self.allowed_values)
            raise ValueError(f"Setting {self.setting_id!r} must be one of: {allowed}.")

        if (
            self.minimum is not None
            and isinstance(normalized, (int, float))
            and float(normalized) < self.minimum
        ):
            raise ValueError(f"Setting {self.setting_id!r} must be at least {self.minimum}.")
        if (
            self.maximum is not None
            and isinstance(normalized, (int, float))
            and float(normalized) > self.maximum
        ):
            raise ValueError(f"Setting {self.setting_id!r} must be at most {self.maximum}.")
        return normalized

    def read(self, session: Any) -> PresetValue:
        return self.getter(session)

    def write(self, session: Any, value: PresetValue) -> PresetValue:
        normalized = self.validate(value)
        self.setter(session, normalized)
        return normalized


class FluentSettingCatalog:
    """Immutable mapping of stable setting IDs to version-specific operations."""

    def __init__(self, definitions: Iterable[SettingDefinition], version: str) -> None:
        self.version = version
        self._definitions = tuple(definitions)
        ids = [definition.setting_id for definition in self._definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("Setting catalog contains duplicate setting IDs.")
        self._by_id = {definition.setting_id: definition for definition in self._definitions}

    def list(self) -> tuple[SettingDefinition, ...]:
        return self._definitions

    def get(self, setting_id: str) -> SettingDefinition:
        try:
            return self._by_id[setting_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Fluent setting: {setting_id}") from exc

    def read(self, session: Any, setting_ids: Iterable[str]) -> dict[str, PresetValue]:
        return {setting_id: self.get(setting_id).read(session) for setting_id in setting_ids}


def _residual(setting_id: str, equation: str) -> SettingDefinition:
    def getter(session: Any) -> PresetValue:
        return float(
            session.settings.solution.monitor.residual.equations[
                equation
            ].absolute_criteria.get_state()
        )

    def setter(session: Any, value: PresetValue) -> None:
        session.settings.solution.monitor.residual.equations[equation].absolute_criteria = value

    return SettingDefinition(
        setting_id=setting_id,
        display_name=f"Residual criterion: {equation}",
        value_type="float",
        getter=getter,
        setter=setter,
        minimum=1e-12,
        maximum=1.0,
        description=f"Absolute convergence criterion for the {equation} equation.",
    )


def create_fluent_252_catalog() -> FluentSettingCatalog:
    """Return the validated Fluent 2025 R2 setting catalog."""

    def solver_time_getter(session: Any) -> PresetValue:
        return cast(PresetValue, session.settings.setup.general.solver.time.get_state())

    def solver_time_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.general.solver.time = value

    def solver_type_getter(session: Any) -> PresetValue:
        return cast(PresetValue, session.settings.setup.general.solver.type.get_state())

    def solver_type_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.general.solver.type = value

    def velocity_getter(session: Any) -> PresetValue:
        return cast(
            PresetValue, session.settings.setup.general.solver.velocity_formulation.get_state()
        )

    def velocity_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.general.solver.velocity_formulation = value

    def energy_getter(session: Any) -> PresetValue:
        return cast(PresetValue, session.settings.setup.models.energy.enabled.get_state())

    def energy_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.energy.enabled = value

    def viscous_model_getter(session: Any) -> PresetValue:
        return cast(PresetValue, session.settings.setup.models.viscous.model.get_state())

    def viscous_model_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.viscous.model = value

    def k_omega_model_getter(session: Any) -> PresetValue:
        return cast(PresetValue, session.settings.setup.models.viscous.k_omega_model.get_state())

    def k_omega_model_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.viscous.k_omega_model = value

    def low_re_getter(session: Any) -> PresetValue:
        return cast(
            PresetValue,
            session.settings.setup.models.viscous.k_omega.k_omega_low_re_correction.get_state(),
        )

    def low_re_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.viscous.k_omega.k_omega_low_re_correction = value

    def curvature_getter(session: Any) -> PresetValue:
        return cast(
            PresetValue,
            session.settings.setup.models.viscous.options.curvature_correction.enabled.get_state(),
        )

    def curvature_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.viscous.options.curvature_correction.enabled = value

    def corner_getter(session: Any) -> PresetValue:
        return cast(
            PresetValue,
            session.settings.setup.models.viscous.options.corner_flow_correction.enabled.get_state(),
        )

    def corner_setter(session: Any, value: PresetValue) -> None:
        session.settings.setup.models.viscous.options.corner_flow_correction.enabled = value

    def reference_getter(name: str) -> SettingGetter:
        return lambda session: cast(
            PresetValue,
            getattr(session.settings.setup.reference_values, name).get_state(),
        )

    def reference_setter(name: str) -> SettingSetter:
        return lambda session, value: setattr(session.settings.setup.reference_values, name, value)

    definitions = [
        SettingDefinition(
            setting_id="solver.time",
            display_name="Solver time",
            value_type="enum",
            getter=solver_time_getter,
            setter=solver_time_setter,
            description="Steady or transient solver mode.",
        ),
        SettingDefinition(
            setting_id="solver.type",
            display_name="Solver type",
            value_type="enum",
            getter=solver_type_getter,
            setter=solver_type_setter,
            allowed_values=("pressure-based", "density-based"),
        ),
        SettingDefinition(
            setting_id="solver.velocity_formulation",
            display_name="Velocity formulation",
            value_type="enum",
            getter=velocity_getter,
            setter=velocity_setter,
            allowed_values=("absolute", "relative"),
        ),
        SettingDefinition(
            setting_id="energy.enabled",
            display_name="Energy equation",
            value_type="bool",
            getter=energy_getter,
            setter=energy_setter,
        ),
        SettingDefinition(
            setting_id="viscous.model",
            display_name="Viscous model",
            value_type="enum",
            getter=viscous_model_getter,
            setter=viscous_model_setter,
        ),
        SettingDefinition(
            setting_id="viscous.k_omega_model",
            display_name="K-omega model",
            value_type="enum",
            getter=k_omega_model_getter,
            setter=k_omega_model_setter,
        ),
        SettingDefinition(
            setting_id="viscous.low_re_correction",
            display_name="K-omega low-Re correction",
            value_type="bool",
            getter=low_re_getter,
            setter=low_re_setter,
        ),
        SettingDefinition(
            setting_id="viscous.curvature_correction",
            display_name="Curvature correction",
            value_type="bool",
            getter=curvature_getter,
            setter=curvature_setter,
        ),
        SettingDefinition(
            setting_id="viscous.corner_flow_correction",
            display_name="Corner flow correction",
            value_type="bool",
            getter=corner_getter,
            setter=corner_setter,
        ),
        _residual("residual.continuity", "continuity"),
        _residual("residual.x-velocity", "x-velocity"),
        _residual("residual.y-velocity", "y-velocity"),
        _residual("residual.z-velocity", "z-velocity"),
        _residual("residual.k", "k"),
        _residual("residual.omega", "omega"),
        SettingDefinition(
            setting_id="reference.area",
            display_name="Reference area",
            value_type="float",
            getter=reference_getter("area"),
            setter=reference_setter("area"),
            minimum=1e-15,
        ),
        SettingDefinition(
            setting_id="reference.density",
            display_name="Reference density",
            value_type="float",
            getter=reference_getter("density"),
            setter=reference_setter("density"),
            minimum=1e-15,
        ),
        SettingDefinition(
            setting_id="reference.length",
            display_name="Reference length",
            value_type="float",
            getter=reference_getter("length"),
            setter=reference_setter("length"),
            minimum=1e-15,
        ),
        SettingDefinition(
            setting_id="reference.velocity",
            display_name="Reference velocity",
            value_type="float",
            getter=reference_getter("velocity"),
            setter=reference_setter("velocity"),
            minimum=0.0,
        ),
        SettingDefinition(
            setting_id="reference.viscosity",
            display_name="Reference viscosity",
            value_type="float",
            getter=reference_getter("viscosity"),
            setter=reference_setter("viscosity"),
            minimum=1e-15,
        ),
    ]
    return FluentSettingCatalog(definitions, version="25.2.0")


FLUENT_252_CATALOG = create_fluent_252_catalog()
