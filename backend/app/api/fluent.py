"""Authenticated Fluent connection, settings, and preset endpoints."""

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status

from app.api.deps import FluentServiceDependency
from app.domain import (
    FluentConnectionConfig,
    FluentOperationReport,
    FluentStatus,
    PresetDocument,
    PresetValidationReport,
    PresetValue,
    SettingCatalogEntry,
    SettingReadRequest,
    SettingWriteRequest,
)

router = APIRouter(tags=["fluent"])


def _translate_errors[T](operation: Callable[[], T]) -> T:
    try:
        return operation()
    except (RuntimeError, ValueError, FileNotFoundError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.get("/status", response_model=FluentStatus)
def fluent_status(fluent: FluentServiceDependency) -> FluentStatus:
    return _translate_errors(fluent.status)


@router.post("/connect", response_model=FluentStatus)
def connect_fluent(
    payload: FluentConnectionConfig,
    fluent: FluentServiceDependency,
) -> FluentStatus:
    return _translate_errors(lambda: fluent.connect(payload))


@router.post("/disconnect", response_model=FluentStatus)
def disconnect_fluent(fluent: FluentServiceDependency) -> FluentStatus:
    return _translate_errors(fluent.disconnect)


@router.get("/catalog", response_model=list[SettingCatalogEntry])
def get_catalog(fluent: FluentServiceDependency) -> list[SettingCatalogEntry]:
    return fluent.catalog()


@router.post("/settings/read", response_model=dict[str, PresetValue])
def read_settings(
    payload: SettingReadRequest,
    fluent: FluentServiceDependency,
) -> dict[str, PresetValue]:
    return _translate_errors(lambda: fluent.read_settings(payload.setting_ids))


@router.post("/settings/write", response_model=FluentOperationReport)
def write_settings(
    payload: SettingWriteRequest,
    fluent: FluentServiceDependency,
) -> FluentOperationReport:
    return _translate_errors(lambda: fluent.write_settings(payload.items))


@router.post("/presets/validate", response_model=PresetValidationReport)
def validate_preset(
    payload: PresetDocument,
    fluent: FluentServiceDependency,
) -> PresetValidationReport:
    return fluent.validate_preset(payload)


@router.post("/presets/apply", response_model=FluentOperationReport)
def apply_preset(
    payload: PresetDocument,
    fluent: FluentServiceDependency,
) -> FluentOperationReport:
    return _translate_errors(lambda: fluent.apply_preset(payload))
