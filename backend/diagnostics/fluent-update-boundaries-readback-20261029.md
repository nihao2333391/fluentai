# Fluent Update Boundaries readback trace

Date: 2026-10-29 (local desktop time)
Platform session: `3b9946c3-4c16-4ee0-9ae5-7fb23c2ef597`
Fluent window: `A-compact Fluent` (`3d, dp, single-process`)
Workflow: Watertight Geometry

## Evidence from the platform log

At 07:58:29, the platform submitted these target mappings:

| Boundary label | Requested type |
| --- | --- |
| `inlet-hot` | `wall` |
| `inlet-cold` | `wall` |
| `wall-big` | `outflow` |
| `wall-small` | `mass-flow-outlet` |
| `outlet` | `velocity-inlet` |

The task's captured pre-execution current table was:

```text
names: inlet-hot, inlet-cold, wall-big, wall-small, outlet
old types: velocity-inlet, velocity-inlet, wall, wall, pressure-outlet
current names: wall-small, wall-big, inlet-cold, outlet, inlet-hot
current types: wall, wall, velocity-inlet, pressure-outlet, velocity-inlet
```

Fluent printed `Boundary Conditions Updated`, and PyFluent returned `True`.
The platform then logged the same `boundary_current_type_list` before and after
execution and reported a mismatch against those old types.

## Evidence from the Fluent GUI

The live Fluent table for this same model showed:

| Boundary label | Displayed type |
| --- | --- |
| `inlet-cold` | `wall` |
| `inlet-hot` | `wall` |
| `outlet` | `velocity-inlet` |
| `wall-big` | `outflow` |
| `wall-small` | `mass-flow-outlet` |

This table matches the submitted mappings above. The platform's failure is a
false mismatch caused by the value source used for verification.

## Code path under investigation

`PyFluentMeshingAdapter.execute_task()` logged `task.arguments.get_state()` on
both sides of the Fluent command. `MeshingLiveService._execute_one_step()` then
called `_read_step()`, which reaches `PyFluentMeshingAdapter.read_arguments()`;
that method also used `get_state()` for the Update Boundaries table.

In installed PyFluent 0.42.1, `PyStateContainer.get_state()` reads its local
state cache when a cached value exists. `get_remote_state()` directly requests
state from Fluent. The unchanged before/after values and the GUI table support a
stale-cache diagnosis. A fresh remote-read result from the patched platform is
still required to confirm that the bypass returns the updated table in this
live workflow.

## Relevant captured messages

```text
07:58:28 info    正在准备 Fluent 步骤: update_boundaries
07:58:28 info    正在同步 Fluent 步骤: update_boundaries
07:58:29 success 已写入第 5 步的 3 项预设并回读。
07:58:29 success 参数同步完成，用时 1.0 秒。（耗时 1.0 秒）
07:58:29 info    ---------------- Boundary Conditions Updated
07:58:29 info    execute update_boundaries
07:58:29 info    Update Boundaries arguments before execution: {
                  'selection_type': 'label',
                  'boundary_label_list': ['inlet-hot', 'inlet-cold', 'wall-big', 'wall-small', 'outlet'],
                  'boundary_label_type_list': ['wall', 'wall', 'outflow', 'mass-flow-outlet', 'velocity-inlet'],
                  'old_boundary_label_list': ['inlet-hot', 'inlet-cold', 'wall-big', 'wall-small', 'outlet'],
                  'old_boundary_label_type_list': ['velocity-inlet', 'velocity-inlet', 'wall', 'wall', 'pressure-outlet'],
                  'boundary_current_list': ['wall-small', 'wall-big', 'inlet-cold', 'outlet', 'inlet-hot'],
                  'boundary_current_type_list': ['wall', 'wall', 'velocity-inlet', 'pressure-outlet', 'velocity-inlet']
                }
07:58:29 info    Update Boundaries state after execution:
                the values, including `boundary_current_type_list`, were unchanged.
07:58:29 info    True
07:58:30 error   Fluent 步骤“update_boundaries”执行失败（耗时 0.4 秒）：
                Fluent 更新边界后的实际类型与模板不一致：
                inlet-hot: 模板要求 wall，平台读到 velocity-inlet；
                inlet-cold: 模板要求 wall，平台读到 velocity-inlet；
                wall-big: 模板要求 outflow，平台读到 wall；
                wall-small: 模板要求 mass-flow-outlet，平台读到 wall；
                outlet: 模板要求 velocity-inlet，平台读到 pressure-outlet
```

## Follow-up after restarting the sidecar

The user then retried the template after restarting the sidecar. The platform
reported `update_boundaries 准备失败: One or more Meshing arguments failed to
write or verify.` The user's other screenshot showed a transient
`meshing-live:read-step` timeout and stated that the platform would retry the
read without resubmitting the write.

The write/verify error came from a timing distinction in the previous patch:
before `update_boundaries` executes, its new mapping is staged in the PyFluent
command arguments, while Fluent's live boundary table still contains the old
types. `write_arguments()` had switched this pre-execution check to
`get_remote_state()`, so it compared the staged template values with the old
live table and rejected them before the update task could run.

The follow-up change now verifies staged Update Boundaries arguments through
`get_state()` before execution, then keeps `get_remote_state()` for the live
boundary table after execution. The regression test models the same split:
staged values are updated locally while the remote table remains old until the
task runs. A real-platform rerun after this follow-up change is still required.

## Reproduction after the staged-state change

The user restarted the sidecar and retried `A-compact`. The platform again
reported `update_boundaries 准备失败: One or more Meshing arguments failed to
write or verify.` The separate `meshing-live:read-step` warning still reported a
timed-out current-step query and automatic retry.

The newest Fluent transcript (`fluent-20261029-082543-40868.trn`) records
surface-mesh completion and `Describe Geometry task complete`, followed by the
name-based automatic inlet/outlet classification. It contains no
`Boundary Conditions Updated` message. In this run, Fluent's boundary-update
command had not executed when the platform failed.

The code path is `retry_prepare()` -> `_prepare_volume()` -> `_prepare_step()`
-> `enter_step()` -> `_write_step()` -> `PyFluentMeshingAdapter.write_arguments()`.
The adapter returns a generic write/verify failure before `_execute_one_step()`
can call `update_boundaries`. The post-execution fresh-table comparison therefore
never runs. This reproduction places the failure before task execution; it does
not support attributing this run to Fluent overwriting a completed update.

PyFluent 0.42.1 source shows that `PyStateContainer.get_state()` reads its
service cache, and `set_state()` updates that cache from the service response.
The staged-state workaround still failed in the real workflow. The new code
therefore defers verification of Update Boundaries command arguments until the
task executes, then checks the live boundary table through the existing fresh
remote read and `_boundary_update_mismatch()` comparison. This avoids rejecting
the staged command on pre-execution state while preserving verification of the
actual requested boundary types.

Backend regression coverage passed (32 tests), including a check that an
unchanged Fluent boundary table is rejected after execution. The changed path
still requires a new real-Fluent run before it can be considered verified.

## Repeated live-status read collision

A later transcript started at 08:39:25, before commit `7f5acf3`. It records
geometry import and two local-sizing additions, then Fluent's TGrid process
ended before surface-mesh generation. Its tail first says `Shutting down
Server...`; the generated cleanup script sends `CLEANUP_EXITING` and then kills
the Fluent host and compute PIDs. The `BAD TERMINATION` report is consistent
with that process cleanup and does not prove that local sizing crashed TGrid.
This run does not test the deferred boundary verification change.

The UI refresh path calls `get_live_session()` and then `read_live_step()` in
the same two-second polling cycle. `get_live_session()` also started a native
`Workflow.CurrentTask` poll whenever the session was waiting. Both operations
use the same single-thread Fluent executor. If the task poll is still running,
`_run()` rejects the step read with `Fluent 当前步骤查询仍未返回`, matching the
warning in the user's screenshot.

The live session already records whether Fluent current-task and transcript
change subscriptions registered successfully. The service now uses those
events instead of starting redundant periodic task polls when either source is
available. If both subscriptions are unavailable, polling remains as a
fallback. The backend closure and adapter regression tests passed (33 tests).
The UI log now states which event subscriptions are available. A new platform
run is still needed to confirm both the poll warning and boundary mapping on
the user's Fluent session.

## Readback marked the live table unreadable instead of warning

Date: 2026-10-30

After the deferred-verification change, a real run failed with
`Fluent 未返回更新后的实际边界表，无法确认边界类型。` even though
`update_boundaries` had executed successfully. The failure came from
`_boundary_update_mismatch()` rather than the intended
"table unavailable" warning path. The gap was in
`PyFluentMeshingAdapter.read_arguments()`:

- The per-field remote reader (`_read_remote_argument`) was stored into the
  read state unconditionally. When PyFluent returns `None` (or a legacy
  Python-literal list string) instead of raising, the read item was marked
  `found` with a non-list value, so the read report "succeeded".
- The service's `boundary_table_unavailable` check only treats items with
  `found=False`/`error` as unavailable, so the mismatch check ran and failed
  on the missing list instead of warning.

Changes:

- `read_arguments()` now always reads Update Boundaries from a fresh remote
  snapshot (restoring the pre-execution behavior that the regression test
  `test_update_boundaries_read_arguments_bypasses_stale_pyfluent_cache`
  encodes), then overrides the dynamic table fields with per-field remote
  reads. A field is marked unreadable only when neither the per-field read
  nor the fresh snapshot yields a list, which routes the service to the
  warning path.
- `_read_remote_argument()` parses legacy Python-literal list strings
  (`"['wall', ...]"`) for `*_list` fields, reusing a new
  `_parse_list_literal()` helper also used by `_normalize_state()`.
- `_update_boundary_previous_state()` reads the initial selection/type state
  from one fresh remote snapshot, switches `selection_type` only when needed,
  and reuses that snapshot as its per-field fallback (no extra RPC).
- `MeshingLiveManager._write_step()` now uses the same staged read report as
  `_prepare_step()` for unverified Update Boundaries writes, so a manual write
  cannot fail on a pre-execution read of the dynamic table.

Regression coverage: three new adapter tests (string-literal parsing,
unreadable table marked not found, per-field failure falling back to the
snapshot) and one new closure test that executes `update_boundaries` with an
unreadable table and expects the step to complete with the
`未提供更新后的动态边界表` warning. Backend suite: 86 passed with two
pre-existing `test_meshing_api.py` failures that also fail at the commit
that authored them and are unrelated to boundaries. A real-Fluent rerun is
still required to confirm the warning path on the live session.

## Warning path contradicted by a preparation failure

Date: 2026-10-30 (08:06 local)

The real-Fluent rerun confirmed the warning path fired
(`update_boundaries 已由 Fluent 执行成功；当前会话未提供更新后的动态边界表`)
but the step still failed immediately with
`update_boundaries 准备失败: <the same warning text>`. Cause:
`_execute_one_step()` passed the deliberately tolerated failed read report to
`_step_report()`, which marks the report failed whenever
`read_report.status == "failed"`; `_prepare_step()` then called
`_preparation_failed()` with the warning message. The regression test missed
this because `FakeMeshingAdapter.read_arguments()` always reports
`status="success"` even for missing items, unlike the real adapter.

Fixes:

- `_execute_one_step()` no longer forwards the read report on the tolerated
  `boundary_table_unavailable` path, so the completed step reports success.
- The closure regression test's adapter now mirrors the real adapter for the
  dynamic boundary fields (missing boundary table fields make the read
  fail), reproducing the real run; the full preparation then reaches
  `volume_ready` with the warning intact.
