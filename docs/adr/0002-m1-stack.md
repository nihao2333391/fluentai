# ADR 0002: M1 stack and process boundaries

- Status: accepted
- Date: 2026-10-22

## Context

M1 must provide a runnable desktop shell without prematurely implementing sidecar lifecycle management or business features.

## Decision

### Frontend

- Electron 45
- electron-vite 6
- Vite 8
- React 19
- TypeScript 5.9
- Vitest 4 and Testing Library

React 19 is used because it is the current stable runtime at implementation time. The original plan recommended React 18; this is not a product-level constraint. Ant Design integration will be evaluated again in M5.

### Electron security

- Renderer uses `contextIsolation: true`, `nodeIntegration: false`, and `sandbox: true`.
- Preload is explicitly emitted as CommonJS `out/preload/index.js`.
- The renderer has a Content Security Policy.
- Navigation to external pages is delegated to the system browser.

### Python sidecar

- M1 uses a project-specific Python 3.12 virtual environment at `.venv`.
- FastAPI and PyFluent versions are pinned in `backend/requirements*.txt`.
- The sidecar currently exposes only `/health`.
- Electron does not yet launch or supervise the sidecar.

### Verification

`scripts/check.ps1` runs:

- frontend lint and formatting;
- TypeScript checks;
- React tests;
- production build;
- Python lint and formatting;
- strict mypy;
- FastAPI tests;
- the M0 regression report gate.

## Consequences

- M1 is independently runnable and testable.
- The sidecar is isolated from the shared M0 Python environment.
- M2 can add lifecycle supervision without changing the renderer's security model.
- The app remains unpackaged until later milestones.
