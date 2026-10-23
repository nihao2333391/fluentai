# Contributing to Fluent AI

## Repository

```text
https://gitee.com/alcohol-free-beverage-station/fluent-ai-for-aic2026
```

## Prerequisites

- Windows 10/11 x64
- Node.js 24+
- pnpm 12+
- Python 3.12
- ANSYS Fluent 2025 R2 for real integration tests

## First checkout

```powershell
git clone https://gitee.com/alcohol-free-beverage-station/fluent-ai-for-aic2026.git
cd fluent-ai-for-aic2026
pnpm install
```

Create the Python environment according to `README.md`, then run:

```powershell
pnpm check
```

## Branch workflow

Do not develop directly on `main`.

```powershell
git checkout main
git pull --ff-only
git checkout -b feature/short-description
git add .
git commit -m "feat: concise description"
git push -u origin feature/short-description
```

Open a Gitee Pull Request into `main`, request review, and merge only after checks pass.

## Commit prefixes

- `feat:` new capability
- `fix:` defect correction
- `test:` test-only change
- `docs:` documentation
- `refactor:` behavior-preserving restructuring
- `chore:` tooling or maintenance

## Generated and local-only files

Do not commit:

- `node_modules/`, `.venv/`
- `build/`, `out/`, `release/`, `outputs/`
- `.runtime/` and Python caches
- Fluent `*.trn` transcripts
- local databases, credentials, tokens, or ANSYS license data

The latest production installer is published as a release asset rather than committed to Git.

## Required validation

For UI and backend changes:

```powershell
pnpm check
```

For Meshing interface changes, also confirm:

```text
M8_SCHEMA_CHECK_PASSED
M8_APPLY_CHECK_PASSED
MESHING_INTERFACE_CHECK_PASSED
```

Real Fluent tests must not generate surface or volume meshes unless explicitly requested.
