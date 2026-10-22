# M6 Verification Record

- Date: 2026-10-22
- Status: **PASSED**

## Automated Verification

| Check                               | Result                        |
| ----------------------------------- | ----------------------------- |
| `pnpm lint`                         | PASS                          |
| `pnpm format:check`                 | PASS                          |
| `pnpm typecheck`                    | PASS                          |
| Vitest                              | PASS, 12 tests across 6 files |
| Electron production build           | PASS                          |
| Ruff                                | PASS                          |
| Ruff format check                   | PASS                          |
| strict mypy                         | PASS, 38 source files         |
| FastAPI, adapter, repository pytest | PASS, 25 tests                |
| M0 regression gate                  | PASS                          |
| M6 real-Fluent report gate          | PASS                          |
| Unified command `pnpm check`        | PASS, `M6_CHECK_PASSED`       |

## Catalog Verification

- Exactly 20 unique setting IDs.
- Duplicate catalog IDs rejected.
- Invalid residual bounds rejected.
- Boolean settings reject integer values.
- Enum settings reject unknown values.
- All 20 settings were read from a real Fluent 2025 R2 session.
- All 20 candidates passed a same-value write and readback probe before being included.

## Adapter Verification

- Successful writes return per-setting expected and actual values.
- Validation failure prevents all writes.
- Partial write failure triggers rollback.
- Rollback readback is verified.
- Apply operations use operation type `apply`.
- Adapter reports disconnected after session shutdown.
- Reading without a connected session fails clearly.
- FakeFluentAdapter follows the same rollback/report contract.

## Real Fluent Result

The real validation report records:

- catalog size: 20;
- settings read: 20;
- apply changes:
  - `residual.continuity`: `0.001` to `0.0011`;
  - `reference.area`: `1.0` to `1.05`;
  - `reference.density`: `1.225` to `1.28625`;
- all applied values read back exactly;
- original values restored;
- final state matched all initial values;
- adapter disconnected cleanly;
- no Fluent process remained.

Report: `docs/poc/reports/m6_fluent_adapter.json`

## Known Limitations

- M6 validates one Fluent 2025 R2 installation and one case file.
- Attach behavior is inherited from the M0 proof but is not re-run by the M6 validation script.
- The adapter is not yet exposed through the FastAPI routers or Renderer.
- Rollback is best-effort because Fluent does not provide a transaction across all setting nodes.

## Gate Decision

M6 is accepted. M7 may begin only after explicit approval.
