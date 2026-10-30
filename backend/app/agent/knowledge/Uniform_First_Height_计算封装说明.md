# Uniform 边界层首层高度（First Height）计算算法 · v1.0

> **用途**：面向 Fluent Meshing 的 `Add Boundary Layers → Offset Method Type = uniform`，根据目标 `y⁺` 和流体工况估算应填写的 `First Height [mm]`。供文丘里管 k–ω SST、恒定物性水的初始网格设计使用。  
> **输出性质**：工程初始估算值，非 Fluent 已验证的真实壁面 `y⁺`，也不自动证明该网格最优。  
> **关系**：本模块与已有的“基于无量纲覆盖范围的层数推荐算法”互相独立；前者决定 **首层多厚**，后者在给定工程经验覆盖目标时决定 **铺多少层**。

## 0｜一分钟看懂

- 你的文丘里管内部有固体管壁。从**管内壁向内部流体方向**长出的第一层棱柱网格，其完整厚度就是 Fluent 的 `First Height`。
- 采用 k–ω SST、希望解析黏性底层时，工程师可以把第一层**网格中心**的目标设为 `y₁⁺ = 1`；这是设计目标，不是 Fluent 的强制输入。
- 计算器中的 `y = y₁⁺·μ/(ρ·uτ)` 是**壁面到第一单元中心距离**，不是完整网格厚度。若首层近似正交且中心位于厚度中点，则 `First Height ≈ 2y`。
- `uτ` 不是入口速度，通常需要从摩擦系数与壁面剪切应力进行估算，所以我们需要**水的密度、黏度、局部代表速度与管道特征直径**。
- **当前示例结果**：按水 `ρ = 998.2 kg/m³`、`μ = 0.001003 Pa·s`、喉部 `U ≈ 20 m/s`、`D = 50 mm`、目标 `y₁⁺ = 1`，计算得到 **`First Height ≈ 0.002841 mm`**，可在 Fluent `First Height [mm]` 中填写约 `0.00284`。

## 1｜计算结果到底控制什么？

| 项目 | 含义 | 由谁决定 |
|---|---|---|
| `y₁⁺` | 第一层单元中心的无量纲壁面距离 | 工程师选择设计目标，如 1 |
| `y` | 管内壁到第一层单元中心的物理距离 | 公式计算，单位 m |
| `First Height (h₁)` | 贴管壁第一层棱柱网格的完整厚度 | `h₁ ≈ 2y`，写入 Fluent |
| `Number of Layers (N)` | 最多生成多少层 | **由另一套层数算法**给出，本例暂取 10 |
| `Growth Rate (r)` | 相邻层厚度增长比例 | 工程师预设，本例 1.2 |

物理背景：`y⁺ = ρ·uτ·y/μ`，其中 `uτ = √(τw/ρ)`，`τw` 为壁面剪切应力。管壁附近存在黏性底层（典型 `y⁺≈0–5`）、缓冲层（约 `5–30`）、对数层（通常从约 `30` 开始）。First Height 计算只针对首层中心，**与“把棱柱层覆盖至外侧 `y⁺=50`”不是同一个计算**。

## 2｜计算链与公式（可单独复算）

**输入**：密度 `ρ [kg/m³]`、动力黏度 `μ [Pa·s]`、局部代表速度 `U [m/s]`、水力直径 `D [m]`、目标 `y₁⁺`。

**步骤 A：** 估算雷诺数

`Re = ρ U D / μ`

**步骤 B：** 估算摩擦系数。Ansys 近壁面第一层高度知识条目给出的内部流动经验关系为

`Cf = 0.079 × Re^(−0.25)`

使用其定义的壁面剪切关系：

`τw = 0.5 × Cf × ρ × U²`

**步骤 C：** 计算摩擦速度

`uτ = √(τw/ρ) = U × √(Cf/2)`

**步骤 D：** 计算中心距离与 First Height

`y = y₁⁺ × μ/(ρ×uτ)`  （m）

`h₁ = 2y`  （m，假设第一层近似正交且单元中心位于层厚的一半处）

`First Height [mm] = 1000 × h₁ [m]`

> **注意**：上述摩擦系数是预估。文丘里管收缩段、喉部、侧管交汇与扩张段都可能存在非充分发展和分离流动，实际壁面剪切应力应在 Fluent 求解后检查。当前 `Re≈9.95×10⁵` 较高，使用该简化摩擦关系有外推的不确定性；代码另支持 `haaland_darcy` 作为可选对照估算，而不是宣称某个公式精确预测喉部局部壁面摩擦。

## 3｜文丘里管案例：具体输入从哪里来

| 输入 | 当前示例 | 获取方式 | 分类 |
|---|---:|---|---|
| 主入口直径 `D_in` | 100 mm | CAD/尺寸图 | 几何已知 |
| 喉部直径 `D_t` | 50 mm | CAD/尺寸图 | 几何已知 |
| 主入口流速 `U_in` | 5 m/s | Fluent 边界条件 | 工况已知 |
| 喉部代表速度 `U` | ≈20 m/s | **近似**：`U_in (D_in/D_t)²`，忽略侧口流量；也可人工输入局部测速/仿真结果 | 算法预估或人工提供 |
| 水密度 `ρ` | 998.2 kg/m³ | Fluent Materials | **示例假设；需要核对实际值** |
| 动力黏度 `μ` | 0.001003 Pa·s | Fluent Materials | **示例假设；需要核对实际值** |
| 首层中心目标 `y₁⁺` | 1 | 工程师选择（低 y⁺ 的 SST 设计目标） | 人工预设 |
| 摩擦模型 | `ansys_internal_cf` | Ansys 官方示例关系；可切换 `haaland_darcy` | 工程师选择 |

本例代入：

- `Re ≈ 995,214`
- `Cf ≈ 0.0025012`
- `uτ ≈ 0.707276 m/s`
- `y ≈ 0.00142067 mm`（中心到壁面）
- **`First Height ≈ 0.00284135 mm`**（完整首层厚度）

与用户发来的 Fluent 截图默认 `First Height = 0.7 mm` 对比，推荐的是一个**基于目标 y⁺ 的首轮候选值**，并不意味着更小的高度就必然带来更高的最小正交质量。

## 4｜与你已有的层数推荐算法合并

已有层数规则：工程师设 `y₁⁺=1`、外侧**经验覆盖目标** `y_target⁺=50`、增长率 `r=1.2`，理想几何增长假设下：

`N = ceil( ln(1 + (r−1)·y_target⁺/(2 y₁⁺)) / ln(r) ) = 10`。

**这里的 50 是项目中可修改的经验目标，不是内部流动的真实“外边界”，也不是 SST 强制阈值。** 它用于确定候选层数，不用于独立求解 First Height。

合并后的 Uniform 面板填写：

| Fluent → Add Boundary Layers | 该示例填写 | 依据 |
|---|---:|---|
| `Offset Method Type` | `uniform` | 工程师选择 |
| `Number of Layers` | `10` | 理想覆盖范围规则（候选） |
| `Growth Rate` | `1.2` | 工程经验预设 |
| **`First Height [mm]`** | **`0.00284`** | **本计算器计算** |
| `Add in` | `fluid-regions` | 项目现有设置 |
| `Grow on` | `only-walls` | 项目现有设置 |

**关键区别**：Smooth Transition 方法没有直接输入 `First Height` 的同等控制方式；它依据局部实际面网格和过渡参数自动决定首层高度。本计算器输出的 First Height 应直接用于 **Uniform** 的候选设置，不应宣称它已经被 Smooth Transition 实际执行。

## 5｜同一模型族 A/B/C，为什么 First Height 会不同

沿用相同的恒定水物性、主入口 5 m/s 和 `D_in/D_t=2` 的假设，三个模型的喉部代表速度都估算为 20 m/s；然而喉部直径改变，`Re` 与摩擦估算仍略有不同。

| 模型 | 喉部直径 | 估算 First Height [mm] | 层数算法结果 |
|---|---:|---:|---:|
| A 紧凑 | 45 mm | 0.002804 | 10 |
| B 中等 | 55 mm | 0.002875 | 10 |
| C 长流程 | 62.5 mm | 0.002922 | 10 |

层数相同是因为层数算法使用相同的**无量纲经验设计目标**；First Height 不同来自工况/物性/特征尺寸。上述结果均为初始估算。

## 6｜接入与验证

### 运行

```bash
python uniform_first_height.py uniform_first_height_config.json
```

配置文件允许选择：

- `velocity_estimate.mode = "continuity_throat"`：从入口速度、入口直径、喉部直径计算代表速度（忽略侧口）；
- `velocity_estimate.mode = "given"`：工程师直接提供局部代表速度；
- `design.target_first_cell_y_plus`：默认 1；
- `design.friction_model`：`ansys_internal_cf` 或 `haaland_darcy`；
- `flow.density_kg_m3` / `dynamic_viscosity_pa_s`：须用实际 Fluent Materials 值替换；
- `number_of_layers`：来自独立层数模块，示例为 10。

程序输出 `recommended_first_height_mm`、雷诺数、估算剪切应力/摩擦速度和 `fluent_candidate_settings`，**不会自动调用 Fluent**。所有计算都采用 SI 单位，向 Fluent UI 显示时才换算为 mm。

### 验证顺序

`参数输入 → 计算 First Height → Uniform 划分网格 → 检查生成层数/正交质量/偏斜度 → SST 求解 → 在喉部与侧管内壁查看 Wall Yplus → 必要时调整 First Height。`

若求解得到的关键区域 `y⁺` 与目标存在偏差，可用 `h_new ≈ h_old × (y_target⁺/y_measured⁺)` 作为一次性局部修正的启发式估算（假定壁面剪切变化不大），随后必须重新生成网格和求解。此近似不是通用误差收敛保证。

## 7｜依据与适用边界

- Ansys Innovation Space, *How to estimate the first cell height (y) from desired y+*：https://innovationspace.ansys.com/knowledge/forums/topic/how-to-estimate-the-first-cell-height-y-for-the-mesh-from-the-desired-value-of-y-plus-y/
- Ansys Fluent Meshing 2025 R2, *Adding Boundary Layers*：https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/flu_ug/tgd_user_workflow_guided_tasks_ftm_add_boundary_layer.html
- Ansys Fluent Meshing 2025 R2, *Uniform offset method / First Height*：https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/fluent_beta_doc/ch36s10.html

**状态声明**：本算法是可复算的候选参数计算器；不单独解决真实壁面摩擦、真实层数和网格无关性，也不会证明 10 层或某个 First Height 是唯一最优。
