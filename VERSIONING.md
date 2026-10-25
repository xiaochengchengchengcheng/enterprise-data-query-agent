# V1 Maintenance Policy

本分支维护轻量 Text-to-SQL 产品线，不包含 V2 的 Python 深度分析、RAG、报告和 API Key 管理功能。

- `v1.0.0`：原始 Python 3.9 版本，永久保留。
- `v1.1.0`：Python 3.11 与 LangChain、LangGraph、FastAPI、FastMCP 现代框架栈版本。
- V1 后续修复从 `support/v1` 创建 `fix/*` 分支，通过 Pull Request 合并。
- `v1.x` 标签发布后不得移动或覆盖。
- V2 的开发和发布继续在 `main` 分支进行。
