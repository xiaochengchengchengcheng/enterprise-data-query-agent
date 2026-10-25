# Versioning and Git Workflow

本项目使用 [Semantic Versioning](https://semver.org/) 管理正式版本，版本格式为 `MAJOR.MINOR.PATCH`：

- `MAJOR`：存在不兼容的接口或架构变更。
- `MINOR`：向后兼容的新功能。
- `PATCH`：向后兼容的问题修复。

## 长期分支

- `main`：始终保持可发布状态，只接收经过验证的合并。
- `feature/<name>`：功能开发，例如 `feature/export-pdf`。
- `fix/<name>`：问题修复，例如 `fix/sql-parser`。
- `docs/<name>`：仅文档变更。
- `release/<version>`：需要集中稳定和验收时使用，例如 `release/2.1.0`。
- `hotfix/<name>`：从正式版本紧急修复生产问题。

短期分支完成并合并后应删除，避免长期分叉。维护旧大版本时，可从相应 Tag 创建 `support/v1` 等维护分支。

## 开发流程

1. 从最新 `main` 创建短期分支。
2. 使用 Conventional Commits 风格提交，例如 `feat: add PDF export`、`fix: reject unsafe SQL`。
3. 推送分支并创建 Pull Request。
4. 通过自动化测试和代码审查后合并到 `main`。
5. 删除已经合并的短期分支。

禁止直接向 `main` 推送未经验证的功能代码。单人维护时也建议使用 Pull Request，以保留清晰的评审和变更记录。

## 发布流程

1. 更新 `CHANGELOG.md` 和版本号。
2. 确认测试全部通过，工作区无未提交文件。
3. 合并发布变更到 `main`。
4. 创建带说明的 Git Tag，例如 `v2.1.0`。
5. 推送 Tag 并创建同名 GitHub Release。

已经发布的 Tag 不应移动或覆盖；需要修复时发布新的 PATCH 版本。

## 当前版本

| Tag | Commit | 说明 |
|-----|--------|------|
| `v1.0.0` | `bad83e6` | 基础 Text-to-SQL 自主取数智能体 |
| `v2.0.0` | `7a6c645` | 支持 RAG、HITL、Python 分析、ECharts 报告、模型调度、MCP 与 API Key 管理 |

查看任意旧版本：

```bash
git switch --detach v1.0.0
```

需要基于旧版本继续开发时，不要在 detached HEAD 上提交；应创建维护分支：

```bash
git switch -c support/v1 v1.0.0
```
