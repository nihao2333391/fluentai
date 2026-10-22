# M0 Fluent 2025 R2 Feasibility Report

- Status: **PASSED**
- Date: 2026-10-22
- Scope: launch, GUI launch, attach, case loading, settings read, write verification, restore, cleanup

## Environment

| Item              | Value                                                                 |
| ----------------- | --------------------------------------------------------------------- |
| Fluent            | Ansys Fluent 2025 R2                                                  |
| Fluent executable | `D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe`         |
| Python            | 3.12.14                                                               |
| Python executable | `D:\Fluent AI\.venvs\ansys-wwj\Scripts\python.exe`                    |
| PyFluent          | `ansys-fluent-core 0.42.1`                                            |
| Test case         | `D:\Fluent AI\ansys-runs\compat-smoke-20261021-170520\01_mesh.cas.h5` |
| Case size         | 1,875,448 bytes                                                       |

## Gate Results

| Test                             | Result | Evidence                                               |
| -------------------------------- | ------ | ------------------------------------------------------ |
| Environment and path check       | PASS   | `docs/poc/reports/env_check.json`                      |
| Headless launch and case load    | PASS   | `docs/poc/reports/launch.json`                         |
| Visible GUI launch and case load | PASS   | `docs/poc/reports/launch_gui.json`                     |
| Temporary session for attach     | PASS   | `docs/poc/reports/launch_hold.json`                    |
| Independent-process attach       | PASS   | `docs/poc/reports/attach.json`                         |
| Structured failure handling      | PASS   | `docs/poc/reports/attach_failure.json`                 |
| Cleanup after launch             | PASS   | No Fluent processes or temporary session file remained |

## Settings Read

All six settings were read successfully from the loaded case:

| Setting                       | Value     |
| ----------------------------- | --------- |
| Solver time                   | `steady`  |
| Viscous model                 | `k-omega` |
| K-omega model                 | `sst`     |
| Energy enabled                | `false`   |
| Continuity residual criterion | `0.001`   |
| X-velocity residual criterion | `0.001`   |

## Write Verification

Setting:

`settings.solution.monitor.residual.equations["continuity"].absolute_criteria`

Procedure:

1. Read original value: `0.001`
2. Write replacement: `0.0011`
3. Read back: `0.0011`
4. Restore original value: `0.001`
5. Read back after restore: `0.001`

Result: **write verified and restored**.

## Technical Findings

1. `session.settings.file.read_case(...)` works for a case-only `.cas.h5` file.
2. `read_case_data(...)` expects a corresponding `.dat.h5`; it failed for the mesh-only smoke case.
3. Settings writes must be applied to the parent settings object, for example:
   `equations["continuity"].absolute_criteria = value`.
   Capturing the child value object and rebinding a local Python variable does not write to Fluent.
4. `session.connection_properties` exposes `ip`, `port`, `password`, process IDs, and host information.
5. A second process successfully attached with the recorded IP, port, and password.
6. Launched sessions used `cleanup_on_exit=True` so `session.exit()` terminated the child process.
7. Attached sessions used `cleanup_on_exit=False` so attaching did not terminate the existing Fluent session.
8. `session.is_server_healthy()` is deprecated in PyFluent 0.42.1; `session.is_active()` is used instead.
9. Temporary passwords are kept only in the runtime session file and are deleted after testing. Committed reports are redacted.

## Limitations

- Only one local Fluent 2025 R2 installation was tested.
- Only six settings and one reversible write were covered.
- The test used one case-only mesh/case file, not a production case/data pair.
- Save and reopen verification is not part of M0.
- Attach was tested against a session launched by the same PyFluent environment.
- Cross-version compatibility, packaging, and Electron integration are not part of M0.
- The tests were executed on Windows only.

## Gate Decision

M0 is accepted. Proceed to M1 only after explicit approval.
