# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC contracts and sidecar supervision: PASSED**
- **M3 - Database and domain model: NOT STARTED**

The desktop app now starts and supervises its local FastAPI sidecar automatically. Electron and the sidecar communicate through a random localhost port and a per-launch bearer token. The token remains in the Electron main process and is not exposed to the renderer.

## Architecture

```text
React renderer
    ↓ typed preload API
Electron main process
    ├─ sidecar supervisor
    ├─ random port + bearer token
    └─ narrow IPC handlers
          ↓ 127.0.0.1
FastAPI sidecar
    ├─ /health                  public liveness
    ├─ /api/system/ready        authenticated readiness
    └─ /api/system/shutdown     authenticated graceful stop
          ↓ future PyFluent gateway
ANSYS Fluent 2025 R2
```

## Technology Baseline

| Layer         | Version                  |
| ------------- | ------------------------ |
| Node.js       | 24.21.0                  |
| pnpm          | 12.5.1                   |
| Electron      | 45.0.0                   |
| electron-vite | 6.0.0                    |
| Vite          | 8.3.5                    |
| React         | 19.3.1                   |
| TypeScript    | 5.9.3                    |
| Python        | 3.12.14                  |
| FastAPI       | 0.159.1                  |
| PyFluent      | ansys-fluent-core 0.42.1 |

## M2 Sidecar Behavior

- Electron spawns `.venv\Scripts\python.exe -m app.sidecar`.
- The sidecar binds to `127.0.0.1` on an operating-system assigned random port.
- Python emits a one-line JSON readiness handshake on stdout.
- Electron verifies `/api/system/ready` with the generated bearer token.
- The renderer receives only status, version, PID, and port through preload IPC.
- Manual restart is available from the renderer.
- Unexpected sidecar exit is detected and retried up to two times with backoff.
- Normal app exit requests authenticated shutdown and confirms process termination.
- If Electron exits abnormally, closing the parent stdin pipe stops the sidecar.
- Renderer production output is checked for accidental token or Authorization-string leakage.

## Security Defaults

- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: true`
- CommonJS preload output for sandbox compatibility
- Content Security Policy in the renderer
- No token or raw IPC renderer object exposed to the renderer
- Sidecar binds to loopback only
- External links open in the system browser

## Repository Layout

```text
src/
  main/                 Electron lifecycle, sidecar supervisor, IPC
  preload/              contextBridge API
  renderer/             React application
  shared/               typed IPC contracts
backend/
  app/                  FastAPI app, auth, schemas, sidecar entry
  tests/                unit and process integration tests
scripts/
  check.ps1             Unified verification
  fluent_poc.py         M0 Fluent feasibility probe
  check_m0_reports.py   M0 evidence gate
docs/
  adr/                  Architecture decisions
  poc/                  Fluent integration evidence
```

## Setup

### Frontend

```powershell
pnpm install
pnpm setup:electron
```

If the Electron binary download is unavailable:

```powershell
$env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
pnpm setup:electron
```

### Python sidecar

```powershell
& 'C:\Users\MECH\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m venv .venv

& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements-dev.txt
```

## Development

Start the complete desktop application, including automatic sidecar startup:

```powershell
pnpm dev
```

The window displays the current sidecar state. If the sidecar is ready, it also shows version, PID, and the random localhost port.

Start only the FastAPI sidecar:

```powershell
pnpm backend:dev
```

The development script generates and prints a temporary token. Authenticated readiness can then be checked with:

```powershell
$headers = @{ Authorization = "Bearer <printed-token>" }
Invoke-RestMethod http://127.0.0.1:8765/api/system/ready -Headers $headers
```

## Verification

Run the complete M2 gate:

```powershell
pnpm check
```

Expected final marker:

```text
M2_CHECK_PASSED
```

Build production assets:

```powershell
pnpm build
```

## Evidence

- M2 verification: `docs/m2-verification.md`
- M2 architecture decision: `docs/adr/0003-m2-sidecar-lifecycle.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Raw M0 reports: `docs/poc/reports/`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M3 will add:

- SQLite schema and migrations;
- automation and model repositories;
- model-to-automation associations;
- application settings;
- jobs and sync-log persistence;
- FakeFluentAdapter-based domain tests.
