# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC contracts and sidecar supervision: NOT STARTED**

M1 provides a runnable Electron + React + TypeScript shell and a FastAPI sidecar skeleton. It does not yet start the sidecar from Electron or expose application APIs.

## Architecture

```text
React renderer
    ↓ typed preload API
Electron main process
    ↓ future secure local IPC
FastAPI sidecar
    ↓ PyFluent
ANSYS Fluent 2025 R2
```

Security defaults:

- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: true`
- CommonJS preload output for sandbox compatibility
- Content Security Policy in the renderer
- External links are denied inside Electron and opened by the system browser

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

## Repository Layout

```text
src/
  main/                 Electron main process
  preload/              contextBridge API
  renderer/             React application
backend/
  app/                  FastAPI sidecar
  tests/                Python tests
scripts/
  fluent_poc.py         M0 Fluent feasibility probe
  check_m0_reports.py   M0 report gate
  check.ps1             Unified local verification
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

`pnpm setup:electron` verifies the Electron runtime binary. If the normal download is unavailable, use:

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

## Development Commands

Run Electron with Vite hot reload:

```powershell
pnpm dev
```

Run the FastAPI sidecar:

```powershell
pnpm backend:dev
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Run the complete M1 verification:

```powershell
pnpm check
```

Production build:

```powershell
pnpm build
```

## M0 Regression Commands

Environment check:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' env-check
```

Launch Fluent, load a case, read six settings, write and restore one setting:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' launch --ui-mode no_gui
```

Keep a session alive for attach testing:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' launch-hold --hold-seconds 120
```

Attach from a second PowerShell window:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\fluent_poc.py' attach
```

Check all M0 evidence:

```powershell
& 'D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe' `
  '.\scripts\check_m0_reports.py'
```

## Evidence

- M0 report: `docs/poc/fluent-2025R2.md`
- Raw M0 reports: `docs/poc/reports/`
- M1 decisions: `docs/adr/0002-m1-stack.md`
- M1 verification: `docs/m1-verification.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M2 will add:

- typed frontend/backend contracts;
- FastAPI lifecycle health and readiness;
- Electron main-process sidecar supervision;
- random localhost port and bearer-token handshake;
- narrow preload IPC methods;
- sidecar shutdown and restart behavior.
