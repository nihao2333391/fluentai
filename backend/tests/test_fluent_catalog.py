from app.fluent.catalog import FLUENT_252_CATALOG, SettingDefinition


def test_catalog_contains_twenty_seven_unique_validated_settings() -> None:
    definitions = FLUENT_252_CATALOG.list()
    setting_ids = [definition.setting_id for definition in definitions]

    assert len(definitions) == 27
    assert len(setting_ids) == 27
    assert FLUENT_252_CATALOG.version == "25.2.0"
    assert FLUENT_252_CATALOG.get("residual.continuity").value_type == "float"
    assert {definition.group for definition in definitions} == {
        "general",
        "models",
        "solution",
        "reference",
    }
    assert "density-based-implicit" in (FLUENT_252_CATALOG.get("solver.type").allowed_values or ())
    assert "unsteady-2nd-order" in (FLUENT_252_CATALOG.get("solver.time").allowed_values or ())
    assert "Coupled" in (FLUENT_252_CATALOG.get("methods.flow_scheme").allowed_values or ())
    assert FLUENT_252_CATALOG.get("initialization.type").value_type == "enum"
    assert FLUENT_252_CATALOG.get("run_calculation.iterations").value_type == "int"


def test_catalog_rejects_invalid_values() -> None:
    residual = FLUENT_252_CATALOG.get("residual.continuity")
    assert residual.validate(0.001) == 0.001

    try:
        residual.validate(0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("Residual criterion accepted an invalid zero value")

    energy = FLUENT_252_CATALOG.get("energy.enabled")
    try:
        energy.validate(1)
    except ValueError:
        pass
    else:
        raise AssertionError("Boolean setting accepted an integer")

    solver_type = FLUENT_252_CATALOG.get("solver.type")
    try:
        solver_type.validate("invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("Enum setting accepted an unknown value")


def test_catalog_rejects_duplicate_ids() -> None:
    definition = SettingDefinition(
        setting_id="test.value",
        display_name="Test",
        group="general",
        value_type="float",
        getter=lambda session: session.value,
        setter=lambda session, value: setattr(session, "value", value),
    )

    from app.fluent.catalog import FluentSettingCatalog

    try:
        FluentSettingCatalog([definition, definition], version="test")
    except ValueError:
        pass
    else:
        raise AssertionError("Catalog accepted duplicate setting IDs")
