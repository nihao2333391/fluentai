# ADR 0010: Separate Fluent Meshing workflow automation

- Status: accepted
- Date: 2026-10-22

## Context

Fluent Solver presets and Fluent Meshing workflow presets use different objects, tasks, validation rules and application semantics. The existing Solver SettingCatalog cannot represent the Meshing task tree.

## Decision

### Separate automation type

Meshing Automation is independent from Solver Automation:

- separate preset schema;
- separate workflow type;
- separate editor and validation;
- separate apply engine;
- shared model library and safe file picker only.

### Supported workflow families

- Fluent Meshing 2025 R2 Watertight Geometry
- Fluent Meshing 2025 R2 Fault-tolerant Meshing

### Schema source

The canonical schema comes from live workflow/task argument objects exposed by PyFluent, not from hardcoded UI labels alone. The reference `.wft` file supplies a real-world baseline and verification values.

### Execution boundary

Applying a Meshing preset writes selected workflow arguments and verifies them by readback. It stops before surface-mesh or volume-mesh generation unless a later milestone explicitly changes this boundary.

### Dynamic model data

Boundary, face-zone, region and local-sizing scopes are model-dependent. Presets are intended for consistently named members of the same model family.

If any required name is missing:

- abort the apply operation;
- report the task and missing name;
- list available names;
- do not perform fuzzy replacement.

### UI

- No embedded three-dimensional geometry viewport in the first implementation.
- Fluent-style task navigation and controls.
- Advanced options remain collapsed by default.
- Users explicitly include only the options they want in the preset.

## Consequences

- Solver and Meshing automation remain independently testable.
- Full option coverage can be generated from the official workflow API.
- Model-specific validation is mandatory.
- Mesh generation remains a separate future capability.
