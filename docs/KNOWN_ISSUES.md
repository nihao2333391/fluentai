# Known Issues and Current Boundaries

- PyFluent 0.42.1 raises `RecursionError` while extracting command arguments for `Identify Construction Surfaces` and `Create Local Refinement Regions`; these two FTM tasks remain explicitly unavailable until PyFluent is fixed or a reference-derived adapter is validated.

1. The Solver preset editor covers General, Models, Solution criteria, and Reference Values. The Meshing editor and apply engine now cover both approved workflows, nested arguments, named compound children, exact name checks, and readback verification.
2. Job execution remains synchronous at the HTTP caller. The UI polls persisted progress, and cancellation is cooperative between workflow stages; an atomic in-progress Fluent call cannot be interrupted.
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
13. The Windows installer bundles a standalone Python runtime and the current site-packages. PyInstaller or dependency pruning can reduce the roughly 300 MB sidecar payload in a later hardening pass.
14. Sidecar logs are currently console-only and not persisted to rotating files.
15. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
16. M0, M6, and M7 cover one Windows installation and Fluent 2025 R2 only.
17. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
18. Arbitrary Python/TUI command execution remains out of scope.
19. Meshing name validation can only use names exposed after geometry import; names that first appear after surface mesh generation are intentionally rejected under the no-mesh rule.
20. Direct `.dsco` import can block in standalone Fluent Meshing. Use the generated `.pmdb` or another verified native geometry format for Meshing apply.
21. The NSIS installer is not Authenticode-signed because no code-signing certificate is configured. Windows SmartScreen may show an unknown-publisher warning.
22. The Windows executable currently uses Electron's default application icon.
