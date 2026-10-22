# ADR 0007: Versioned Fluent adapter and setting catalog

- Status: accepted
- Date: 2026-10-22

## Context

The M0 proof demonstrated low-level PyFluent access. M6 needs a stable application-facing contract rather than page-specific PyFluent calls.

## Decision

### Adapter contract

`FluentAdapter` exposes connection, status, case loading/saving, catalog reads, writes, and preset application. Both `PyFluentAdapter` and `FakeFluentAdapter` implement this contract.

### Versioned catalog

`FluentSettingCatalog` maps stable setting IDs to version-specific getter and setter functions. The Fluent 2025 R2 catalog contains exactly 20 settings that passed live read-write-read validation.

Catalog values are validated before any write:

- strict integer, float, boolean, string, or enum types;
- optional allowed-value sets;
- optional numeric bounds;
- duplicate IDs rejected at catalog construction.

### Connection behavior

- launch mode starts a dedicated solver session;
- attach mode connects by host/port or server-info file;
- attached sessions are not terminated by adapter disconnect;
- launched sessions are closed through `session.exit()`;
- no arbitrary TUI or Python execution is exposed.

### Write verification and rollback

1. Validate all settings before modifying Fluent.
2. Capture original values.
3. Apply settings sequentially.
4. Read each value back immediately.
5. Compare numerics with tolerance.
6. On any failure, attempt to restore every captured value.
7. Verify rollback values.
8. Return a structured report containing forward and rollback outcomes.

### Test doubles

`FakeFluentAdapter` follows the same report model and exercises rollback without Fluent or a license.

## Consequences

- Business code depends on stable setting IDs, not PyFluent object paths.
- Version upgrades require a new catalog/adapter rather than scattered conditional logic.
- Live validation can be rerun independently of the UI.
- Sidecar API exposure remains an M7 task.
