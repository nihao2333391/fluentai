# ADR 0005: Secure model file selection and credential storage

- Status: accepted
- Date: 2026-10-22

## Context

M3 exposed business persistence over authenticated HTTP, but the Renderer had no safe way to select model files or provide Fluent credentials. Allowing arbitrary paths or sending secrets through generic IPC would widen the desktop attack surface.

## Decision

### Model file selection

- The Renderer requests a file selection through preload IPC.
- The Electron main process opens a native dialog filtered to Fluent case and mesh types.
- The selected path is canonicalized with `realpathSync.native`.
- The path must resolve to a regular, non-empty file.
- The extension must be `.cas`, `.cas.h5`, `.msh`, or `.msh.h5`.
- The Renderer receives a random selection token and display metadata.
- Model create/update handlers resolve the token in main and substitute the canonical path before calling the sidecar.
- Selection tokens exist only in memory and expire when the app exits.

### Model metadata refresh

The sidecar re-stats the stored path and updates size, modification time, and timestamp. A missing or invalid file returns a structured API error.

### Credential storage

- Electron safeStorage async APIs are used.
- The plaintext password is accepted only from the Renderer credential form path.
- The password is encrypted before writing to disk.
- The encrypted file is stored under the app user-data directory.
- The Renderer never receives the stored password.
- The main process retains an internal read method for future Fluent connection work.

### Renderer boundary

- A typed service layer wraps all preload calls.
- Business operations do not call localhost directly.
- Paths and bearer tokens are not exposed to the Renderer.
- File selection tokens are not reusable across app restarts.

## Consequences

- Arbitrary renderer-supplied model paths are rejected by the create/update IPC contract.
- Secrets are protected by the operating-system-backed Electron credential provider.
- Future UI work can use a stable typed service layer.
- Credential migration and key-rotation handling remain future work.
