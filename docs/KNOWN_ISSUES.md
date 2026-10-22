# Known Issues and Current Boundaries

1. The renderer does not yet consume the M3 business API; router, Ant Design, Zustand, i18n, and business pages remain future work.
2. File selection and path validation are currently API-level only; native Electron file pickers arrive in M4.
3. Fluent operations are represented by the adapter contract and FakeFluentAdapter only. The real PyFluent adapter is not yet connected to business workflows.
4. Jobs are persisted but no background job worker or progress transport is implemented.
5. SQLite migration 1 is the only schema version. Future migrations must remain additive and immutable.
6. Database backup, restore, compaction, export, and corruption recovery are not implemented.
7. Packaged sidecar executable resolution and PyInstaller bundling are not implemented.
8. Sidecar logs are currently console-only and not persisted to rotating files.
9. Automatic restart is limited to two attempts per failure sequence.
10. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
11. PyFluent settings classes are version-specific. Production adapters must keep the Fluent 2025 R2 mapping explicit.
12. `read_case_data()` requires a matching data file; case-only loading must use `read_case()`.
13. Fluent connection properties include an ephemeral password and must never enter normal logs or committed reports.
14. M0 covers one Windows installation and one Fluent version only.
15. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
16. In restricted networks, the Electron runtime binary may require `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`.
17. Arbitrary Python/TUI command execution remains out of scope.
