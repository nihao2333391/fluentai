# Known Issues and Current Boundaries

1. The renderer still uses the M4 status page rather than the final four-module application shell. Full UI work begins in M5.
2. Model file selection is exposed through the typed service but is not yet presented in a complete model-management form.
3. Fluent credentials are encrypted and stored by Electron, but are not yet consumed by the sidecar or PyFluent connection flow.
4. Selection tokens are memory-only and become invalid after an application restart.
5. Model files are referenced in place and are not copied into an application-managed library directory.
6. File permission failures depend on Windows ACL behavior and are represented through structured IPC/API errors; no administrator-elevation workflow exists.
7. Fluent operations are represented by the adapter contract and FakeFluentAdapter only. The real PyFluent adapter is not yet connected to business workflows.
8. Jobs are persisted but no background job worker or progress transport is implemented.
9. Database backup, restore, compaction, export, and corruption recovery are not implemented.
10. Packaged sidecar executable resolution and PyInstaller bundling are not implemented.
11. Sidecar logs are currently console-only and not persisted to rotating files.
12. Automatic restart is limited to two attempts per failure sequence.
13. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
14. PyFluent settings classes are version-specific. Production adapters must keep the Fluent 2025 R2 mapping explicit.
15. `read_case_data()` requires a matching data file; case-only loading must use `read_case()`.
16. M0 covers one Windows installation and one Fluent version only.
17. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
18. Arbitrary Python/TUI command execution remains out of scope.
