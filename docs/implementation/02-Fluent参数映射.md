# Fluent AI｜Fluent 参数映射基线

**版本：V1 技术设计基线 0.1**  
**状态：逻辑映射已定；单位及运行映射须完成验证后方可作为执行契约**  
**核对对象：Fluent 2025 R2 Watertight Geometry、Add Boundary Layers**

## 1. 分层与所有权

数据按用途区分：工程输入、计算输入输出、工程推荐、Fluent 设置。工程输入和计算快照由工程参数服务管理；推荐由 Agent/推荐服务展示；Fluent 工作流参数由模板服务保存并交 Fluent 执行服务使用。

模板预设继续采用 `MeshingPresetDocument` 与 `MeshingPresetItem` 表示工作流步骤、参数路径、值、使用时输入标记及复合子项。Agent 推荐须提供结构化数据，用户核对后手动填写；V1 不增加推荐到模板的自动写入。

## 2. 边界层字段对应关系

| 用户可见项 | 内部 Fluent 字段路径 | 方法适用条件 | 推荐数据性质 | 单位/验证要求 |
|---|---|---|---|---|
| Offset Method Type | `add_boundary_layer.offset_method_type` | 有边界层子项时 | 用户选择或 Agent 推荐 | 枚举含 `uniform`、`smooth-transition`；代码映射已核对 |
| Number of Layers | `add_boundary_layer.number_of_layers` | 有边界层子项，且 Fluent 工作流条件允许 | Smooth Transition 理论层数推荐 | 整数；范围及实际生成行为须验证 |
| Growth Rate | `add_boundary_layer.rate` | 方法不是 `last-ratio` | 工程参考或用户设置 | 无量纲；不得与算法输出混为 Fluent 实际值 |
| First Height | `add_boundary_layer.first_height` | Uniform 或 `last-ratio` | Uniform 工程估算，可填写时由用户手动填写 | Fluent 预设当前为浮点型；数值单位待核验 |
| Transition Ratio | `add_boundary_layer.transition_ratio` | `smooth-transition` 或 `last-ratio` | 工程参考或用户设置 | 无量纲候选；范围、实际语义和适用性待核验 |
| Add in、Grow on、区域选择 | `add_boundary_layer` 下对应字段 | 取决于实际几何与区域 | 用户指定区域 | 保留现有几何标签和复合字段校验；不由算法猜测 |

参数路径及方法显示条件来自 `backend/app/meshing/workflow_schema.json` 和 `src/renderer/src/pages/meshingPreset.ts`。这些依据能证明预设 Schema 与前端过滤规则，不能单独证明 Fluent 实例接收并以预期单位解释该数值。

## 3. 工程输入与单位

工程参数以稳定的 `parameter_id` 表示，并记录值、原始文本、标准单位、展示单位、几何/流体 `region_id`、来源、确认状态、版本及时间。密度、动力黏度和速度必须关联对应区域；入口、喉部与侧支几何不得混用。

| 参数 | 建议标准单位 | 备注 |
|---|---|---|
| 长度、直径、壁距 | m | 保留用户原输入与 mm 等显示单位 |
| 速度 | m/s | 记录入口、喉部或目标区域 |
| 密度 | kg/m³ | 记录对应流体区域 |
| 动力黏度 | Pa·s | 记录对应流体区域 |
| y+、增长率、Transition Ratio | 无量纲 | 保留参数定义及推荐来源 |
| First Height | 内部计算以 m 表示 | 映射到 Fluent 前转换须由实机/接口验证 |

如果预设 Schema 当前不含单位定义，保留现有 JSON 形状，不把单位悄悄塞入未经版本化的参数值。单位转换单独由已测试的参数定义层负责；确认契约与 Fluent 对应关系后再决定持久化字段的升级方式。

## 4. 推荐工具输入输出

Uniform 首层高度工具输入至少包括目标区域、密度、动力黏度、特征速度、特征直径及目标首层中心 y+。输出包括 Reynolds 数、采用定义的摩擦系数、摩擦速度、首层中心距离、完整层高、公式、假设和适用性警告。工具返回值是工程估算，不等于已经验证的 Fluent 字段值。

Smooth Transition 层数工具输入至少包括首层中心 y+ 目标、覆盖设计终点、增长率和目标区域；输出理论层数、公式计算详情、输入假设和待验证事项。项目讨论所采用的 `y+ = 1`、覆盖目标 `y+ = 50`、增长率 `1.2` 属工程设计输入，不作为普遍定律，也不能保证 Fluent 实际生成层数和最终壁面 y+。

每次计算生成不可变输入快照，关联工具 ID 和版本、输入来源及单位。输入变化时保留旧结果并标记受影响结果过期；新一轮计算写入新结果。

## 5. 映射验证级别与门槛

- `unverified`：尚未对照实际 Schema 或 Fluent 行为。
- `code_verified`：确认参数路径、类型、条件与现有调用代码一致。
- `runtime_verified`：在目标 Fluent 版本中写入、回读并检查展示单位/数量级。
- `unsupported`：目标工作流或方法不接受此参数。

现状：前端方法条件与静态预设 Schema 可作代码依据；真实单位、界面显示、PyFluent 写入和读回数值仍须实机验证。映射未达到 `runtime_verified` 时，推荐卡片标记为工程估算或待验证，不标作可直接执行值。

运行验证步骤：连接 Fluent 2025 R2；读取 Add Boundary Layers 当前字段及单位；选定 Uniform 或 Smooth Transition；写入具有明显且安全差异的测试值；回读比较；验证切换方法后字段启用状态；记录字段路径、读写报告、单位换算和 Fluent 版本。不得在用户模型上执行未经确认的网格生成。

## 6. 一致性检查

自动检查覆盖：未知字段拒绝、类型拒绝、方法切换条件、复合区域字段、单位换算边界、计算工具缺参、参数版本变化引发旧推荐失效、推荐卡片显示来源与验证级别。Fluent 实机验收独立记录，模拟适配器测试不能代替实机证据。
