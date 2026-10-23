# Fluent AI 与 ANSYS Fluent Meshing 接口可行性方案

## 1. 结论

Fluent AI 通过 pyFluent 与 ANSYS Fluent Meshing 建立连接、读取工作流参数、写入参数并回读验证的接口方案可行。

2025 R2 实机验证结果：

- 启动模式连接：通过。
- Watertight 工作流任务枚举：11 个。
- 全量参数枚举：427 项。
- 全量参数读取：427/427 成功。
- 直接写入并回读：通过。
- 导入参考几何后写入并回读：通过。
- 停止位置：`Generate the Surface Mesh` 和 `Generate the Volume Mesh` 之前。

附加连接模式能够建立 gRPC 连接并获得连接状态，但当前 PyFluent 0.42.1 对 Fluent 2025 R2 legacy Meshing workflow 的 attach 读取存在 `StringVector is not iterable` 限制，无法可靠读取任务参数。因此：

- 生产连接默认使用 `launch` 模式。
- `attach` 模式暂标记为“可连接、参数读写待 PyFluent 修复或改用 server-info/后续版本”。
- 不允许在 attach 参数读取失败时继续写入。

## 2. 已验证环境

- ANSYS Fluent：2025 R2 / 25.2.0
- Fluent 可执行文件：`D:\Ansys2025R2\ANSYS Inc\v252\fluent\ntbin\win64\fluent.exe`
- PyFluent：随项目 `.venv` 安装的版本
- 验证几何：`wenqiuli.dsco.pmdb`
- 验证报告：`docs\poc\reports\meshing-interface-check.json`

## 3. 总体架构

```text
Fluent AI Renderer
    |
    | Electron preload contextBridge
    v
Electron Main / IPC
    |
    | authenticated HTTP
    v
FastAPI Sidecar
    |
    v
MeshingService (single-worker executor)
    |
    v
PyFluentMeshingAdapter
    |
    | gRPC
    v
ANSYS Fluent Meshing Session
```

核心约束：

1. 所有 Meshing 会话操作串行化到同一个单线程执行器，避免并发读写同一工作流。
2. 读取、写入、预设应用共用同一个 workflow 缓存，避免重复初始化工作流。
3. 写入必须支持回读验证；写入值与实际值不一致时报告失败。
4. 任何自动化流程都不得执行生成表面网格或体网格的任务。
5. attach 模式读取失败时禁止写入。

## 4. 已实现接口

### 连接管理

- `GET /api/meshing/status`
- `POST /api/meshing/connect`
- `POST /api/meshing/disconnect`

连接配置复用 `FluentConnectionConfig`，支持：

- `launch` / `attach`
- Fluent 可执行文件
- host / port / password / server-info file
- `no_gui` / `gui`
- 启动超时、退出清理、处理器数量

### 直接读取

`POST /api/meshing/read`

请求：

```json
{
  "workflow_type": "watertight",
  "items": [
    {
      "task_path": ["import_geometry"],
      "argument_path": ["length_unit"],
      "compound_child_name": null
    }
  ]
}
```

当 `items` 为空时，读取当前工作流 Schema 中的全部叶子参数。

响应包含：

- 工作流任务名列表
- 每项参数是否存在
- 当前值
- 逐项错误

### 直接写入

`POST /api/meshing/write`

请求：

```json
{
  "workflow_type": "watertight",
  "verify": true,
  "items": [
    {
      "task_path": ["create_surface_mesh"],
      "argument_path": ["cfd_surface_mesh_controls", "max_size"],
      "compound_child_name": null,
      "value": 0.002,
      "required": true
    }
  ]
}
```

写入响应包含每项的：

- expected
- actual
- success
- message

写入操作同步记录到 `sync_logs`。

## 5. 实机验证数据

### 全量枚举与读取

```text
task_count = 11
item_count = 427
found_count = 427
errors = []
```

代表值：

```text
import_geometry.file_format = CAD
import_geometry.length_unit = mm
add_local_sizing.add_child = no
create_surface_mesh.cfd_surface_mesh_controls.min_size = 0.1
create_surface_mesh.cfd_surface_mesh_controls.max_size = 1.0
create_volume_mesh.volume_fill = polyhedra
```

### 直接写入回读

```text
import_geometry.length_unit: mm -> mm
status = success
actual = mm
```

### 导入几何后的写入回读

```text
import_geometry.length_unit = m
create_surface_mesh.cfd_surface_mesh_controls.min_size = 0.0005
create_surface_mesh.cfd_surface_mesh_controls.max_size = 0.002
```

三项均通过回读，未执行表面网格和体网格生成。

## 6. 用户界面

设置页新增 `Fluent Meshing 连接` 卡片，支持：

- 启动 / 附加模式
- Fluent 路径
- host / port
- 后台 / GUI 会话
- Watertight / Fault-tolerant 切换
- “连接与读写诊断”

诊断流程为：

1. 读取一组代表参数。
2. 选取一个已读取的值。
3. 将同一值写回并回读。
4. 展示任务数、读取项和写入验证项。

该测试不会改变当前参数语义。

## 7. 剩余工作

已完成：

1. 将 FDL 任务顺序、`displayText`、`members`/`arguments` 顺序和高级/开发者分组写入 Meshing Schema。
2. Meshing 表单已按增强后的 Schema 渲染原版显示名和技术参数路径。
3. 开发者字段默认隐藏，并提供显式开关。
4. 每个条件字段显示原始 `isActive` 条件，便于预设审核。

剩余工作：

1. 将 FDL `isActive` 表达式实现为完整的运行时条件求值器，做到字段随上游值实时显示/隐藏。
2. 为 Fault-tolerant 的两个 PyFluent 复合子任务限制增加明确的 UI 禁用状态。
3. 为 attach 模式增加 PyFluent 版本探测；不支持时只允许连接和状态查看，禁止读写。
4. 将“写入前快照”和“失败回滚”扩展到直接 Meshing 写入接口。

## 8. 验收标准

- 启动 Meshing 后状态显示已连接和 PID/端口。
- 能读取 Watertight 11 个任务和 427 项参数。
- 能写入指定嵌套参数并回读一致。
- 能导入同类几何后写入并回读。
- 写入过程不触发网格生成。
- attach 不支持时给出明确错误，不产生部分写入。
