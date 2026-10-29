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
