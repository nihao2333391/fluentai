# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC and sidecar supervision: PASSED**
- **M3 - Database and domain model: PASSED**
- **M4 - Electron security and file capabilities: PASSED**
- **M5 - UI framework and design system: PASSED**
- **M6 - FluentAdapter and SettingCatalog: PASSED**
- **M7 - First end-to-end vertical slice: PASSED**
- **M8 - Complete automation and model workflows: IN PROGRESS**

The application now supports a real, persisted vertical workflow:

```text
launch or attach Fluent
→ connect and show status
→ import a model through the native picker
→ load the model into Fluent
→ create a validated automation preset
→ select the model
→ apply the preset
→ verify each setting by readback
→ persist a job and sync log
→ restore the previous value
```

## Real Fluent Evidence

The M7 validation ran through the real sidecar HTTP API and Fluent 2025 R2:

- Catalog exposed 20 settings;
- Fluent launched and reported a real PID and port;
- model file imported into SQLite;
- model loaded into Fluent;
- automation created with `reference.area = 1.05`;
- workflow applied the automation;
- readback returned `1.05`;
- previous value `1.0` restored;
- job status reached `succeeded` with 100% progress;
- apply and write sync logs were persisted;
- Fluent disconnected cleanly;
- sidecar exited with code 0.

Evidence:

- `docs/poc/reports/m7_workflow.json`
- `docs/m7-verification.md`

## Architecture

```text
React renderer
    ├─ four-module Ant Design shell
    ├─ real model import and automation forms
    ├─ workflow apply controls
    └─ typed Renderer service layer
          ↓ narrow preload API
Electron main process
    ├─ sidecar supervisor
    ├─ authenticated API proxy
    ├─ native model-file picker
    ├─ safeStorage credential vault
    └─ user-data database path
          ↓ 127.0.0.1 + bearer token
FastAPI sidecar
    ├─ authentication
    ├─ business API
    ├─ FluentService dedicated execution thread
    ├─ SQLite repositories
    ├─ jobs and sync logs
    └─ PyFluentAdapter
          ↓
ANSYS Fluent 2025 R2
```

## Vertical-Slice Capabilities

### Fluent connection

- launch and attach configuration;
- dedicated single-thread executor for PyFluent;
- main-thread PyFluent preload in the sidecar to avoid worker-thread import deadlocks;
- connection status with version, PID, host, and port;
- explicit disconnect.

### Model library

- native Electron file picker;
- secure selection token;
- model persistence with size and timestamp;
- model load into Fluent;
- metadata refresh API.

### Automation creation

- Fluent-style preset workflow;
- left-side groups matching Fluent concepts: General, Models, Solution, Reference Values;
- real Fluent 2025 R2 enum choices for solver time/type, velocity formulation, viscous and k-omega models;
- switches for boolean model options;
- numeric controls for residual criteria and reference values;
- explicit include/exclude selection for every preset item;
- no manual setting-ID entry;
- backend validation before persistence;
- duplicate-name protection;
- preset stored as versioned JSON.

### Apply workflow

- choose a persisted model;
- connect automatically when needed;
- load the model;
- apply the preset;
- per-setting readback verification;
- best-effort rollback on partial failure;
- task lifecycle persisted in `jobs`;
- apply/write results persisted in `sync_logs`;
- recent sync logs shown in the automation page.

## Fluent API

- `GET /api/fluent/status`
- `POST /api/fluent/connect`
- `POST /api/fluent/disconnect`
- `GET /api/fluent/catalog`
- `POST /api/fluent/settings/read`
- `POST /api/fluent/settings/write`
- `POST /api/fluent/presets/validate`
- `POST /api/fluent/presets/apply`
- `POST /api/models/{id}/open`
- `POST /api/automations/{id}/apply`

All endpoints require the per-launch bearer token.

## Development and Verification

```powershell
pnpm dev
pnpm check
```

Expected final marker:

```text
M7_CHECK_PASSED
```

Run the real end-to-end workflow:

```powershell
& 'D:\Fluent AI\fluent-ai-app\.venv\Scripts\python.exe' `
  'D:\Fluent AI\fluent-ai-app\scripts\validate_m7_workflow.py'
```

## Evidence

- M7 verification: `docs/m7-verification.md`
- M7 architecture decision: `docs/adr/0008-m7-vertical-slice.md`
- M6 verification: `docs/m6-verification.md`
- M5 verification: `docs/m5-verification.md`
- M4 verification: `docs/m4-verification.md`
- M3 verification: `docs/m3-verification.md`
- M2 verification: `docs/m2-verification.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## M8 Progress

Completed:

- Fluent-style grouped preset editor;
- real enum option lists from Fluent 2025 R2;
- per-setting include controls and type-specific widgets.

Remaining M8 work:

- Materials and cell-zone branches;
- boundary-condition and named-zone selectors;
- solver methods and controls;
- monitors, initialization and calculation activities;
- full automation edit and duplicate workflows;
- richer model-to-automation associations;
- recent-session restore;
- detailed job progress and cancellation;
- sync-log details and filtering;
- broader error recovery and UI regression coverage.
