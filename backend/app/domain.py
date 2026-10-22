"""Pydantic domain contracts for persisted Fluent AI resources."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PresetValue = int | float | bool | str | None


class PresetItem(BaseModel):
    """One declarative Fluent setting in an automation preset."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    setting_id: str = Field(min_length=1, max_length=200)
    type: Literal["int", "float", "bool", "string", "enum"]
    value: PresetValue
    required: bool = True

    @model_validator(mode="after")
    def validate_value_type(self) -> PresetItem:
        expected: tuple[type[object], ...]
        if self.type == "int":
            expected = (int,)
        elif self.type == "float":
            expected = (int, float)
        elif self.type == "bool":
            expected = (bool,)
        else:
            expected = (str,)

        if self.type == "int" and isinstance(self.value, bool):
            raise ValueError("Boolean values are not valid for int settings.")
        if not isinstance(self.value, expected):
            raise ValueError(f"Value does not match preset type {self.type!r}.")
        return self


class PresetDocument(BaseModel):
    """Versioned automation preset payload."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    fluent_version: str | None = None
    items: list[PresetItem] = Field(default_factory=list)


class AutomationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    preset: PresetDocument = Field(default_factory=PresetDocument)
    status: Literal["draft", "active"] = "draft"


class AutomationUpdate(AutomationCreate):
    pass


class AutomationRead(AutomationCreate):
    id: int
    created_at: str
    updated_at: str


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    file_path: str = Field(min_length=1, max_length=2_000)
    description: str = Field(default="", max_length=2_000)
    tags: list[str] = Field(default_factory=list)


class ModelUpdate(ModelCreate):
    pass


class ModelRead(ModelCreate):
    id: int
    file_size: int
    file_mtime: str | None
    automation_ids: list[int] = Field(default_factory=list)
    default_automation_id: int | None = None
    created_at: str
    updated_at: str


class ModelAutomationAssociate(BaseModel):
    automation_id: int = Field(gt=0)
    is_default: bool = True


class SettingsRead(BaseModel):
    values: dict[str, str]


class SettingsUpdate(BaseModel):
    values: dict[str, str]


class JobCreate(BaseModel):
    job_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, object] = Field(default_factory=dict)


class JobRead(BaseModel):
    id: str
    job_type: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: int
    message: str
    payload: dict[str, object]
    result: dict[str, object] | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class SyncLogCreate(BaseModel):
    direction: Literal["read", "write", "sync", "apply", "pull"]
    target: str = Field(min_length=1, max_length=300)
    automation_id: int | None = None
    model_id: int | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    status: Literal["success", "failed"]
    message: str = Field(default="", max_length=4_000)


class SyncLogRead(SyncLogCreate):
    id: int
    created_at: str


FluentLaunchMode = Literal["launch", "attach"]
FluentUiMode = Literal["no_gui", "no_graphics", "hidden_gui", "gui"]


class FluentConnectionConfig(BaseModel):
    """Connection options for a real Fluent session."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mode: FluentLaunchMode = "launch"
    fluent_path: str | None = None
    product_version: str = "25.2.0"
    processor_count: int = Field(default=1, ge=1, le=128)
    ui_mode: FluentUiMode = "no_gui"
    start_timeout: int = Field(default=300, ge=10, le=1_800)
    cleanup_on_exit: bool = True
    host: str = "127.0.0.1"
    port: int | None = Field(default=None, ge=1, le=65_535)
    password: str | None = None
    server_info_file: str | None = None


class FluentStatus(BaseModel):
    """Current adapter session status."""

    connected: bool
    mode: FluentLaunchMode | None = None
    version: str | None = None
    pid: int | None = None
    host: str | None = None
    port: int | None = None


class SettingWriteResult(BaseModel):
    """Per-setting write and readback outcome."""

    setting_id: str
    expected: PresetValue
    actual: PresetValue
    success: bool
    message: str = ""


class FluentOperationReport(BaseModel):
    """Write or preset-apply report with rollback information."""

    operation: Literal["write", "apply"]
    status: Literal["success", "failed"]
    results: list[SettingWriteResult] = Field(default_factory=list)
    rollback_attempted: bool = False
    rollback_succeeded: bool | None = None
    rollback_results: list[SettingWriteResult] = Field(default_factory=list)
