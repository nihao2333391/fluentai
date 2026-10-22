# Known Issues and Current Boundaries

1. M2 does not yet expose SQLite, automation APIs, model APIs, or Fluent operations through the sidecar.
2. The Fluent M0 proof is not yet integrated into the application's Fluent gateway.
3. The renderer currently shows status and planned modules only; router, Ant Design, Zustand, i18n, and business flows remain future work.
4. Packaged sidecar executable resolution and PyInstaller bundling are not implemented.
5. Sidecar logs are currently console-only and not persisted to rotating files.
6. Automatic restart is limited to two attempts per failure sequence and does not display a full diagnostic report yet.
7. The per-launch bearer token is passed through the child process environment. It is not exposed to the renderer, but same-user process inspection remains part of the local threat model.
8. PyFluent settings classes are version-specific. Production adapters must keep the Fluent 2025 R2 mapping explicit.
9. `read_case_data()` requires a matching data file; case-only loading must use `read_case()`.
10. Fluent connection properties include an ephemeral password and must never enter normal logs or committed reports.
11. M0 covers one Windows installation and one Fluent version only.
12. FastAPI TestClient emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
13. In restricted networks, the Electron runtime binary may require `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`.
14. Arbitrary Python/TUI command execution remains out of scope.
