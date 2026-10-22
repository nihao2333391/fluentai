"""FastAPI entry point for the Fluent AI sidecar."""

from datetime import UTC, datetime

from fastapi import FastAPI

from app import __version__

app = FastAPI(
    title="Fluent AI Sidecar",
    description="Local service for Fluent integration and application persistence.",
    version=__version__,
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return sidecar liveness information."""
    return {
        "status": "ok",
        "service": "fluent-ai-sidecar",
        "version": __version__,
        "timestamp": datetime.now(UTC).isoformat(),
    }
