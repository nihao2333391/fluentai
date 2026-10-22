# ADR 0008: First persisted Fluent vertical slice

- Status: accepted
- Date: 2026-10-22

## Context

M6 provided a validated adapter, but no application path connected persisted models and automations to a real Fluent session.

## Decision

### Fluent execution thread

- All adapter calls run on one dedicated `ThreadPoolExecutor` worker.
- This keeps PyFluent session operations on a consistent thread.
- PyFluent is preloaded by the sidecar main thread before readiness.
- Preloading avoids a Windows import-lock deadlock observed when NumPy/PyFluent were first imported from a FastAPI worker thread.

### API surface

The sidecar exposes authenticated endpoints for:

- connection status, connect and disconnect;
- catalog discovery;
- settings read/write;
- preset validation and direct apply;
- model open;
- persisted automation apply.

### Persisted workflow

`POST /api/automations/{id}/apply` performs:

1. create a queued job;
2. load model and automation records;
3. validate the preset;
4. reuse or create a Fluent connection;
5. load the selected model when requested;
6. apply the preset with readback verification;
7. persist a sync log;
8. update the job to succeeded or failed;
9. return a structured workflow report.

### UI vertical slice

- model page imports and lists real models;
- automation page loads the catalog and persists typed presets;
- automation list applies presets against a selected model;
- settings page persists Fluent launch/attach parameters;
- recent sync logs are visible;
- global task status polls active jobs every two seconds;
- business pages wait for sidecar readiness before requesting data.

## Consequences

- The first real end-to-end workflow is usable.
- PyFluent threading and import behavior are documented.
- More complete editing, association, job cancellation, and recovery remain M8 work.
- The sidecar API is now the system of record for workflow execution state.
