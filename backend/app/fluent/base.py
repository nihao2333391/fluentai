"""Stable adapter contract used by future Fluent integration services."""

from dataclasses import dataclass
from typing import Protocol

from app.domain import PresetDocument, PresetItem, PresetValue


@dataclass(frozen=True)
class FluentSessionInfo:
    connected: bool
    mode: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class SettingWriteResult:
    setting_id: str
    expected: PresetValue
    actual: PresetValue
    success: bool
    message: str = ""


class FluentAdapter(Protocol):
    def connect(self, config: dict[str, object]) -> FluentSessionInfo: ...

    def disconnect(self) -> None: ...

    def status(self) -> FluentSessionInfo: ...

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]: ...

    def write_settings(self, items: list[PresetItem]) -> list[SettingWriteResult]: ...

    def apply_preset(self, preset: PresetDocument) -> list[SettingWriteResult]: ...
