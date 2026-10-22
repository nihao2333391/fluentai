from typing import Any

from app.domain import FluentConnectionConfig, PresetDocument, PresetItem
from app.fluent.catalog import FluentSettingCatalog, SettingDefinition
from app.fluent.pyfluent_adapter import PyFluentAdapter


class FakeSession:
    def __init__(self) -> None:
        self.is_active_value = True
        self.one = 1.0
        self.two = 2.0

    def is_active(self) -> bool:
        return self.is_active_value


def _definition(
    setting_id: str, attribute: str, *, fail_value: float | None = None
) -> SettingDefinition:
    def getter(session: Any) -> float:
        return float(getattr(session, attribute))

    def setter(session: Any, value: Any) -> None:
        if fail_value is not None and float(value) == fail_value:
            raise RuntimeError("Injected write failure")
        setattr(session, attribute, float(value))

    return SettingDefinition(
        setting_id=setting_id,
        display_name=setting_id,
        group="general",
        value_type="float",
        getter=getter,
        setter=setter,
        minimum=0.0,
    )


def test_pyfluent_adapter_writes_and_verifies() -> None:
    session = FakeSession()
    catalog = FluentSettingCatalog(
        [_definition("test.one", "one"), _definition("test.two", "two")],
        version="test",
    )
    adapter = PyFluentAdapter(catalog=catalog, session=session, connection_mode="launch")

    report = adapter.write_settings(
        [
            PresetItem(setting_id="test.one", type="float", value=3.0),
            PresetItem(setting_id="test.two", type="float", value=4.0),
        ]
    )

    assert report.status == "success"
    assert session.one == 3.0
    assert session.two == 4.0
    assert all(result.success for result in report.results)
    assert report.rollback_attempted is False


def test_pyfluent_adapter_rolls_back_partial_failure() -> None:
    session = FakeSession()
    catalog = FluentSettingCatalog(
        [
            _definition("test.one", "one"),
            _definition("test.two", "two", fail_value=9.0),
        ],
        version="test",
    )
    adapter = PyFluentAdapter(catalog=catalog, session=session, connection_mode="launch")

    report = adapter.apply_preset(
        PresetDocument(
            items=[
                PresetItem(setting_id="test.one", type="float", value=5.0),
                PresetItem(setting_id="test.two", type="float", value=9.0),
            ]
        )
    )

    assert report.status == "failed"
    assert report.operation == "apply"
    assert report.rollback_attempted is True
    assert report.rollback_succeeded is True
    assert session.one == 1.0
    assert session.two == 2.0
    assert report.rollback_results


def test_pyfluent_adapter_validation_prevents_writes() -> None:
    session = FakeSession()
    catalog = FluentSettingCatalog([_definition("test.one", "one")], version="test")
    adapter = PyFluentAdapter(catalog=catalog, session=session, connection_mode="launch")

    report = adapter.write_settings([PresetItem(setting_id="test.one", type="float", value=-1.0)])

    assert report.status == "failed"
    assert report.rollback_attempted is False
    assert session.one == 1.0


def test_pyfluent_adapter_status_tracks_fake_session() -> None:
    session = FakeSession()
    adapter = PyFluentAdapter(session=session, connection_mode="attach")

    assert adapter.status().connected is True
    session.is_active_value = False
    assert adapter.status().connected is False


def test_pyfluent_adapter_requires_connection() -> None:
    adapter = PyFluentAdapter()
    try:
        adapter.read_settings(["solver.time"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("Adapter read succeeded without a Fluent session")


def test_connection_config_validation() -> None:
    config = FluentConnectionConfig(mode="launch", processor_count=2)
    assert config.product_version == "25.2.0"
    assert config.processor_count == 2
