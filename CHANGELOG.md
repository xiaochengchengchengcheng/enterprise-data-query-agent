# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)，所有正式版本均通过 Git Tag 和 GitHub Release 发布。

## 2.0.0 - 2026-10-25

### Added

- Human-approved analysis plans with revision feedback.
- Multi-dataset StateGraph execution workflow.
- Docker/Local Python analysis executor with AST and resource controls.
- HTML/Markdown report generation with ECharts configurations.
- Persistent SQLite vector store and business metadata indexing.
- Runtime chat and embedding model registry.
- Python 3.9-compatible MCP stdio tool server.
- Scoped API keys with expiry and revocation.
- Multi-turn conversation context and v2 Streamlit workflow.

### Changed

- The legacy Text-to-SQL response now exposes only masked result rows to internal/v2 consumers.
- API and health version updated to `2.0.0`.
- Project identity updated to Enterprise AI Data Analyst.

### Compatibility

- Existing `/api/query` clients remain supported.
- API Key enforcement stays disabled by default until explicitly configured.

## 1.0.0 - 2026-10-13

### Added

- LangGraph-based Text-to-SQL agent workflow.
- MySQL metadata discovery and read-only query execution.
- FastAPI backend and Streamlit user interface.
- Sensitive-data masking, SQL validation, IP allowlist and audit logging.
- OpenAI-compatible LLM gateway and multi-turn query support.
