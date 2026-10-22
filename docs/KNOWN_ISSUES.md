# Known Issues and Current Boundaries

1. M1 does not yet launch, monitor, authenticate, or stop the FastAPI sidecar from Electron.
2. The renderer only displays the four planned modules; router, Ant Design, Zustand, i18n, and business flows are not implemented.
3. SQLite and all automation/model APIs are not implemented.
4. PyFluent settings classes are version-specific. Production adapters must keep the Fluent 2025 R2 mapping explicit.
5. `read_case_data()` requires a matching data file; case-only loading must use `read_case()`.
6. Settings writes must be applied through the parent settings object rather than by rebinding a captured child value object.
7. Fluent connection properties include an ephemeral password and must never enter normal logs or committed reports.
8. M0 covers one Windows installation and one Fluent version only.
9. FastAPI TestClient currently emits a Starlette deprecation warning about `httpx`; tests pass, but the HTTP test dependency should be revisited before upgrading Starlette.
10. In restricted networks, the Electron runtime binary may require `ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/`.
11. Arbitrary Python/TUI command execution remains out of scope.
