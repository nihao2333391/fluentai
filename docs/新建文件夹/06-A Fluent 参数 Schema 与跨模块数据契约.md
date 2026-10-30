# Fluent AI｜06-A Fluent 参数 Schema 与跨模块数据契约

**文档版本：V0.1**

**文档状态：统一字段设计草案，实际 Fluent API 映射待代码审查**

**关联文档：01、02-B、02-C、02-D、03、06**

---

## 1. 设计目标

建立一套统一、可追溯的工程参数管理机制。

需要解决四个问题：

1. 用户提供的几何尺寸和物理工况如何保存。
2. 计算工具如何获得可靠、完整的输入。
3. 计算结果如何转化为 Fluent 参数建议。
4. 如何确认建议值对应真实 Fluent 工作流中的正确字段。

V1 采用用户手动填写 Fluent 模板参数的方式。

参数推荐系统只负责计算、解释、校验和展示，不直接修改模板配置。

## 2. 参数体系分层

本项目将参数划分为四个层次。

| 层次 | 数据类型 | 典型示例 | 主要负责人 |
|---|---|---|---|
| A | 工程输入参数 | 直径、速度、密度、目标 y+ | 工程参数工作区 |
| B | 工具计算参数 | Re、Cf、摩擦速度、理论层数 | 计算工具服务 |
| C | 工程推荐参数 | 建议方法、首层高度、层数 | 推荐结果服务 |
| D | Fluent 设置参数 | Offset Method、First Height、Number of Layers | 模板与 Fluent 适配服务 |

各层使用明确的数据契约进行转换。

**不允许直接把模型生成的自然语言数值当成 Fluent 执行参数。**

---

## 3. 工程输入参数 Schema

### 3.1 设计原则

每个工程输入参数都应具有：

- 稳定的内部 ID。
- 明确的物理意义。
- 数据类型及单位。
- 对应几何或物理区域。
- 参数来源。
- 用户确认状态。
- 数据版本。

### 3.2 文丘里案例的基础参数表

| 内部参数 ID（拟定） | 物理意义 | 内部单位 |
|---|---|---|
| `geometry.main_inlet_diameter` | 主入口直径 | m |
| `geometry.throat_diameter` | 喉部直径 | m |
| `geometry.side_inlet_diameter` | 侧支入口直径 | m |
| `flow.main_inlet_velocity` | 主入口速度 | m/s |
| `flow.side_inlet_velocity` | 侧支入口速度 | m/s |
| `fluid.density` | 对应流体区域的密度 | kg/m³ |
| `fluid.dynamic_viscosity` | 对应流体区域的动力黏度 | Pa·s |
| `boundary_layer.first_yplus_target` | 第一层中心目标 y+ | 无量纲 |
| `boundary_layer.outer_yplus_target` | 设计覆盖终点 y+ | 无量纲 |
| `boundary_layer.growth_rate` | 层厚增长率 | 无量纲 |

以上 ID 是系统内部建议名称，并非 Fluent 原生字段。

其中密度、黏度、速度等可能随区域发生变化，因此实际记录还需要 `region_id`。

例如主入口水流和侧支流体应明确区分，不能默认共用一份物性数据。

### 3.3 参数状态

建议统一：

- `proposed`：已提取但尚未核实。
- `confirmed`：已确认，可参与计算。
- `invalid`：未通过校验。
- `superseded`：已被更新值替代。

工程参数服务负责状态维护，Agent 负责通过对话进行确认。

### 3.4 单位处理

后端计算使用统一标准单位，建议优先采用 SI。

例如：

用户输入：55 mm。

计算使用：0.055 m。

系统保留原始输入和展示单位，以方便用户核对。

---

## 4. 计算工具 Schema

### 4.1 统一工具接口规范

所有专业计算工具在接入前必须定义：

1. 工具 ID。
2. 工具版本。
3. 输入参数 Schema。
4. 输出参数 Schema。
5. 参数单位。
6. 必填条件。
7. 校验规则。
8. 算法及适用范围。
9. 异常类型。
10. 测试用例。

工具实际计算使用经过校验的结构化输入，而不是未经处理的自然语言文本。

### 4.2 Uniform First Height 工具

建议工具标识：

`boundary_layer.uniform_first_height`

输入：

| 字段 | 含义 | 单位 |
|---|---|---|
| `density` | 对应流体密度 | kg/m³ |
| `dynamic_viscosity` | 动力黏度 | Pa·s |
| `characteristic_velocity` | 目标区域特征速度 | m/s |
| `hydraulic_diameter` | 特征水力直径 | m |
| `target_first_yplus` | 第一层目标 y+ | 无量纲 |
| `target_region_id` | 计算目标区域 | ID |

计算结果：

| 字段 | 含义 | 单位 |
|---|---|---|
| `reynolds_number` | 雷诺数 | 无量纲 |
| `skin_friction_coefficient` | 采用约定定义的摩擦系数 | 无量纲 |
| `friction_velocity` | 摩擦速度 | m/s |
| `estimated_wall_distance` | 第一层中心壁面距离 | m |
| `estimated_first_height` | 第一层完整厚度估算值 | m |

同时返回计算假设、采用的相关经验公式以及适用性警告。

其中摩擦系数定义必须与现有算法保持一致，并检查适用范围。

特别注意：计算工具返回的是**工程估计的层高**。它能否直接填写到某个 Fluent 参数字段，需要再经过 D 层映射校验。

### 4.3 Smooth Transition Layers 工具

建议工具标识：

`boundary_layer.smooth_transition_layers`

输入：

| 字段 | 含义 |
|---|---|
| `first_yplus` | 第一层中心目标 y+ |
| `target_outer_yplus` | 设计覆盖终点 y+ |
| `growth_rate` | 层厚增长率 |

输出：

| 字段 | 含义 |
|---|---|
| `recommended_layers` | 理论推荐层数 |
| `coverage_target` | 采用的 y+ 覆盖设计目标 |
| `growth_rate_used` | 实际采用的增长率 |
| `calculation_details` | 计算细节 |
| `assumptions` | 计算假设 |

当前案例可以使用 y+ = 1、目标覆盖 y+ = 50、增长率 1.2，得到理论推荐层数 10。

**理论推荐层数不代表 Fluent 最终一定生成相同层数，也不保证生成后自动达到目标 y+ 分布。**

---

## 5. 工程推荐结果 Schema

计算结果与 Fluent 参数建议应分开。

建议定义 `EngineeringRecommendation`。

### 5.1 核心字段

| 字段 | 作用 |
|---|---|
| `recommendation_id` | 推荐结果 ID |
| `case_id` | 工程案例 ID |
| `template_id` | 所属模板 |
| `method` | 当前选择的边界层方法 |
| `input_snapshot_id` | 本次计算使用的输入快照 |
| `tool_id` | 使用的计算工具 |
| `tool_version` | 工具版本 |
| `calculated_values` | 工具实际计算结果 |
| `suggested_parameters` | 建议使用的工程设置 |
| `fluent_mapping_status` | Fluent 字段映射状态 |
| `assumptions` | 工程假设 |
| `verification_items` | 后续验证要求 |
| `status` | 当前、已过期或已被替代等状态 |

### 5.2 两条推荐分支

**Uniform：**

主要输出方法选择与 First Height 估算。

**Smooth Transition：**

主要输出方法选择与 Number of Layers 推荐。

Growth Rate、Transition Ratio 等其他参数，可以提供经过核实的参考设置，但需要明确区分：

- 算法直接计算结果。
- 工程经验参考值。
- 用户现有模板设置。
- 尚未确认的候选值。

### 5.3 推荐结果的持久化

每次计算绑定独立输入快照。

参数发生修改时，旧计算记录仍然保留。

如果修改会影响工具计算结果，对应推荐状态变为 `stale`。

需要重新计算时，生成新结果记录，而不是直接覆盖历史结果。

---

## 6. Fluent 参数 Schema

### 6.1 字段定义

建议建立统一的 `FluentParameterDefinition`。

每个参数至少包含：

| 字段 | 作用 |
|---|---|
| `parameter_id` | 系统内部字段 ID |
| `workflow_type` | Watertight / Fault-tolerant 等工作流类型 |
| `workflow_step_id` | 对应 Fluent 工作流步骤 |
| `display_name` | 前端显示名称 |
| `fluent_api_field` | 实际 Fluent/PyFluent 参数名 |
| `data_type` | 数据类型 |
| `canonical_unit` | 内部标准单位 |
| `display_unit` | 展示单位 |
| `applicable_methods` | 可用的网格设置方法 |
| `validation_rules` | 字段校验规则 |
| `schema_version` | 参数 Schema 版本 |
| `mapping_status` | 实际映射验证状态 |

必须由现有代码和 Fluent 实际运行环境确认 `fluent_api_field`。

### 6.2 边界层设置映射表

| 参数名称 | Uniform | Smooth Transition | 当前处理原则 |
|---|---|---|---|
| Offset Method | 可选 | 可选 | 作为方法推荐结果 |
| Number of Layers | 支持 | 支持 | Smooth 分支主要计算目标 |
| Growth Rate | 视实际工作流 | 视实际工作流 | 保留现有设置或经验证的参考值 |
| First Height | **待核对工作流** | 不直接采用该方法的计算结果填写 | Uniform 估算结果需核对真实映射 |
| Transition Ratio | 视实际工作流 | 支持相关控制 | 以实际字段定义为准 |
| Add in | 取决于模型区域 | 取决于模型区域 | 由用户当前几何区域决定 |
| Grow on | 取决于模型面标签 | 取决于模型面标签 | 复用已有选择与映射逻辑 |

上述“支持”属于功能概念层面的说明，具体字段和适用条件需要针对现有 Fluent 2025 R2 工作流核实。

### 6.3 工作流差异

不同 Fluent Meshing 工作流可能具有不同的参数名称、可用方法及启用条件。

因此不能只建立一份没有工作流类型的通用字段表。

应使用工作流类型和实际版本标识选择对应映射。

例如：

- Fluent 2025 R2。
- Watertight Geometry。
- Add Boundary Layers。

上述环境标识要在真实代码审查时确认。

### 6.4 参数映射验证状态

建议区分：

- `unverified`：尚未核对。
- `code_verified`：已确认现有项目存在对应参数处理。
- `runtime_verified`：已在实际 Fluent 工作流中验证。
- `unsupported`：当前工作流不支持。

只有满足当前方法适用条件，并具有足够映射依据的参数，才允许展示为“可直接填写”。

尚未完成验证时，仍可以展示工程估算结果，但必须明确标注 Fluent 字段待核实。

---

## 7. 数据转换流程

用户通过聊天提供工程信息后，按以下流程处理。

### 阶段 A：识别与确认

Agent 从消息、图片等来源提取候选参数。

后端校验参数类型、单位和区域归属。

存在歧义时，请求用户确认。

### 阶段 B：计算前校验

用户选择计算方法。

系统读取对应工具的 input_schema，检查必填参数。

完整且有效后生成 InputSnapshot。

### 阶段 C：工具计算

通过后端工具注册服务调用已有 Python 函数。

计算工具返回确定性的结构化结果。

### 阶段 D：工程推荐

推荐服务关联工具结果、工程依据和推荐方法。

生成对应的 EngineeringRecommendation。

### 阶段 E：Fluent 字段映射

根据 FluentParameterDefinition 查找当前工作流对应的设置参数。

检查：

- 真实字段是否存在。
- 参数是否适用于当前方法。
- 单位是否匹配。
- 数值是否符合实际参数约束。
- 映射是否通过验证。

### 阶段 F：前端展示

Agent 显示推荐卡片。

用户阅读计算依据、参数数值、单位及 Fluent 字段后，手动填写模板。

V1 不自动更新模板数据。

---

## 8. 模块之间的数据责任

| 模块 | 负责内容 |
|---|---|
| 工程参数工作区 | 工程输入的保存、确认与更新 |
| Agent Runtime | 自然语言交互、分析与调用请求 |
| 能力仓库 | 规则、知识、工具 Schema 与授权 |
| 工具执行服务 | 确定性计算和工具结果 |
| 推荐结果服务 | 参数建议及计算记录 |
| Fluent 参数 Schema 服务 | 真实工作流字段映射与校验 |
| 模板编辑器 | 显示和保存 Fluent 设置 |
| Fluent 执行服务 | 执行经过校验的模板参数 |

一个模块不应绕过上述责任边界直接修改其他模块的数据。

---

## 9. 异常与边界情况

至少处理以下场景：

1. 用户提供的尺寸缺少单位。
2. 图片识别结果存在歧义。
3. 相同参数出现互相冲突的数值。
4. 工况参数无法确定目标区域。
5. 计算工具输入不完整。
6. 输入超出经验公式适用范围。
7. 计算工具返回无效数值。
8. 推荐方法对应的 Fluent 参数不存在。
9. Fluent 参数存在但当前方法不可用。
10. 实际 Fluent 版本与参数映射版本不匹配。
11. 用户修改工程参数后，历史结果已过期。
12. 用户切换 Uniform / Smooth Transition 后，部分参数不再适用。

遇到参数无法可靠映射的情况，应保留工程计算结果并提示待验证，不应生成看似可以直接执行的错误设置。

---

## 10. Codex 代码审查与交接要求

本部分与其他模块统一交付 Codex。

开发前必须先检查：

1. 当前 Fluent Meshing 使用的工作流类型。
2. 当前 Fluent 与 PyFluent 的实际版本。
3. 已有模板参数表的真实字段定义。
4. 前端参数表单的显示与启用条件。
5. 参数存储格式及接口结构。
6. Python 调用 Fluent 时实际使用的字段名。
7. 现有边界层算法的输入输出及单位。
8. 工程参数工作区是否能够复用现有数据校验机制。

Codex 应先提交《Fluent 工作流参数与实际字段映射总表》。

此表至少需要包含：

- 前端字段。
- 后端字段。
- Fluent API 字段。
- 所属工作流。
- 适用方法。
- 数据类型。
- 单位。
- 默认值及来源。
- 校验规则。
- 对应代码位置。
- 实际验证状态。

该表是后续 Agent 推荐、工具注册及 Fluent 参数执行适配的共同依据。

## 11. V1 验收标准

1. 工程输入参数具有统一的数据定义。
2. 输入参数能够记录区域、单位和来源。
3. 计算工具具有明确的输入输出 Schema。
4. 计算结果关联不可变输入快照。
5. 参数变化后能够识别旧计算结果的有效性。
6. 推荐结果与工具结果能够分别保存。
7. Uniform 与 Smooth Transition 分支参数互不混淆。
8. Fluent 字段映射具有工作流与版本信息。
9. 参数推荐不会绕过实际 Fluent 字段验证。
10. 用户可以根据已验证的推荐参数手动填写模板。
11. 各模块复用同一套参数定义，避免重复维护。

**文档状态：V0.1。当前字段属于统一逻辑设计，真实 Fluent API 字段及默认值待代码审查后完善。**