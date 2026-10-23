# M4 Verification Record

- Date: 2026-10-22
- Status: **PASSED**

## Automated Verification

| Check                                | Result                        |
| ------------------------------------ | ----------------------------- |
| `pnpm lint`                          | PASS                          |
| `pnpm format:check`                  | PASS                          |
| `pnpm typecheck`                     | PASS                          |
| Vitest                               | PASS, 10 tests across 5 files |
| Electron production build            | PASS                          |
| Ruff                                 | PASS                          |
| Ruff format check                    | PASS                          |
| strict mypy                          | PASS, 33 source files         |
| FastAPI and repository pytest        | PASS, 16 tests                |
| M0 regression gate                   | PASS                          |
| Renderer authentication leakage scan | PASS                          |
| Unified command `pnpm check`         | PASS, `M4_CHECK_PASSED`       |

## File Handling Tests

- Valid `.cas.h5` file is canonicalized and registered.
- Selection token resolves only to the selected canonical file.
- Unsupported extensions are rejected.
- Empty files are rejected.
- Missing files are rejected.
- Directory paths are rejected.
- Unknown selection tokens are rejected.
- Model refresh updates file size and modification time.
- Missing model files return HTTP 400.

## Credential Tests

- Credential status starts unconfigured.
- Passwords are encrypted before writing.
- The stored file does not contain the plaintext password.
- Internal main-process read returns the original password.
- Clearing credentials removes the encrypted file.
- Storage is refused when encryption is unavailable.
- Existing passwords are not exposed through preload contracts.

## IPC and Renderer Tests

- Renderer service delegates automation calls through preload.
- Missing preload API produces a clear error.
- SidecarManager authenticated request proxy creates and persists an automation.
- Automation remains after sidecar restart.
- Business IPC registration is active in the running Electron app.
- Credential status IPC is called successfully by the Renderer.

## Real Electron Smoke Test

- Electron opened a responding window titled `Fluent AI`.
- Business IPC and sidecar startup completed without errors.
- Electron 45 async safeStorage API is used; no deprecation warning remains.
- Closing the window cleaned the sidecar process.
- No leftover Electron or Python processes remained.

## Known Test Warning

FastAPI TestClient emits a Starlette deprecation warning recommending `httpx2`. All tests pass; this should be revisited before a Starlette major upgrade.

## Gate Decision

M4 is accepted. M5 may begin only after explicit approval.
