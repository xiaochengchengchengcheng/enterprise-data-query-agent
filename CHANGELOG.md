# Changelog

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
