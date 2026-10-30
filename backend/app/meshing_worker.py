"""Executable entry point for a per-task Fluent Meshing worker subprocess.

The Electron sidecar spawns one worker per live Meshing task::

    python -m app.meshing_worker

Environment:

- ``FLUENT_AI_WORKER_RUN_DIR``      task run directory; the worker chdirs into
  its ``fluent-work`` subfolder before connecting so every Fluent instance has
  its own working directory.
- ``FLUENT_AI_WORKER_ADAPTER``      import path ``module:Class`` for the
  adapter to host (default ``app.meshing.pyfluent_adapter:PyFluentMeshingAdapter``).
- ``FLUENT_AI_WORKER_PRELOAD_PYFLUENT``  set to ``1`` to import PyFluent on the
  worker main thread before serving requests, mirroring the sidecar practice.

The parent drives the worker through newline-delimited JSON on stdio
(see :mod:`app.meshing.worker_protocol`). The worker exits when its stdin
closes or the parent disposes it.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path
from typing import Any

DEFAULT_ADAPTER_TARGET = "app.meshing.pyfluent_adapter:PyFluentMeshingAdapter"


def _load_adapter(target: str) -> Any:
    module_name, _, attribute = target.partition(":")
    if not attribute:
        raise ValueError(f"Adapter target must look like 'module:Class', got {target!r}")
    module = importlib.import_module(module_name)
    adapter_class = getattr(module, attribute)
    if os.environ.get("FLUENT_AI_WORKER_PRELOAD_PYFLUENT") == "1":
        import ansys.fluent.core as pyfluent  # type: ignore[import-untyped]

        try:
            return adapter_class(pyfluent_module=pyfluent)
        except TypeError:
            return adapter_class()
    return adapter_class()


def _prepare_workdir() -> Path | None:
    run_dir_text = os.environ.get("FLUENT_AI_WORKER_RUN_DIR", "").strip()
    if not run_dir_text:
        return None
    run_dir = Path(run_dir_text)
    work_dir = run_dir / "fluent-work"
    work_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(work_dir)
    return run_dir


def main() -> int:
    try:
        _prepare_workdir()
        target = os.environ.get("FLUENT_AI_WORKER_ADAPTER") or DEFAULT_ADAPTER_TARGET
        adapter = _load_adapter(target)
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        return 2
    from app.meshing.worker_host import run_worker

    return run_worker(adapter)


if __name__ == "__main__":
    sys.exit(main())
