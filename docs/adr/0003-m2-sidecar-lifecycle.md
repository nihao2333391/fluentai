# ADR 0003: Sidecar lifecycle and local authentication

- Status: accepted
- Date: 2026-10-22

## Context

The renderer must use the FastAPI sidecar without receiving the bearer token or gaining arbitrary IPC access. The sidecar must also stop when the application exits and recover from unexpected process failure.

## Decision

### Startup and handshake

- Electron spawns `python -m app.sidecar`.
- The sidecar binds to `127.0.0.1` with port `0`, letting the OS choose a free port.
- Python prints one JSON line to stdout:
  `{"event":"sidecar_ready","port":...,"pid":...,"version":...}`.
- Electron reads the line, then calls the authenticated readiness endpoint.

### Authentication

- Electron generates 32 random bytes per launch.
- The token is passed to the child through `FLUENT_AI_SIDECAR_TOKEN`.
- `/health` is public liveness information.
- `/api/system/ready` and `/api/system/shutdown` require `Authorization: Bearer <token>`.
- The token is never sent to the renderer or included in status events.

### IPC surface

The preload bridge exposes only:

- `sidecar.getStatus()`
- `sidecar.restart()`
- `sidecar.onStatusChanged(listener)`

No generic IPC channel, child process, filesystem, or shell access is exposed.

### Lifecycle

- Normal quit calls authenticated shutdown and waits for the process to exit.
- If graceful shutdown fails, Electron terminates only its own child process.
- Unexpected exits are detected and retried up to two times with backoff.
- A parent-pipe watchdog makes the sidecar exit if the Electron main process disappears.
- Sidecar status is broadcast to the renderer through a fixed IPC event.

## Consequences

- The renderer cannot directly call the local HTTP API.
- The random port does not need to be known by the renderer.
- Local authentication material remains outside renderer bundles.
- The sidecar remains independently testable through Python process integration tests.
- Packaged sidecar executable resolution remains a later packaging task.
