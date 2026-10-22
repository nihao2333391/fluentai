# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC and sidecar supervision: PASSED**
- **M3 - Database and domain model: PASSED**
- **M4 - Electron security and file capabilities: PASSED**
- **M5 - UI framework and design system: NOT STARTED**

M4 completes the secure bridge between the Renderer and the M3 business API. Model paths must originate from a native file picker, Fluent passwords are encrypted through Electron safeStorage, and all business operations use typed preload IPC rather than direct HTTP access.

## Architecture

```text
React renderer
    ↓ typed renderer service
    ↓ narrow preload API
Electron main process
    ├─ sidecar supervisor
    ├─ authenticated API proxy
    ├─ native model-file picker and path registry
    ├─ safeStorage credential vault
    └─ user-data database path
          ↓ 127.0.0.1 + bearer token
FastAPI sidecar
    ├─ authentication
    ├─ business API
    ├─ SQLite migrations and repositories
    └─ FakeFluentAdapter
          ↓ future FluentAdapter
ANSYS Fluent 2025 R2
```

## Security Model

- `contextIsolation: true`
- `nodeIntegration: false`
- `sandbox: true`
- CommonJS preload output
- Content Security Policy
- No raw `ipcRenderer` or arbitrary IPC channel exposed
- Bearer token remains in the Electron main process
- Renderer communicates with the sidecar only through typed IPC
- Model file paths require a native file picker selection token
- Selected paths are canonicalized and validated as regular, non-empty Fluent files
- Fluent passwords are encrypted with Electron safeStorage
- Existing passwords are never returned to the Renderer
- External links open in the system browser

## M4 Capabilities

### Native model file selection

Supported files:

- `.cas`
- `.cas.h5`
- `.msh`
- `.msh.h5`

The Renderer receives a short-lived selection token plus display metadata. The main process resolves the token to the canonical path only when creating or updating a model.

### Model metadata refresh

`POST /api/models/{id}/refresh` re-reads the selected file and updates:

- file size
- modification time
- updated timestamp

Missing, inaccessible, empty, directory, or unsupported paths are rejected.

### Encrypted Fluent credentials

The main process stores the encrypted Fluent password at:

`%APPDATA%\fluent-ai\secrets\fluent-credentials.json`

The Renderer can only:

- query whether secure storage is available;
- query whether a password is configured;
- set or replace the password;
- clear the password.

It cannot read the existing password.

### Typed business IPC

The preload API now exposes:

- automations
- models and file selection
- settings
- jobs
- sync logs
- credential status and management

The Renderer service wrapper is in `src/renderer/src/services/fluentAi.ts`.

## Development

Install and run:

```powershell
pnpm install
pnpm setup:electron

& 'C:\Users\MECH\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements-dev.txt

pnpm dev
```

## Verification

```powershell
pnpm check
```

Expected final marker:

```text
M4_CHECK_PASSED
```

## Evidence

- M4 verification: `docs/m4-verification.md`
- M4 architecture decision: `docs/adr/0005-m4-secure-file-and-credentials.md`
- M3 verification: `docs/m3-verification.md`
- M2 verification: `docs/m2-verification.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M5 will add:

- React Router with four top-level modules;
- Ant Design 5 theme and locale integration;
- responsive application shell;
- global sidecar and task status surfaces;
- loading, empty, error, and permission states;
- i18n foundation and theme switching;
- frontend component and layout tests.
