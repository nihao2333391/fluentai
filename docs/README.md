# Fluent AI 文档目录与评委阅读顺序

本页说明各文档的用途。评委或首次使用者建议按以下顺序阅读：

1. [项目首页 README](../README.md)：项目定位、当前交付状态、环境要求和启动入口。
2. [用户操作指南](用户操作指南.md)：应用页面、首次使用和 Meshing 流程。
3. [生产交付与部署指南](生产交付与部署指南.md)：源码准备、开发启动、检查和 Windows 安装包构建。
4. [已知问题](KNOWN_ISSUES.md)：当前能力边界和待处理问题。
5. [项目进度](PROGRESS.md)与[验证记录](verification/)：功能进度及对应验证范围。

## 各类读者从哪里开始

| 读者 | 建议入口 | 目的 |
| --- | --- | --- |
| 评委 / 体验者 | `README.md` → `用户操作指南.md` → `KNOWN_ISSUES.md` | 了解项目、运行条件和已知限制 |
| 从源码启动的人 | `README.md` → `生产交付与部署指南.md` | 安装依赖并启动开发版 |
| 构建安装包的人 | `生产交付与部署指南.md` | 构建、检查并交付 Windows 安装包 |
| 开发者 | `CONTRIBUTING.md` → `PROGRESS.md` → `adr/` | 了解协作、进度和架构决策 |

**安装包状态：** 当前仓库没有公开的 Windows `.exe` 安装包。`release/` 被 Git 忽略；在项目维护者发布安装包前，体验者需要按生产交付指南从源码构建。

## Project status

- `PROGRESS.md` - implemented milestones and current status
- `KNOWN_ISSUES.md` - known boundaries and unresolved risks
- `ISSUES_AND_CHANGES.md` - chronological user-reported issues, diagnoses, code changes, and verification status

## Architecture

- `adr/` - architecture decision records and milestone design decisions

## Verification

- `verification/` - milestone verification reports (M1-M10)
- `poc/` - real Fluent proof-of-concept records and machine-readable reports

## Fluent Meshing

- `meshing/FLUENT_MESHING_INTERFACE_PLAN.md` - connection, read/write, safety, and remaining work
- `meshing/meshing-workflow-inventory.md` - reference `.wbt`/`.wft` workflow inventory
- `meshing/fluent-meshing-25.2-watertight.schema.json` - enriched Watertight schema
- `meshing/fluent-meshing-25.2-fault-tolerant.schema.json` - enriched Fault-tolerant schema
- `meshing/ui-audit/MESHING_UI_FULL_AUDIT.md` - full FDL UI audit
- `meshing/ui-audit/Fluent_Meshing_UI_Audit_2025R2.xlsx` - filterable audit workbook
- `meshing/ui-audit/meshing-workflow-map.html` - interactive workflow map
- `meshing/ui-audit/meshing-ui-options.csv` - flattened option inventory

## Repository

评审快照位于 GitHub `zhuxu` 分支：

```text
https://github.com/nihao2333391/fluentai/tree/zhuxu
```

后续开发以 Gitee `develop` 分支为工作分支：

```text
https://gitee.com/alcohol-free-beverage-station/fluent-ai-for-aic2026/tree/develop
```
