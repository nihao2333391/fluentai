"""Stable adapter contract used by Fluent integration services."""

from typing import Protocol

from app.domain import (
    FluentConnectionConfig,
    FluentOperationReport,
    FluentStatus,
    PresetDocument,
    PresetItem,
    PresetValue,
)


class FluentAdapter(Protocol):
    def connect(self, config: FluentConnectionConfig) -> FluentStatus: ...

    def disconnect(self) -> None: ...

    def status(self) -> FluentStatus: ...

    def load_case(self, file_path: str) -> None: ...

    def save_case(self, file_path: str) -> None: ...

    def read_settings(self, setting_ids: list[str]) -> dict[str, PresetValue]: ...

    def write_settings(self, items: list[PresetItem]) -> FluentOperationReport: ...

    def apply_preset(self, preset: PresetDocument) -> FluentOperationReport: ...
