# Known Issues and Current Boundaries

- PyFluent 0.42.1 raises `RecursionError` while extracting command arguments for `Identify Construction Surfaces` and `Create Local Refinement Regions`; these two FTM tasks remain explicitly unavailable until PyFluent is fixed or a reference-derived adapter is validated.

1. The Solver preset editor covers General, Models, Solution criteria, and Reference Values. Meshing schema and persistence now exist, but the Meshing editor and apply engine are still pending.
2. Job execution is synchronous. Progress is persisted but not streamed in real time, and cancellation is not implemented.
3. Attach mode is supported by the adapter and settings but the M7 real workflow validation uses launch mode.
4. Fluent credentials are encrypted and stored by Electron, but are not yet consumed by the sidecar attach flow.
5. Model files are referenced in place and are not copied into an application-managed library directory.
6. Selection tokens are memory-only and become invalid after an application restart.
7. Recent-session restoration and richer sync-log filtering are not implemented.
8. Rollback is best-effort because Fluent does not provide a transaction across arbitrary setting nodes.
9. Only the curated 20-setting Fluent 2025 R2 catalog is supported.
10. Ant Design and icon modules produce an eager renderer bundle around 3.07 MB before gzip. Bundle optimization remains a hardening task.
11. Theme and language preferences persist locally, but authoritative synchronization with backend app settings is not implemented.
12. Database backup, restore, compaction, export, and corruption recovery are not implemented.
13. Packaged sidecar executable resolution and PyInstaller bundling are not implemented.
14. Sidecar logs are currently console-only and not persisted to rotating files.
15. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
16. M0, M6, and M7 cover one Windows installation and Fluent 2025 R2 only.
17. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
18. Arbitrary Python/TUI command execution remains out of scope.
