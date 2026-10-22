# ADR 0009: Fluent-style preset editor

- Status: accepted
- Date: 2026-10-22

## Context

The first automation form exposed stable setting IDs and raw string values. That was technically functional but did not match how Fluent users select solver and model options.

## Decision

Automation creation uses a Fluent-oriented grouped workflow.

### Groups

- General
- Models
- Solution
- Reference Values

### Option controls

- enum settings use Select controls populated from real Fluent 2025 R2 `allowed_values()`;
- boolean settings use Switch controls;
- numeric settings use bounded InputNumber controls;
- string settings use text input only when required.

### Preset inclusion

Every setting has an explicit checkbox. Only checked settings are written to the versioned preset JSON. This avoids silently storing the entire Fluent state.

### Real enum options

The catalog now contains verified Fluent 2025 R2 choices, including:

- solver time;
- pressure/density-based solver type;
- absolute/relative velocity formulation;
- viscous models;
- k-omega submodels.

## Consequences

- Users no longer type internal setting IDs or arbitrary enum values.
- Presets remain declarative and validated by the backend.
- Additional Fluent branches require validated catalog metadata and controls before appearing in the UI.
- Case-dependent materials, zones, and boundary conditions require a model-aware schema in the next M8 step.
