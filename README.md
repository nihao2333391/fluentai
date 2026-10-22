# Fluent AI

Fluent AI is a Windows desktop application for managing reusable ANSYS Fluent automation presets, model references, Fluent connections, and verified setting synchronization.

## Current Status

- **M0 - Fluent feasibility: PASSED**
- **M1 - Engineering foundation: PASSED**
- **M2 - IPC and sidecar supervision: PASSED**
- **M3 - Database and domain model: PASSED**
- **M4 - Electron security and file capabilities: PASSED**
- **M5 - UI framework and design system: PASSED**
- **M6 - FluentAdapter and SettingCatalog: NOT STARTED**

The application now has a responsive four-module Ant Design shell with route navigation, persistent light/dark/system themes, Chinese/English localization, global sidecar and task status, and reusable loading, empty, error, and permission states.

## Architecture

```text
React renderer
    ├─ React Router 7 hash routes
    ├─ Ant Design 5 + design tokens
    ├─ Zustand persisted preferences
    ├─ i18next Chinese/English resources
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
    ├─ SQLite migrations and repositories
    └─ FakeFluentAdapter
          ↓ future FluentAdapter
ANSYS Fluent 2025 R2
```

## Four Top-Level Modules

- 自动化创建 / Create Automation
- 我的自动化 / My Automations
- 我的模型 / My Models
- 设置 / Settings

M5 establishes the route, navigation, responsive layout, design system, state components, and settings controls. The individual automation and model business forms remain placeholders until their corresponding workflow milestones.

## UI Framework

| Capability             | Implementation                              |
| ---------------------- | ------------------------------------------- |
| Routing                | React Router 7 hash router                  |
| Components             | Ant Design 5                                |
| Icons                  | Ant Design Icons                            |
| UI state               | Zustand 5 with persisted preferences        |
| Localization           | i18next + react-i18next                     |
| React 19 compatibility | `@ant-design/v5-patch-for-react-19`         |
| Theme                  | Ant Design algorithms plus CSS variables    |
| Responsive behavior    | Ant Design Layout/Sider and CSS breakpoints |

### Theme

Supported modes:

- light
- dark
- follow system

Theme and language preferences persist in local storage under `fluent-ai-ui-preferences`.

### Localization

Chinese and English resources are kept key-for-key equivalent by an automated test. Ant Design locale providers switch together with the application language.

### Page states

Reusable components cover:

- loading
- empty
- error with retry action
- unavailable desktop bridge
- permission/bridge unavailable state

### Global status surfaces

The application header shows:

- active job count, including no-active-task state;
- FastAPI sidecar state;
- sidecar version, PID, and random port in a popover;
- manual sidecar restart.

## Technology Baseline

| Layer         | Version                  |
| ------------- | ------------------------ |
| Node.js       | 24.21.0                  |
| pnpm          | 12.5.1                   |
| Electron      | 45.0.0                   |
| electron-vite | 6.0.0                    |
| Vite          | 8.3.5                    |
| React         | 19.3.1                   |
| React Router  | 7.18.4                   |
| Ant Design    | 5.29.3                   |
| Zustand       | 5.0.16                   |
| i18next       | 26.5.4                   |
| TypeScript    | 5.9.3                    |
| Python        | 3.12.14                  |
| FastAPI       | 0.159.1                  |
| PyFluent      | ansys-fluent-core 0.42.1 |

## Development

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
M5_CHECK_PASSED
```

## Evidence

- M5 verification: `docs/m5-verification.md`
- M5 architecture decision: `docs/adr/0006-m5-ui-framework.md`
- M4 verification: `docs/m4-verification.md`
- M3 verification: `docs/m3-verification.md`
- M2 verification: `docs/m2-verification.md`
- M1 verification: `docs/m1-verification.md`
- M0 Fluent report: `docs/poc/fluent-2025R2.md`
- Known boundaries: `docs/KNOWN_ISSUES.md`

## Next Milestone

M6 will add:

- explicit Fluent 2025 R2 adapter implementation;
- curated SettingCatalog with 10-20 validated settings;
- typed read/write/apply operations;
- readback validation and rollback reports;
- FakeFluentAdapter contract tests;
- integration tests against the real M0 Fluent environment.
