"""Synchronization log endpoints."""

from typing import Literal

from fastapi import APIRouter, status

from app.api.deps import DatabaseDependency
from app.domain import SyncLogCreate, SyncLogRead
from app.repositories.sync_logs import SyncLogRepository

router = APIRouter(tags=["sync-logs"])


@router.get("", response_model=list[SyncLogRead])
def list_sync_logs(
    database: DatabaseDependency,
    limit: int = 100,
    direction: Literal["read", "write", "sync", "apply", "pull"] | None = None,
    status_filter: Literal["success", "failed"] | None = None,
    automation_id: int | None = None,
    meshing_automation_id: int | None = None,
    model_id: int | None = None,
    search: str | None = None,
) -> list[SyncLogRead]:
    return SyncLogRepository(database).list(
        limit=max(1, min(limit, 500)),
        direction=direction,
        status=status_filter,
        automation_id=automation_id,
        meshing_automation_id=meshing_automation_id,
        model_id=model_id,
        search=search.strip() if search else None,
    )


@router.post("", response_model=SyncLogRead, status_code=status.HTTP_201_CREATED)
def create_sync_log(payload: SyncLogCreate, database: DatabaseDependency) -> SyncLogRead:
    return SyncLogRepository(database).create(payload)
