# ADR 0001: Reuse the locally verified PyFluent environment for M0

- Status: accepted for M0
- Date: 2026-10-22

## Context

The implementation plan originally proposed a new Python 3.10 environment. The workstation already contains a proven Python 3.12 environment at `D:\Fluent AI\.venvs\ansys-wwj` with `ansys-fluent-core 0.42.1`, and this environment has previously been used for Fluent 2025 R2 work.

## Decision

M0 reuses the existing Python 3.12/PyFluent 0.42.1 environment instead of creating a second unverified Python environment. Exact installed packages are exported to `requirements-m0.lock.txt`.

## Consequences

- M0 tests the known-good local baseline sooner.
- The application runtime is not yet frozen for distribution.
- Before M1 or packaging, we must decide whether to:
  1. bundle a validated Python runtime with PyInstaller, or
  2. create a new reproducible environment and repeat the gate tests.
- Python 3.10 remains an option for production if compatibility testing proves it safer.