"""In-memory Fluent adapter for domain tests and UI development."""

from typing import Literal

from app.domain import (
    FluentConnectionConfig,
    FluentOperationReport,
    FluentStatus,
    PresetDocument,
    PresetItem,
    PresetValue,
    SettingWriteResult,
)
from app.fluent.comparison import preset_values_equal


class FakeFluentAdapter:
    def __init__(
        self,
        initial_settings: dict[str, PresetValue] | None = None,
        *,
        version: str = "25.2.0-fake",
    ) -> None:
        self.settings = dict(initial_settings or {})
        self.version = version
        self.mode: Literal["launch", "attach"] | None = None
        self.connected = False
        self.write_calls: list[list[PresetItem]] = []

    def connect(self, config: FluentConnectionConfig) -> FluentStatus:
        self.connected = True
        self.mode = config.mode
        return self.status()

    def disconnect(self) -> None:
        self.connected = False
        self.mode = None

    def status(self) -> FluentStatus:
        return FluentStatus(
            connected=self.connected,
            mode=self.mode,
            version=self.version if self.connected else None,
        )

    def load_case(self, file_path: str) -> None:
        if not self.connected:
            raise RuntimeError("Fake Fluent is not connected.")
        self.settings.setdefault("case.loaded", file_path)

    def save_case(self, file_path: str) -> None:
        if not self.connected:
            raise RuntimeError("Fake Fluent is not connected.")
        self.settings["case.saved"] = file_path

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]:
        return {setting_id: self.settings[setting_id] for setting_id in setting_ids}

    def write_settings(self, items: list[PresetItem]) -> FluentOperationReport:
        if not self.connected:
            raise RuntimeError("Fake Fluent is not connected.")
        self.write_calls.append(items)
        results: list[SettingWriteResult] = []
        old_values: dict[str, PresetValue] = {}
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
            old_values[item.setting_id] = self.settings[item.setting_id]
            self.settings[item.setting_id] = item.value
            actual = self.settings[item.setting_id]
            results.append(
                SettingWriteResult(
                    setting_id=item.setting_id,
                    expected=item.value,
                    actual=actual,
                    success=preset_values_equal(item.value, actual),
                )
            )

        failed = any(not result.success for result in results)
        rollback_results: list[SettingWriteResult] = []
        if failed and old_values:
            for setting_id, old_value in old_values.items():
                self.settings[setting_id] = old_value
                rollback_results.append(
                    SettingWriteResult(
                        setting_id=setting_id,
                        expected=old_value,
                        actual=old_value,
                        success=True,
                        message="Rolled back.",
                    )
                )
        return FluentOperationReport(
            operation="write",
            status="failed" if failed else "success",
            results=results,
            rollback_attempted=failed and bool(old_values),
            rollback_succeeded=(
                all(result.success for result in rollback_results) if failed else None
            ),
            rollback_results=rollback_results,
        )

    def apply_preset(self, preset: PresetDocument) -> FluentOperationReport:
        report = self.write_settings(preset.items)
        return report.model_copy(update={"operation": "apply"})
