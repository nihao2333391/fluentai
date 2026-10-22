# Project Progress

| Milestone                                  | Status      | Summary                                                                                             |
| ------------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------- |
| M0 - Fluent feasibility                    | PASSED      | launch, GUI launch, attach, case load, 6 settings read, write/restore verified, cleanup verified    |
| M1 - Engineering foundation                | PASSED      | Electron + React + TypeScript shell, FastAPI sidecar skeleton, linting, typing, tests, build and CI |
| M2 - IPC contracts and sidecar supervision | NOT STARTED | Awaiting approval after M1 review                                                                   |

## M0 Evidence

- Script: `scripts/fluent_poc.py`
- Gate checker: `scripts/check_m0_reports.py`
- Report: `docs/poc/fluent-2025R2.md`
- Raw reports: `docs/poc/reports/`

## M1 Evidence

- Desktop entry: `src/main/index.ts`
- Preload bridge: `src/preload/index.ts`
- Renderer: `src/renderer/src/App.tsx`
- Sidecar: `backend/app/main.py`
- Unified check: `scripts/check.ps1`
- CI: `.github/workflows/ci.yml`
- Decision record: `docs/adr/0002-m1-stack.md`
