"""FastAPI application factory for the Fluent AI sidecar."""

import os
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request, status

from app import __version__
from app.auth import require_bearer_token
from app.schemas import HealthResponse, ReadyResponse, ShutdownResponse


def create_app(auth_token: str | None = None) -> FastAPI:
    """Create a sidecar application with an optional bearer token."""
    app = FastAPI(
        title="Fluent AI Sidecar",
        description="Local service for Fluent integration and application persistence.",
        version=__version__,
    )
    app.state.auth_token = auth_token
    app.state.request_shutdown = None

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
