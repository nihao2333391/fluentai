# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC and sidecar supervision: PASSED**
- **M3 - Database and domain model: PASSED**
- **M4 - Electron security and file capabilities: NOT STARTED**

The application now starts a supervised FastAPI sidecar, initializes a versioned SQLite database, and exposes authenticated CRUD APIs for automations, models, associations, settings, jobs, and synchronization logs.

## Architecture

```text
React renderer
    ↓ typed preload IPC
Electron main process
    ├─ sidecar supervisor
    ├─ random port + bearer token
    ├─ user-data database path
    └─ narrow IPC handlers
          ↓ 127.0.0.1
FastAPI sidecar
    ├─ bearer authentication
    ├─ authenticated business API
    ├─ SQLite migrations and repositories
    └─ FakeFluentAdapter
          ↓ future FluentAdapter
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

## Persistence

SQLite is owned exclusively by the Python sidecar.

- Production data path: `%APPDATA%\fluent-ai\data\fluent-ai.db`
- Development fallback: `.runtime\data\fluent-ai.db`
- WAL journal mode
- Foreign keys enabled
- Connection per operation
- Versioned migrations in `schema_migrations`

Tables:

- `automations`
- `models`
- `model_automations`
- `app_settings`
- `jobs`
- `sync_logs`
- `schema_migrations`

Automation presets are versioned JSON documents with typed setting items. Models and automations use a many-to-many association, with at most one default automation per model.

## Authenticated Business API

- `/api/automations`
- `/api/automations/{id}`
- `/api/models`
- `/api/models/{id}`
- `/api/models/{id}/associate`
- `/api/settings`
- `/api/jobs`
- `/api/jobs/{id}`
- `/api/sync-logs`

All business endpoints require the per-launch bearer token. FastAPI also exposes `/docs` and `/openapi.json` on the loopback listener for development.

## Development

Install dependencies:

```powershell
pnpm install
pnpm setup:electron

& 'C:\Users\MECH\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe' `
  -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.\.venv\Scripts\python.exe' -m pip install -r backend\requirements-dev.txt
```

Run the complete desktop app:

```powershell
pnpm dev
```

Run only the sidecar in development:

```powershell
pnpm backend:dev
```

The development script prints a temporary bearer token. Use it for authenticated readiness or API requests.

## Verification

```powershell
pnpm check
```

Expected final marker:

```text
M3_CHECK_PASSED
```

Run the M3 database/API tests directly:

```powershell
$env:PYTHONPATH = 'D:\Fluent AI\fluent-ai-app\backend'
& 'D:\Fluent AI\fluent-ai-app\.venv\Scripts\python.exe' `
  -m pytest -q 'D:\Fluent AI\fluent-ai-app\backend\tests'
```

## Evidence

- M3 verification: `docs/m3-verification.md`
- M3 architecture decision: `docs/adr/0004-m3-persistence.md`
- M2 verification: `docs/m2-verification.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M4 will add:

- secure Electron file pickers and path validation;
- model file metadata refresh;
- encrypted handling for future Fluent credentials;
- IPC methods for business operations;
- typed renderer service layer;
- file-related error and permission tests.
