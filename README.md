# Fluent AI

> 面向 ANSYS Fluent Meshing 的 Windows 桌面自动化、七步工作流实时同步与同类模型批量处理工具。

> **评委 / 首次使用者请从这里开始。** 当前仓库提供源码与使用文档；GitHub Releases 暂无可下载的安装包。请按下方“开发”从源码启动。GitHub `zhuxu` 是本次评审快照；后续开发以 Gitee `develop` 为工作分支。

## 快速导航

| 你要做什么 | 阅读 / 操作 |
| --- | --- |
| 先了解项目、功能和当前状态 | 阅读本 README 的“当前能力”“当前状态”和“支持的主要格式” |
| 快速了解操作流程 | [Fluent AI 用户操作指南](docs/用户操作指南.md) |
| 了解评审阅读顺序和文档用途 | [文档目录与阅读顺序](docs/README.md) |
| 安装已构建的 Windows 应用 | 当前暂无公开安装包；请联系项目维护者获取，或按下方步骤从源码构建 |
| 从源码启动应用 | 按下方“开发”中的环境和启动步骤操作 |
| 构建 Windows 安装包 | 阅读[生产交付与部署指南](docs/生产交付与部署指南.md) |
| 查看已知限制和验证材料 | [已知问题](docs/KNOWN_ISSUES.md)、[验证记录](docs/verification/) |

### 评委建议阅读顺序

1. 本 README：项目定位、状态、环境要求和启动入口。
2. [用户操作指南](docs/用户操作指南.md)：了解应用的页面和实际操作流程。
3. [生产交付与部署指南](docs/生产交付与部署指南.md)：从源码安装依赖、启动、检查和打包。
4. [已知问题](docs/KNOWN_ISSUES.md)：了解当前限制。
5. [项目进度](docs/PROGRESS.md)与[验证记录](docs/verification/)：核对完成功能和测试证据。

### 当前交付状态

- 仓库包含项目源码、用户指南、构建脚本和验证记录。
- 当前没有随 GitHub 仓库公开的 `.exe` 安装包；`release/` 目录由 Git 忽略。
- 评审时可从源码启动：需要 Windows x64、Node.js 24+、pnpm 12.5.1+、Python 3.12+。真实 Fluent Meshing 功能需要 ANSYS Fluent 2025 R2 和有效许可证。
- 本次整理不代表新一轮构建或 Fluent 实机验收；请以每份验证记录中的日期和范围为准。

---

## 📘 完整使用指南

> **第一次使用、部署、排障或团队交接，请先阅读完整手册。**

| 文档                                | 入口                                                            |
| ----------------------------------- | --------------------------------------------------------------- |
| **Fluent AI 完整使用指南（推荐）**  | [docs/用户操作指南.md](docs/用户操作指南.md)                    |
| 快速排障：Fluent/Discovery/CAD 导入 | [查看故障排查章节](docs/用户操作指南.md#13-故障排查)            |
| 七步 Watertight 工作流              | [查看工作流章节](docs/用户操作指南.md#8-七步-watertight-工作流) |
| 应用自动化与实时同步                | [查看实时同步章节](docs/用户操作指南.md#9-应用自动化与实时同步) |
| 开发、测试与打包                    | [查看开发构建章节](docs/用户操作指南.md#14-更新卸载与开发构建)  |
| 团队协作说明                        | [CONTRIBUTING.md](CONTRIBUTING.md)                              |

完整手册覆盖：安装与校验、首次启动、Fluent/Meshing 连接、模型导入、自动化创建、七步工作流、双向同步、多模型批处理、数据备份、常见错误、CAD Reader 主机名修复、开发构建和交付验收。

---

## 当前能力

- **Meshing 自动化预设**：按 Fluent Meshing 真实任务树保存参数。
- **七步 Watertight 工作流**：导入几何、局部尺寸、表面网格、描述几何、更新区域、边界层、体网格。
- **实时双向同步**：Fluent AI 修改写入 Fluent，Fluent 原生界面修改可回读。
- **逐项回读验证**：写入后读取实际值，避免界面显示与 Fluent 状态不一致。
- **多模型批处理**：同一预设按模型队列依次应用。
- **模型库**：支持 Fluent 算例/网格与常见 CAD/几何格式。
- **原生命名保留**：`.scdoc/.scdocx/.dsco` 和 `.pmdb` 可保留 Meshing 命名选择。
- **中文/English 界面**：中文术语与 ANSYS 汉化版对齐，英文保持原版。
- **本地数据安全**：SQLite、每日自动备份、手动备份与安全恢复。
- **独立 Python Sidecar**：安装包自带 Python 3.12 与 PyFluent 运行环境。

## 技术架构

```text
React + TypeScript + Ant Design
            ↓ Electron IPC
Electron Main Process
            ├─ Sidecar supervision
            ├─ Native file picker
            ├─ User data / backups
            └─ Secure local storage
            ↓ 127.0.0.1 + bearer token
FastAPI Sidecar
            ├─ SQLite repositories
            ├─ Jobs and sync logs
            ├─ Serialized Fluent executor
            └─ PyFluent Meshing adapter
            ↓
ANSYS Fluent Meshing 2025 R2
```

## 当前状态

| 里程碑       | 状态        | 说明                                                                         |
| ------------ | ----------- | ---------------------------------------------------------------------------- |
| M0–M7        | PASSED      | Fluent 可行性、工程基础、IPC、数据库、安全文件、Fluent Adapter、首条纵向流程 |
| M8           | PASSED      | Watertight/Fault-tolerant schema、预设编辑、名称检查、写入回读               |
| M9           | PASSED      | 交付生命周期、Sidecar、NSIS 安装包与安装冒烟测试                             |
| M10          | IN PROGRESS | 产品加固、备份恢复、更多 Fluent 设置、签名准备                               |
| M11          | PASSED      | Meshing UI、连接诊断、参数直读直写、427 项实机回读                           |
| 实时 Meshing | PASSED      | 七步工作流执行、双向同步、模型队列、日志与状态反馈                           |

详细进度见 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 安装包

当前 Windows x64 安装包：

```text
FluentAI-0.1.0-x64-Setup.exe
```

SHA-256：

```text
03eda593d2c662149acf7fb5dfc799b67793bd9c50f6b9ffcf27ded449e65ec9
```

说明：

- 安装包不直接提交到 Git，避免大文件超过仓库限制。
- 当前构建尚未配置 Authenticode 证书，Windows SmartScreen 可能提示未知发布者。
- 安装前请核对 SHA-256，并从项目维护者提供的可信位置获取安装包。

## 30 秒启动

1. 启动 Fluent AI，等待 **FastAPI 侧车 · 已就绪**。
2. 打开 **设置 → Fluent Meshing 连接**。
3. 选择“启动新会话”，填写 `fluent.exe`，建议选择“显示 GUI”。
4. 保存并连接，运行“连接与读写诊断”。
5. 打开 **我的模型** 导入几何。
6. 打开 **网格划分自动化** 创建预设。
7. 点击预设的“应用”，选择模型并选择“应用并实时同步”。
8. 在七步页面逐项检查参数并执行当前步骤。

完整步骤：[docs/用户操作指南.md](docs/用户操作指南.md)。

## 支持的主要格式

**Fluent 算例/网格：**

```text
.cas  .cas.h5  .msh  .msh.h5
```

**CAD / 几何：**

```text
.scdoc  .scdocx  .dsco  .pmdb
.step   .stp     .stpz  .iges  .igs
.x_t    .x_b     .sat   .sab
.jt     .3dxml   .catpart  .catproduct
.sldprt .sldasm  .ipt   .iam   .prt  .asm
.par    .stl     .fmd   .tgf
```

推荐 Meshing 输入顺序：

1. `.pmdb`
2. 原生 `.scdoc/.scdocx/.dsco`
3. `.step/.stp`
4. 其它 B-Rep CAD 格式

STEP 可能丢失命名选择；Watertight 节点可能拒绝 faceted `.fmd/.tgf`。详见完整手册的格式兼容性章节。

## CAD 导入超时快速提示

若 Fluent 报告：

```text
Timeout reached, failed to start Discovery!
```

先检查 Windows 计算机名与 Python/DNS 主机名是否不同：

```powershell
Write-Output $env:COMPUTERNAME
[System.Net.Dns]::GetHostName()
```

不同名称会导致 Fluent 与 Discovery 查找不同的 `RunningCADs` 插件目录。完整修复脚本见：

- [完整指南：SCDOC/DSCO 导入超时](docs/用户操作指南.md#133-scdoc--scdocx--dsco-导入超时)

## 开发

### 环境

- Node.js 24+
- pnpm 12.5.1+
- Python 3.12+
- ANSYS Fluent 2025 R2

### 初始化

```powershell
pnpm install
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

### 开发与检查

```powershell
pnpm dev
pnpm check
```

### Windows 安装包

```powershell
pnpm package:win
```

构建流程包含：

- TypeScript 检查；
- Electron renderer/main/preload 构建；
- Python 3.12 sidecar 暂存；
- sidecar 启动与 HTTP 握手验证；
- NSIS 安装包；
- 静默安装；
- 安装版启动与 sidecar smoke test；
- SHA-256 和 release manifest。

## 仓库

Gitee：

```text
https://gitee.com/alcohol-free-beverage-station/fluent-ai-for-aic2026
```

协作流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 验证证据

- [项目进度](docs/PROGRESS.md)
- [已知问题](docs/KNOWN_ISSUES.md)
- [Meshing 实时验证](docs/poc/reports/meshing-live-check.json)
- [原生 SCDOC 导入验证](docs/poc/reports/meshing-live-start-acompact-native-junction.json)
- [Meshing 接口验证](docs/poc/reports/meshing-interface-check.json)
- [安装包冒烟测试](docs/poc/reports/installer-smoke.json)
- [Sidecar 打包验证](docs/poc/reports/packaging-sidecar.json)

## 许可与声明

本项目不是 ANSYS 官方产品。ANSYS、Fluent、Discovery、SpaceClaim 等名称和许可归 ANSYS, Inc. 所有。使用本应用前，请确认已获得相应 ANSYS 软件和许可。
