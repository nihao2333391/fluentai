# ADR 0011: Meshing preset storage and validation contract

- Status: accepted
- Date: 2026-10-22

## Context

M8.1 produced complete Watertight and Fault-tolerant task schemas, but there was no persisted Meshing preset model or API.

## Decision

### Separate persistence

Meshing automations are stored in a dedicated `meshing_automations` table rather than reusing Solver automation rows.

Fields include:

- unique name;
- description;
- model family;
- optional reference model;
- workflow type;
- versioned preset JSON;
- draft/active status;
- timestamps.

A migration from schema version 1 to version 2 adds the table without rewriting Solver data.

### Preset item identity

Each selected option is identified by:

```json
{
  "task_path": ["add_local_sizing", "wall-big"],
  "argument_path": ["boi_size"],
  "value": 0.001,
  "required": true
}
```

- `task_path` follows the real workflow task hierarchy.
- `argument_path` follows nested command arguments.
- Values support scalar, list and object JSON types.

### Validation

Preset validation checks:

- workflow schema exists;
- task path exists;
- argument path exists;
- argument is editable;
- value type matches;
- allowed values are respected;
- duplicate task/argument selections are rejected.

Validation occurs before create and update.

### API

New authenticated routes:

- `GET /api/meshing/schemas`
- `POST /api/meshing/presets/validate`
- `GET/POST /api/meshing-automations`
- `GET/PUT/DELETE /api/meshing-automations/{id}`
- `POST /api/meshing-automations/{id}/validate`

### Model-family intent

A Meshing preset targets a consistently named model family rather than one exact case. The optional reference model identifies the family baseline. Runtime name validation remains mandatory before applying a preset.

## Consequences

- Solver and Meshing automation data remain independent.
- Meshing presets can be created before the editor UI is complete.
- Schema updates can invalidate old presets in a controlled way.
- UI and apply engine are the next required steps.
