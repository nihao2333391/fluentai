"""Application settings endpoints."""

import re

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DatabaseDependency
from app.domain import SettingsRead, SettingsUpdate
from app.repositories.settings import SettingsRepository

router = APIRouter(tags=["settings"])
SETTING_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@router.get("", response_model=SettingsRead)
def get_settings(database: DatabaseDependency) -> SettingsRead:
    return SettingsRead(values=SettingsRepository(database).get_all())


@router.put("", response_model=SettingsRead)
def update_settings(payload: SettingsUpdate, database: DatabaseDependency) -> SettingsRead:
    invalid = [key for key in payload.values if not SETTING_KEY_PATTERN.fullmatch(key)]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid setting keys: {', '.join(sorted(invalid))}",
        )
    return SettingsRead(values=SettingsRepository(database).update(payload.values))
