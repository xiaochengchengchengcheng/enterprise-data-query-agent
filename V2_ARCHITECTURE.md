# Enterprise AI Data Analyst v2.1 Architecture

## 1. Goals

V2 keeps the original read-only Text-to-SQL path and adds an auditable analysis workflow:

1. retrieve business metadata and terminology from the vector store;
2. generate a structured analysis plan;
3. pause for human approval or revision;
4. execute one to three read-only SQL tasks;
5. mask query results before model or Python processing;
6. optionally execute generated analytical Python in a restricted runtime;
7. synthesize conclusions and generate HTML/Markdown reports.

## 2. Components

| Component | Responsibility |
|---|---|
| `advanced_agent_graph.py` | LangGraph planning/execution orchestration and HITL state transitions |
| `sql_agent_graph.py` | Existing read-only Text-to-SQL graph; now returns masked rows to v2 |
| `model_registry.py` | LangChain-backed runtime-selectable chat and embedding providers |
| `rag_store.py` | SQLite persistence for embeddings, metadata and terminology |
| `python_executor.py` | AST validation plus Docker/explicit Local execution |
| `report_generator.py` | ECharts HTML and Markdown report generation |
| `api_key_manager.py` | PBKDF2-hashed keys, scopes, expiry and revocation |
| `conversation_store.py` | Multi-turn conversation and pending analysis task state |
| `mcp_server_v2.py` | FastMCP tools/resources with stdio transport and generated schemas |

## 3. State lifecycle

```text
new -> awaiting_approval -> running -> success
                        \-> failed
     -> revision_required -> awaiting_approval
```

`POST /api/v2/analyses/plan` only plans. It never runs SQL or Python. Execution begins only after `approved=true` is submitted to the review endpoint.

## 4. API overview

| Method | Path | Scope | Purpose |
|---|---|---|---|
| POST | `/api/v2/analyses/plan` | `analysis` | Create an analysis plan |
| POST | `/api/v2/analyses/{id}/review` | `analysis` | Revise or approve a plan |
| GET | `/api/v2/analyses/{id}` | `analysis` | Read task state and results |
| GET | `/api/v2/analyses/{id}/report/html` | `reports:read` | Read HTML/ECharts report |
| GET | `/api/v2/analyses/{id}/report/markdown` | `reports:read` | Read Markdown report |
| GET | `/api/v2/models` | `models:read` | List registered models |
| POST | `/api/v2/models` | `admin` | Register or replace a runtime model |
| POST | `/api/v2/rag/sync` | `rag:write` | Index live database schemas |
| POST | `/api/v2/rag/documents` | `rag:write` | Add business terms/documents |
| GET | `/api/v2/rag/search` | `rag:read` | Search vector context |
| POST/GET/DELETE | `/api/v2/api-keys` | `admin` | Manage API keys |

## 5. Python execution boundary

Docker is the default and recommended executor. The container runs:

- without a network;
- as a non-root user;
- with all Linux capabilities dropped;
- with a read-only root filesystem;
- with CPU, memory, PID and timeout limits;
- with only a temporary task directory mounted.

AST validation is defense in depth, not a standalone sandbox. Local execution is intentionally disabled unless `ALLOW_LOCAL_PYTHON_EXECUTION=true` is set. Do not enable Local mode for untrusted users.

## 6. RAG strategy

The default `local-hashing` embedding keeps development self-contained and stores vectors in SQLite. Production deployments should configure an OpenAI-compatible embedding endpoint. Re-index documents when changing the embedding model because vectors from different models are not comparable.

## 7. Persistence limitations

RAG documents and API keys are persisted in SQLite. Analysis tasks and conversation turns are currently in-memory with a 24-hour TTL; use Redis/PostgreSQL and a background task queue before multi-instance production deployment.
