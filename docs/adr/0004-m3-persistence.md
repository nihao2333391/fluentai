# ADR 0004: SQLite persistence and domain repositories

- Status: accepted
- Date: 2026-10-22

## Context

M3 needs persistent automations, model references, associations, settings, jobs, and synchronization logs without introducing a second database owner in Electron.

## Decision

### Ownership

- The Python sidecar is the only component that opens the SQLite database.
- Electron passes `FLUENT_AI_DATA_DIR` through the sidecar environment.
- Production data is stored under `%APPDATA%\fluent-ai\data`.
- Development falls back to `.runtime\data`.

### Connection strategy

- A connection is opened per repository operation.
- `foreign_keys = ON` is set for every connection.
- `busy_timeout` is 5 seconds.
- WAL journal mode is enabled during initialization.
- Transactions commit on success and roll back on exceptions.

### Migrations

- `schema_migrations` records applied versions.
- Migration 1 creates all M3 tables and default app settings.
- Future schema changes must add a new immutable migration; existing migrations are not edited after release.

### Domain model

- Automation presets are versioned JSON documents with typed setting items.
- Models and automations use a many-to-many association table.
- A partial unique index enforces at most one default automation per model.
- Jobs and sync logs are persisted now, even though execution workers arrive later.

### API

- Business routes are grouped under an authenticated `/api` router.
- Repository exceptions map to HTTP 404 and 409.
- Missing model files map to HTTP 400.
- Response contracts are Pydantic models in the Python sidecar and mirrored TypeScript types in the renderer IPC contract.

### Fluent boundary

`FakeFluentAdapter` implements the initial adapter contract so domain and application logic can be tested without Fluent or a license.

## Consequences

- Database access remains single-owner and testable.
- Repository tests can run without Fluent.
- The business API is ready for the renderer service layer.
- Packaged database backup, compaction, and export remain future work.
