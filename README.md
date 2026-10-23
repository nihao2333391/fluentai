# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Repository

Team development repository:

```text
https://gitee.com/alcohol-free-beverage-station/fluent-ai-for-aic2026
```

See `CONTRIBUTING.md` for clone, branch, Pull Request, and validation instructions.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC and sidecar supervision: PASSED**
- **M3 - Database and domain model: PASSED**
- **M4 - Electron security and file capabilities: PASSED**
- **M5 - UI framework and design system: PASSED**
- **M6 - FluentAdapter and SettingCatalog: PASSED**
- **M7 - First end-to-end vertical slice: PASSED**
- **M8 - Complete Meshing automation and apply workflows: PASSED**
- **M9 - Delivery lifecycle and packaging: PASSED**
- **M10 - Product hardening: IN PROGRESS**
- **M11 - Meshing connection, direct read/write, and FDL UI metadata: PASSED**

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

- Catalog exposed 39 settings;
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
- `docs/verification/m7-verification.md`

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

Expected final markers:

```text
M8_SCHEMA_CHECK_PASSED
M8_APPLY_CHECK_PASSED
```

Run the real end-to-end workflow:

```powershell
& 'D:\Fluent AI\fluent-ai-app\.venv\Scripts\python.exe' `
  'D:\Fluent AI\fluent-ai-app\scripts\validate_m7_workflow.py'
```

## Windows Packager

Build the installable Windows x64 application:

```powershell
pnpm package:win
```

The command builds the Electron application, stages a standalone Python 3.12 sidecar, verifies the packaged sidecar, creates an NSIS installer, silently installs it, runs a packaged renderer/sidecar smoke test, and uninstalls the test installation.

Artifact:

```text
release\FluentAI-0.1.0-x64-Setup.exe
```

Current installer boundary: it is not Authenticode-signed. The Fluent AI application icon is included.

For signed releases, configure:

```powershell
$env:CSC_LINK = "D:\certificates\fluent-ai.pfx"
$env:CSC_KEY_PASSWORD = "<password>"
$env:FLUENT_AI_REQUIRE_SIGNING = "1"
pnpm package:win
```

The release pipeline writes `release-manifest.json` and a SHA-256 checksum, and refuses an unsigned artifact when required signing is enabled.

## Evidence

- M7 verification: `docs/verification/m7-verification.md`
- M9.2 packaging: `docs/verification/m9.2-verification.md`
- M7 architecture decision: `docs/adr/0008-m7-vertical-slice.md`
- M6 verification: `docs/verification/m6-verification.md`
- M5 verification: `docs/verification/m5-verification.md`
- M4 verification: `docs/verification/m4-verification.md`
- M3 verification: `docs/verification/m3-verification.md`
- M2 verification: `docs/verification/m2-verification.md`
- M1 verification: `docs/verification/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## M8 and M9 Progress

Completed:

- Fluent-style Solver preset editor;
- real enum option lists from Fluent 2025 R2;
- Watertight schema: 11 tasks and 562 arguments including nested templates;
- Fault-tolerant schema: 25 tasks and 635 arguments including nested templates;
- task/argument edit paths and allowed-value metadata extracted from PyFluent;
- independent Meshing automation database model;
- Meshing preset task/argument validation;
- authenticated Meshing automation CRUD APIs.
- exact live-name validation before any Meshing write;
- Watertight and Fault-tolerant geometry import;
- named compound-child creation and multiple local-sizing controls;
- readback verification and strict stop-before-mesh behavior;
- Solver automation edit and duplicate workflows;
- model association and direct open-in-Fluent actions.
- standalone Python sidecar staged into Electron resources;
- Windows NSIS installer with silent install/uninstall smoke verification;
- installed application verified to load the real renderer and reach sidecar readiness.
- formal application icon;
- daily and manual SQLite backups with integrity checks and safety restore;
- sidecar development-dependency pruning.
- Solver Methods, Initialization and Run Calculation branches with real read/write/restore verification.
- Model-specific fluid material density and viscosity presets discovered after case load.
- Named velocity-inlet, pressure-outlet and wall boundary-condition presets discovered from the active case.
- Residual monitor options and per-equation residual monitor toggles.

M9 completion includes:

- recent-session restore across application restarts;
- detailed job progress and cooperative cancellation;
- server-side sync-log filtering by direction, status, model, automation, and text.
