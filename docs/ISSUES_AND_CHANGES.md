# Software Issues and Changes

This log records user-visible problems, their diagnosis, code changes, and the evidence used to check each change. An entry stays open until the user-visible behavior is verified.

## 2026-10-27 — Show Update Boundaries for fluid-only geometry

### User-visible problem

- In the template editor, the user selects “The geometry consists of only fluid regions with no voids” in Describe Geometry.
- Fluent then exposes an Update Boundaries operation, but the platform only offered its fixed seven-step workflow and omitted that operation.
- Expected result: show an Update Boundaries step after Describe Geometry for this geometry type, allow boundary zone/type pairs to be saved, and include the task in the live workflow when applying that template.

### Diagnosis

- The Fluent schema includes a root `update_boundaries` task and its editable `boundary_zone_list` / `boundary_zone_type_list` arguments.
- The platform contract had a fixed seven-step list without Update Boundaries. The live manager also constructed its seven steps from a constant list.
- The template editor's generic panel did not make the two parallel lists understandable as paired boundary mappings.
- The screenshot shows the separate “Enclose Fluid Regions (Capping)” task. This change follows the user's confirmed scope and adds Update Boundaries only.

### Code changes

- `backend/app/meshing/workflow_schema.json` now describes Update Boundaries in the workflow order after Describe Geometry.
- `src/renderer/src/pages/MeshingAutomationCreatePage.tsx` conditionally shows the step when the selected geometry type is fluid-only, and provides a paired zone-name/boundary-type editor.
- `src/renderer/src/pages/MeshingLiveSyncPage.tsx`, `backend/app/services/meshing_live.py`, and `backend/app/domain.py` include the conditional step in the live execution sequence and allow its eighth step index.
- `backend/app/meshing/schema_index.py` validates matching list lengths, non-empty unique zone names, and Fluent's supported boundary types.
- The live step reads only the two editable boundary-mapping lists, keeping internal and read-only task fields out of its parameter panel.

### Verification and status

- `pnpm build` passed, including TypeScript checks and Electron renderer bundling.
- Targeted ESLint passed for the changed renderer files.
- Python syntax compilation passed for the changed backend modules; `workflow_schema.json` parsed successfully.
- Fluent's live task execution has not been exercised in this turn. Status: In progress pending a live Fluent check.

### Next step

- Build the updated app and verify the fluid-only selection reveals Update Boundaries, then confirm the saved mapping reaches the live Fluent step.

## 2026-10-27 — Template autosave resets local sizing and loses face-label choices

### User-visible problem

- The user reads six face labels from a reference model, switches to **Add Local Sizing**, and selects a label.
- Draft creation or autosave changes the page state. The workflow jumps back to geometry import, and the labels disappear from the selectable list even though the reference-label count remains visible.
- Expected result: autosaving the same template preserves the current step, child tasks, selected labels, and shared label catalog.

### Diagnosis

- The schema initialization effect depended on the saved template object. Autosave replaces that object in React state.
- For a new template, every object replacement ran the “new template” initialization branch again. That branch cleared the label catalog, selected values, and active step. The separate reference-label result state survived, which explains the mismatch between “six labels read” and an empty selector.
- The local-sizing schema also contains Fluent expressions such as `S_ActiveBOIGrowthRate(...)` and `$/GlobalSettings/...`. The renderer cannot evaluate those expressions. Its fallback kept unknown conditions visible, which allowed unrelated controls such as Bias Factor to appear.

### Code changes

- `src/renderer/src/pages/MeshingAutomationCreatePage.tsx` now keys initialization to template identity, workflow type, and explicit reload revision. Autosave updates to the same template no longer reinitialize the editor.
- `src/renderer/src/pages/meshingPreset.ts` now applies Fluent 25.2 local-sizing rules for size-type-specific controls, label/zone selection, and edge-only growth settings. The UI hides curvature/proximity controls in ordinary Face Size mode and hides Bias Factor unless Edge Size is available and selected with the matching growth method.
- `src/renderer/src/pages/MeshingAutomationCreatePage.test.tsx` and `src/renderer/src/pages/meshingPreset.test.ts` cover the autosave state transition and representative local-sizing modes.
- Research compared `docs/meshing/fluent-meshing-25.2-watertight.schema.json` with the installed `Meshing.fdl` at `D:\Program Files\ANSYS Inc252\v252\fluent\fluent25.2.0\cortex\resources\Meshing.fdl`. FDL expresses some choices dynamically through Fluent functions. The live Fluent window was minimized during research, so visual comparison against an open Fluent dialog remains pending.

### Verification and status

- `pnpm typecheck` passed after the visibility-rule correction.
- The focused `meshingPreset` test passed (1 passed, 4 skipped).
- The editor regression test reads five labels through the reference-model inspection API, creates the draft, selects a label in Local Sizing, waits for update autosave, and confirms the selected label and current step remain present (1 passed).
- The focused `meshingPreset` rule test passed (1 passed, 4 skipped).
- `pnpm typecheck` passed. Targeted ESLint completed without errors.
- `pnpm build` passed and generated the Electron main, preload, and renderer outputs.
- User-visible Fluent/platform verification remains pending. Status: In progress.

### Next step

- Confirm the reference-model label survives draft creation, step switching, and local-sizing autosave in the running desktop app.
- Compare the platform's default, Curvature, Proximity, and Edge Size controls with an open Fluent 2025 R2 dialog before expanding rules for Fluent-only dynamic options.

## 2026-10-27 — Sidecar cannot open its SQLite database

### User-visible problem

- The user starts the desktop application and sees the sidecar service reported as abnormal.
- Electron opens its window, then the Python sidecar exits while initializing SQLite with `OperationalError: unable to open database file` at `PRAGMA journal_mode = WAL`.
- Expected result: the sidecar creates or opens its database and reports `ready`.

### Diagnosis

- `backend/app/main.py` already resolves `FLUENT_AI_DATA_DIR` to `<directory>/fluent-ai.db`, and `SidecarManager` already passes its configured directory to the child process through that environment variable.
- `src/main/index.ts` always configured the sidecar database as `<app.getPath('userData')>/data`, so callers could not select a writable location through `FLUENT_AI_DATA_DIR`.
- In this launch environment, Windows denied the Electron process access to its default per-user application-data path. SQLite consequently could not create or open the database. This is an environment-specific access restriction; ordinary installed launches retain Electron's per-user data location by default.
- The first Electron launch was separately blocked because the Windows AppContainer could not read the Electron distribution folder under `node_modules`. Granting the AppContainer read/execute access to that specific `dist` folder allowed the desktop window to start. This was a local development-machine permission adjustment, not an application code change.

### Code or configuration changes

- `src/main/sidecar.ts` now resolves a non-empty `FLUENT_AI_DATA_DIR` override to an absolute path. When the override is empty or absent, it keeps `<userData>/data` as the default.
- `src/main/index.ts` passes the resolved directory into `SidecarManager`, which forwards it to the Python process.
- `src/main/sidecar.test.ts` covers both the explicit override and the default path.
- For this restricted development environment, launched the built app with `FLUENT_AI_DATA_DIR=<workspace>/.runtime/dev-data`; the database now stays in the ignored, writable `.runtime` directory.

### Verification and status

- `pnpm build` completed successfully after the fix.
- The focused path-selection tests passed: explicit override and default path (2 passed).
- Started the desktop app with `FLUENT_AI_DATA_DIR=<workspace>/.runtime/dev-data`. SQLite created `fluent-ai.db` in that directory.
- The live Electron window displays `FastAPI 侧车 · 已就绪`; the sidecar is serving requests.
- The sidecar subprocess integration tests time out when run inside the restricted test sandbox because Windows blocks its asyncio socket-pair setup. The desktop app was therefore verified in a normal process context, where the sidecar reached ready state.
- Status: Resolved for this launch environment. Ordinary installed launches continue using Electron's default user-data directory unless an override is set.

### Next step

- For restricted or portable development launches, set `FLUENT_AI_DATA_DIR` to a writable persistent directory before starting the app.

## 2026-10-26 — Fluent Meshing launch remains disconnected

### User-visible problem

- The user selects **Start a new session**, chooses a Fluent executable, and clicks **Connect**.
- A command window flashes and Fluent opens, while the platform still shows **Not connected**.
- The platform reports `Error invoking remote method 'meshing:connect': Error: Sidecar request failed: HTTP 500`.
- The user's installation is Fluent 2025 R2 at `D:\Program Files\ANSYS Inc252\v252\fluent\ntbin\win64\fluent.exe`.

### Diagnosis

- The **Fluent executable** field is the path used to start `fluent.exe`; it is not the host address. The **Host** field is the address PyFluent uses when attaching to an existing session. In **Start a new session** mode, the adapter launches Fluent locally and uses the generated server-info data for the handshake; the Host and Port fields are used by attach mode.
- The Electron renderer reaches the Python sidecar, but the Meshing launch call raises an exception before the adapter returns a connected session.
- A direct PyFluent reproduction raised `ValueError: Connecting to remote Fluent instances is not allowed`. This indicates that the generated server-info address was treated as remote, even though Fluent was launched locally.
- Instrumenting the handshake showed that Fluent wrote `192.168.1.101` into its server-info data, even when PyFluent's `launch_fluent_ip` and the inherited `REMOTING_SERVER_ADDRESS` were set to loopback.
- PyFluent rejects that non-loopback address with `allow_remote_host=False`. Enabling remote access would weaken the intended local-only connection, so the fix keeps remote access disabled.

### Code change attempted

- Fluent's documented `-host_ip` option and environment variables passed by PyFluent did not change the server-info address on this machine.
- Fluent's own `-setenv` startup arguments did: `-setenv="FLUENT_HOST_IP=-127.0.0.1" -setenv="REMOTING_SERVER_ADDRESS=127.0.0.1"` made the server-info address `localhost`.
- `backend/app/meshing/pyfluent_adapter.py` now passes those two `-setenv` arguments for local launch mode. Debug mode logs the executable path, version, UI mode, and launch/handshake exception.
- The UI's `127.0.0.1` Host value was appropriate for this same-machine setup; the executable path was also a separate, correctly purposed setting. The failure came from the address Fluent advertised during its startup handshake, not from confusing the executable path with the Host field.

### Verification and current status

- A live PyFluent launch using the two `-setenv` arguments connected successfully; the handshake reported `ip='localhost'` and `SESSION_CONNECTED True`.
- After the adapter change and development app restart, an isolated sidecar API request to `/api/meshing/connect` returned HTTP 200 with `connected: true`, Fluent 2025 R2, `host: localhost`, and an allocated port. A disconnect request then returned `connected: false`.
- Earlier platform retries before this change still returned HTTP 500 because Fluent advertised `192.168.1.101`.
- The main Electron window has not yet been verified to change its status to **Connected** after the successful sidecar check. The issue remains **in progress** until that user-visible state is confirmed.

### Next diagnostic step

- In the main Electron window, connect using the updated adapter and confirm that the UI shows **Connected**.
- Confirm that the Meshing read/write diagnostic can run before marking the issue resolved.

## 2026-10-28 — Connection button fails when mode-specific fields are unmounted

### User-visible problem

- The user selects **Start a new session**, keeps the Fluent executable path, and clicks **Connect**.
- The UI reports `Cannot read properties of undefined (reading 'trim')`; Fluent remains disconnected.
- Expected result: launch mode connects without needing Host or Port fields, which belong to attach mode.

### Diagnosis

- `FluentConnectionCard` renders Host and Port only in attach mode, and Fluent path only in launch mode.
- Ant Design `validateFields()` can omit fields whose `Form.Item` is not mounted. The form type claimed each field was always a string, but runtime values can be `undefined`.
- The Connect handler called `.trim()` directly on the mode-specific Port, so launch mode could fail before invoking the Electron/sidecar connection API. `MeshingConnectionCard` had the same unsafe pattern.
- This matches the screenshot toast and the observed disconnected status. The screenshot alone does not identify which card raised the toast; source inspection confirms the same failure path exists in both cards.

### Code changes

- `src/renderer/src/components/FluentConnectionCard.tsx` builds its config with null-safe field normalization. Launch mode ignores Port; attach mode parses it.
- `src/renderer/src/components/MeshingConnectionCard.tsx` applies the same safe handling, so switching its mode cannot trigger the same exception.
- `src/renderer/src/components/FluentConnectionCard.test.tsx` covers launch mode with omitted attach fields and attach mode with Host/Port values.

### Verification and status

- `pnpm typecheck` passed.
- Focused Fluent and Meshing connection tests passed: 3 tests total.
- `git diff --check` passed.
- Live Fluent connection from the desktop UI was not run in this turn. Status: fixed in code; desktop confirmation pending.

### Next step

- Restart the desktop app with the updated renderer and click **Connect** in launch mode. Confirm the toast is gone and the connection status changes to **Connected**.

## Entry template

### YYYY-MM-DD — Short issue title

#### User-visible problem

- What the user did:
- What the user saw:
- Expected result:
- Environment:

#### Diagnosis

- Evidence:
- Cause or current hypothesis:
- Remaining uncertainty:

#### Code or configuration changes

- Files changed:
- What changed and why:

#### Verification and status

- Checks run and results:
- User-visible verification:
- Status: Open / In progress / Resolved

#### Next step

-
