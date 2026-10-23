"""Authenticated API router aggregation."""

from fastapi import APIRouter, Depends

from app.api import (
    automations,
    fluent,
    jobs,
    meshing_automations,
    models,
    session,
    settings,
    sync_logs,
    system,
)
from app.auth import require_bearer_token

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_bearer_token)])
api_router.include_router(automations.router, prefix="/automations")
api_router.include_router(fluent.router, prefix="/fluent")
api_router.include_router(meshing_automations.router)
api_router.include_router(models.router, prefix="/models")
api_router.include_router(settings.router, prefix="/settings")
api_router.include_router(jobs.router, prefix="/jobs")
api_router.include_router(sync_logs.router, prefix="/sync-logs")
api_router.include_router(session.router, prefix="/session")
api_router.include_router(system.router, prefix="/system")
