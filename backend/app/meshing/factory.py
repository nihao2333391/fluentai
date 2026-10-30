"""Factories that create one Fluent Meshing adapter per live session.

Two strategies are available:

- :class:`SharedAdapterFactory` hands every session the same adapter instance
  (the legacy single-Fluent behaviour, capped at one concurrent session).
- :class:`SubprocessWorkerFactory` gives every session its own
  :class:`SubprocessMeshingAdapter`, so each task owns an isolated worker
  process and Fluent instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.meshing.base import MeshingWorkflowAdapter
from app.meshing.worker_client import (
    DEFAULT_ADAPTER_TARGET,
    SubprocessMeshingAdapter,
)


@runtime_checkable
class SessionAdapterFactory(Protocol):
    """Create and release the adapter bound to one live Meshing session."""

    @property
    def max_sessions(self) -> int:
        """Upper bound on concurrent sessions this factory can support."""

    @property
    def reusable(self) -> bool:
        """Whether session adapters may reuse one shared Fluent connection."""

    def create(self, *, session_id: str, run_dir: Path | None = None) -> MeshingWorkflowAdapter: ...

    def dispose(self, adapter: MeshingWorkflowAdapter) -> None:
        """Release any resources attached to a finished session adapter."""


class SharedAdapterFactory:
    """One shared adapter instance for every session (legacy mode)."""

    def __init__(self, adapter: MeshingWorkflowAdapter) -> None:
        self._adapter = adapter

    @property
    def max_sessions(self) -> int:
        return 1

    @property
    def reusable(self) -> bool:
        return True

    def create(self, *, session_id: str, run_dir: Path | None = None) -> MeshingWorkflowAdapter:
        return self._adapter

    def dispose(self, adapter: MeshingWorkflowAdapter) -> None:
        return None


class SubprocessWorkerFactory:
    """Spawn one worker subprocess per session for true parallel execution."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        adapter_target: str = DEFAULT_ADAPTER_TARGET,
        preload_pyfluent: bool = True,
        max_sessions: int = 3,
    ) -> None:
        self._python_executable = python_executable
        self._adapter_target = adapter_target
        self._preload_pyfluent = preload_pyfluent
        self._max_sessions = max(1, max_sessions)

    @property
    def max_sessions(self) -> int:
        return self._max_sessions

    @property
    def reusable(self) -> bool:
        return False

    def create(self, *, session_id: str, run_dir: Path | None = None) -> MeshingWorkflowAdapter:
        return SubprocessMeshingAdapter(
            run_dir=run_dir,
            python_executable=self._python_executable,
            adapter_target=self._adapter_target,
            preload_pyfluent=self._preload_pyfluent,
        )

    def dispose(self, adapter: MeshingWorkflowAdapter) -> None:
        dispose = getattr(adapter, "dispose", None)
        if callable(dispose):
            dispose()
