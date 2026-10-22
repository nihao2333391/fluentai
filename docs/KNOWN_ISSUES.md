# Known Issues and Current Boundaries

1. Automation creation, automation list, and model list pages are M5 shells; real forms, tables, and business workflows arrive in later milestones.
2. Fluent credentials are encrypted and stored by Electron, but are not yet consumed by the sidecar or PyFluent connection flow.
3. Fluent operations are represented by the adapter contract and FakeFluentAdapter only. The real PyFluent adapter is not yet connected to business workflows.
4. Jobs are persisted but no background job worker or progress transport is implemented.
5. Ant Design and icon modules produce an eager renderer bundle around 2.36 MB before gzip. Route-level code splitting and bundle optimization should be addressed during hardening.
6. Theme and language preferences persist locally, but authoritative synchronization with backend app settings is not implemented yet.
7. Selection tokens are memory-only and become invalid after an application restart.
8. Model files are referenced in place and are not copied into an application-managed library directory.
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
