"""Shared response schemas for the local sidecar API."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Unauthenticated liveness response."""

    status: Literal["ok"] = "ok"
    service: Literal["fluent-ai-sidecar"] = "fluent-ai-sidecar"
    version: str
    timestamp: str


class ReadyResponse(BaseModel):
    """Authenticated readiness response."""

    status: Literal["ready"] = "ready"
    service: Literal["fluent-ai-sidecar"] = "fluent-ai-sidecar"
    version: str
    pid: int
    timestamp: str


class ShutdownResponse(BaseModel):
    """Authenticated shutdown acknowledgement."""

    status: Literal["shutting-down"] = "shutting-down"
