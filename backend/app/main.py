"""FastAPI application factory for the Fluent AI sidecar."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app import __version__
from app.api.router import api_router
from app.auth import require_bearer_token
from app.database import Database
from app.fluent.base import FluentAdapter
from app.fluent.pyfluent_adapter import PyFluentAdapter
from app.repositories.errors import RepositoryConflictError, RepositoryNotFoundError
from app.schemas import HealthResponse, ReadyResponse, ShutdownResponse
from app.services.fluent_service import FluentService

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_database_path(database_path: Path | str | None = None) -> Path:
    """Resolve the sidecar database path from an explicit value or environment."""
    if database_path is not None:
        return Path(database_path)
    data_directory = os.environ.get("FLUENT_AI_DATA_DIR")
    if data_directory:
        return Path(data_directory) / "fluent-ai.db"
    return PROJECT_ROOT / ".runtime" / "data" / "fluent-ai.db"


def create_app(
    auth_token: str | None = None,
    database_path: Path | str | None = None,
    fluent_adapter: FluentAdapter | None = None,
) -> FastAPI:
    """Create a sidecar application with authentication and persistence."""
    app = FastAPI(
        title="Fluent AI Sidecar",
        description="Local service for Fluent integration and application persistence.",
        version=__version__,
    )
    database = Database(resolve_database_path(database_path))
    database.initialize()
    app.state.auth_token = auth_token
    app.state.request_shutdown = None
    app.state.database = database
    app.state.fluent_service = FluentService(database, fluent_adapter or PyFluentAdapter())

    @app.exception_handler(RepositoryNotFoundError)
    def handle_not_found(_request: Request, exc: RepositoryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(RepositoryConflictError)
    def handle_conflict(_request: Request, exc: RepositoryConflictError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    def handle_file_not_found(_request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    app.include_router(api_router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Return unauthenticated liveness information."""
        return HealthResponse(
            version=__version__,
            timestamp=datetime.now(UTC).isoformat(),
        )

    @app.get(
        "/api/system/ready",
        response_model=ReadyResponse,
        tags=["system"],
        dependencies=[Depends(require_bearer_token)],
    )
    def ready() -> ReadyResponse:
        """Return authenticated readiness information."""
        return ReadyResponse(
            version=__version__,
            pid=os.getpid(),
            database="ready",
            timestamp=datetime.now(UTC).isoformat(),
        )

    @app.post(
        "/api/system/shutdown",
        response_model=ShutdownResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["system"],
        dependencies=[Depends(require_bearer_token)],
    )
    def shutdown(request: Request) -> ShutdownResponse:
        """Request a graceful sidecar shutdown."""
        callback: object = getattr(request.app.state, "request_shutdown", None)
        if not callable(callback):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shutdown callback is not configured.",
            )
        shutdown_callback: Callable[[], None] = callback
        shutdown_callback()
        return ShutdownResponse()

    return app


app = create_app(os.environ.get("FLUENT_AI_SIDECAR_TOKEN"))
