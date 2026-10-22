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
- **M7 - First end-to-end vertical slice: NOT STARTED**

M6 adds a real Fluent 2025 R2 PyFluent adapter, a curated catalog of 20 validated settings, typed read/write/apply operations, readback verification, and rollback reporting.

## Architecture

```text
React renderer
    ├─ four-module Ant Design shell
    ├─ typed Renderer service layer
    └─ persisted theme and language
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
    ├─ SQLite migrations and repositories
    └─ Fluent service layer
          ├─ FluentSettingCatalog 25.2
          ├─ PyFluentAdapter
          └─ FakeFluentAdapter
               ↓
ANSYS Fluent 2025 R2
```

## M6 FluentAdapter

`PyFluentAdapter` supports:

- launch mode;
- attach mode by host/port or server-info file;
- session status and version information;
- case loading;
- case saving;
- reading catalog settings;
- writing settings with immediate readback verification;
- applying a versioned preset document;
- rollback after partial write failure;
- per-setting success and diagnostic results.

The sidecar API and UI do not yet expose Fluent operations. M7 will connect the adapter through authenticated routes and the first end-to-end workflow.

## Validated SettingCatalog 25.2

The catalog contains 20 settings verified against Fluent 2025 R2:

- solver time;
- solver type;
- velocity formulation;
- energy equation;
- viscous model;
- k-omega model;
- low-Re correction;
- curvature correction;
- corner-flow correction;
- six residual criteria;
- reference area;
- reference density;
- reference length;
- reference velocity;
- reference viscosity.

Each setting has:

- stable setting ID;
- display name;
- value type;
- getter and setter;
- allowed values or numeric range;
- description.

## Readback and rollback

Writes are evaluated as follows:

```text
validate all requested values
→ capture original values
→ apply each setting
→ read every value back
→ compare with numeric tolerance
→ stop and rollback on failure
→ verify rollback values
→ return a structured report
```

No arbitrary Python/TUI execution is exposed through this adapter.

## Real Fluent Evidence

Validated against Ansys Fluent 2025 R2:

- all 20 catalog settings read successfully;
- three settings applied through `apply_preset`;
- all three readback values matched;
- original values restored through `write_settings`;
- all 20 values matched the original state;
- adapter disconnected cleanly;
- no Fluent process remained.

Evidence:

- `docs/poc/reports/m6_fluent_adapter.json`
- `docs/m6-verification.md`

## Technology Baseline

| Layer        | Version                  |
| ------------ | ------------------------ |
| Node.js      | 24.21.0                  |
| pnpm         | 12.5.1                   |
| Electron     | 45.0.0                   |
| React        | 19.3.1                   |
| React Router | 7.18.4                   |
| Ant Design   | 5.29.3                   |
| Zustand      | 5.0.16                   |
| i18next      | 26.5.4                   |
| TypeScript   | 5.9.3                    |
| Python       | 3.12.14                  |
| FastAPI      | 0.159.1                  |
| PyFluent     | ansys-fluent-core 0.42.1 |

## Development and Verification

```powershell
pnpm dev
pnpm check
```

Expected final marker:

```text
M6_CHECK_PASSED
```

Run the real Fluent adapter validation:

```powershell
& 'D:\Fluent AI\fluent-ai-app\.venv\Scripts\python.exe' `
  'D:\Fluent AI\fluent-ai-app\scripts\validate_m6_fluent.py'
```

The validation launches Fluent, reads all catalog settings, applies three safe changes, verifies readback, restores the original state, writes the report, and closes the session.

## Evidence

- M6 verification: `docs/m6-verification.md`
- M6 architecture decision: `docs/adr/0007-m6-fluent-adapter.md`
- M5 verification: `docs/m5-verification.md`
- M4 verification: `docs/m4-verification.md`
- M3 verification: `docs/m3-verification.md`
- M2 verification: `docs/m2-verification.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M7 will add:

- FastAPI Fluent connection/status/read/write/apply endpoints;
- adapter lifecycle owned by the sidecar;
- preview and validation APIs;
- renderer workflows for applying a preset;
- first persisted model+automation end-to-end path;
- structured sync logs and job progress.
