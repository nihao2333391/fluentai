"""Executable entry point for the Fluent AI sidecar.

The Electron main process spawns this module, reads one JSON handshake line from
stdout, and then calls the authenticated readiness endpoint.
"""

import asyncio
import contextlib
import json
import os
import socket
import sys
import threading
from typing import cast

import uvicorn

from app import __version__
from app.main import create_app

STARTUP_TIMEOUT_SECONDS = 20.0


def _emit(event: str, **payload: object) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def _listening_port(server: uvicorn.Server) -> int:
    servers = getattr(server, "servers", None)
    if not servers:
        raise RuntimeError("Uvicorn did not expose a listening server.")
    sockets = getattr(servers[0], "sockets", None)
    if not sockets:
        raise RuntimeError("Uvicorn did not expose a listening socket.")
    sock = cast(socket.socket, sockets[0])
    address = sock.getsockname()
    return int(address[1])


def _watch_parent_pipe(server: uvicorn.Server) -> None:
    """Stop the sidecar when the Electron main-process stdin pipe closes."""
    if os.environ.get("FLUENT_AI_PARENT_PIPE") != "1":
        return

    def watch() -> None:
        with contextlib.suppress(Exception):
            os.read(sys.stdin.fileno(), 1)
        server.should_exit = True

    threading.Thread(target=watch, name="parent-pipe-watch", daemon=True).start()


async def serve() -> int:
    """Run Uvicorn on a random localhost port and announce readiness."""
    token = os.environ.get("FLUENT_AI_SIDECAR_TOKEN")
    if not token:
        _emit("sidecar_error", message="FLUENT_AI_SIDECAR_TOKEN is required")
        return 2

    app = create_app(token)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    def request_shutdown() -> None:
        server.should_exit = True

    app.state.request_shutdown = request_shutdown
    _watch_parent_pipe(server)
    server_task = asyncio.create_task(server.serve())

    deadline = asyncio.get_running_loop().time() + STARTUP_TIMEOUT_SECONDS
    while not server.started and not server_task.done():
        if asyncio.get_running_loop().time() >= deadline:
            server.should_exit = True
            server_task.cancel()
            _emit("sidecar_error", message="Sidecar startup timed out")
            return 3
        await asyncio.sleep(0.05)

    if not server.started:
        if server_task.done():
            server_task.result()
        _emit("sidecar_error", message="Sidecar server failed to start")
        return 4

    port = _listening_port(server)
    _emit(
        "sidecar_ready",
        port=port,
        pid=os.getpid(),
        version=__version__,
        host="127.0.0.1",
    )

    await server_task
    return 0


def main() -> int:
    try:
        return asyncio.run(serve())
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        _emit("sidecar_error", message=f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
