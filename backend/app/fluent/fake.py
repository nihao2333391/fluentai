"""In-memory Fluent adapter for domain tests and UI development."""

from app.domain import PresetDocument, PresetItem, PresetValue
from app.fluent.base import FluentSessionInfo, SettingWriteResult


class FakeFluentAdapter:
    def __init__(self, initial_settings: dict[str, PresetValue] | None = None) -> None:
        self.settings = dict(initial_settings or {})
        self.session = FluentSessionInfo(connected=False)
        self.append_only_calls: list[list[PresetItem]] = []

    def connect(self, config: dict[str, object]) -> FluentSessionInfo:
        self.session = FluentSessionInfo(
            connected=True,
            mode=str(config.get("mode", "launch")),
            version="25.2.0-fake",
        )
        return self.session

    def disconnect(self) -> None:
        self.session = FluentSessionInfo(connected=False)

    def status(self) -> FluentSessionInfo:
        return self.session

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]:
        return {setting_id: self.settings[setting_id] for setting_id in setting_ids}

    def write_settings(self, items: list[PresetItem]) -> list[SettingWriteResult]:
        self.append_only_calls.append(items)
        results: list[SettingWriteResult] = []
        for item in items:
            if item.setting_id not in self.settings:
                results.append(
                    SettingWriteResult(
                        setting_id=item.setting_id,
                        expected=item.value,
                        actual=None,
                        success=False,
                        message="Setting does not exist in the fake Fluent session.",
                    )
                )
                continue
            self.settings[item.setting_id] = item.value
            results.append(
                SettingWriteResult(
                    setting_id=item.setting_id,
                    expected=item.value,
                    actual=self.settings[item.setting_id],
                    success=True,
                )
            )
        return results

    def apply_preset(self, preset: PresetDocument) -> list[SettingWriteResult]:
        return self.write_settings(preset.items)
