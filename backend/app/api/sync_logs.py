"""Synchronization log endpoints."""

from fastapi import APIRouter, status

from app.api.deps import DatabaseDependency
from app.domain import SyncLogCreate, SyncLogRead
from app.repositories.sync_logs import SyncLogRepository

router = APIRouter(tags=["sync-logs"])


@router.get("", response_model=list[SyncLogRead])
def list_sync_logs(database: DatabaseDependency, limit: int = 100) -> list[SyncLogRead]:
    return SyncLogRepository(database).list(limit=max(1, min(limit, 500)))


@router.post("", response_model=SyncLogRead, status_code=status.HTTP_201_CREATED)
def create_sync_log(payload: SyncLogCreate, database: DatabaseDependency) -> SyncLogRead:
    return SyncLogRepository(database).create(payload)
