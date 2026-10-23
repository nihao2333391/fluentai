"""Database backup and restore endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DatabaseDependency
from app.domain import (
    DatabaseBackupInfo,
    DatabaseBackupList,
    RestoreDatabaseReport,
    RestoreDatabaseRequest,
)

router = APIRouter(tags=["system"])


@router.get("/backups", response_model=DatabaseBackupList)
def list_database_backups(database: DatabaseDependency) -> DatabaseBackupList:
    return DatabaseBackupList(
        backups=[DatabaseBackupInfo.model_validate(item) for item in database.list_backups()]
    )


@router.post("/backups", response_model=DatabaseBackupInfo, status_code=status.HTTP_201_CREATED)
def create_database_backup(database: DatabaseDependency) -> DatabaseBackupInfo:
    return DatabaseBackupInfo.model_validate(database.create_backup("manual"))


@router.post("/restore", response_model=RestoreDatabaseReport)
def restore_database_backup(
    payload: RestoreDatabaseRequest,
    database: DatabaseDependency,
) -> RestoreDatabaseReport:
    try:
        safety_backup, _restored = database.restore_backup(payload.backup_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return RestoreDatabaseReport(
        status="success",
        backup_name=payload.backup_name,
        safety_backup=DatabaseBackupInfo.model_validate(safety_backup),
        message="Database restored. A pre-restore safety backup was created.",
    )
