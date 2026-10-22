"""FastAPI dependencies for persistence."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.database import Database
from app.services.fluent_service import FluentService
from app.services.meshing_service import MeshingService


def get_database(request: Request) -> Database:
    database: object = getattr(request.app.state, "database", None)
    if not isinstance(database, Database):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )
    return database


DatabaseDependency = Annotated[Database, Depends(get_database)]


def get_fluent_service(request: Request) -> FluentService:
    service: object = getattr(request.app.state, "fluent_service", None)
    if not isinstance(service, FluentService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Fluent service is not configured.",
        )
    return service


FluentServiceDependency = Annotated[FluentService, Depends(get_fluent_service)]


def get_meshing_service(request: Request) -> MeshingService:
    service: object = getattr(request.app.state, "meshing_service", None)
    if not isinstance(service, MeshingService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meshing service is not configured.",
        )
    return service


MeshingServiceDependency = Annotated[MeshingService, Depends(get_meshing_service)]
