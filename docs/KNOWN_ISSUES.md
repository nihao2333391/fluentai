# Known Issues and Current Boundaries

1. The real PyFluent adapter is not yet exposed through FastAPI or the Renderer. M7 will connect it to authenticated routes and the first workflow.
2. Attach mode was validated in M0 but the M6 adapter validation script rechecks launch mode only.
3. Rollback is best-effort because Fluent does not provide a transaction across arbitrary setting nodes.
4. Only the curated 20-setting Fluent 2025 R2 catalog is supported. Other Fluent versions require a separate validated catalog/adapter.
5. Automation and model pages remain UI shells until the vertical-slice milestone.
6. Fluent credentials are encrypted and stored by Electron, but are not yet consumed by the sidecar or PyFluent connection flow.
7. Jobs are persisted but no background job worker or progress transport is implemented.
8. Ant Design and icon modules produce an eager renderer bundle around 2.36 MB before gzip. Bundle optimization remains a hardening task.
9. Theme and language preferences persist locally, but authoritative synchronization with backend app settings is not implemented.
10. Selection tokens are memory-only and become invalid after an application restart.
11. Model files are referenced in place and are not copied into an application-managed library directory.
12. Database backup, restore, compaction, export, and corruption recovery are not implemented.
13. Packaged sidecar executable resolution and PyInstaller bundling are not implemented.
14. Sidecar logs are currently console-only and not persisted to rotating files.
15. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
16. M0 and M6 cover one Windows installation and one Fluent version only.
17. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
18. Arbitrary Python/TUI command execution remains out of scope.
