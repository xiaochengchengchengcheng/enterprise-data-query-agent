# -*- coding: utf-8 -*-
"""FastMCP server exposing the enterprise data analyst capabilities."""

import logging
from typing import Any, Dict, Optional

from fastmcp import FastMCP

from advanced_agent_graph import advanced_data_analyst
from model_registry import model_registry
from rag_store import rag_store
from sql_agent_graph import run_agent

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name='enterprise-data-analyst',
    instructions=(
        '企业内网智能数据分析服务。仅执行只读 SQL，返回结果已脱敏；'
        '深度分析计划必须先由用户确认。'
    ),
    version='2.1.0',
)


@mcp.tool
def nl2sql_query(user_query: str, session_id: str = '') -> Dict[str, Any]:
    """Convert a natural-language question to read-only SQL and return masked data."""
    return run_agent(user_query, session_id)


@mcp.tool
def analysis_plan(
    user_query: str,
    session_id: Optional[str] = None,
    chat_model: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a RAG-enhanced analysis plan that requires human approval."""
    return advanced_data_analyst.create_plan(
        user_query,
        session_id,
        chat_model,
        embedding_model,
    )


@mcp.tool
def analysis_review(
    analysis_id: str,
    approved: bool,
    feedback: str = '',
) -> Dict[str, Any]:
    """Approve, reject, or revise a pending analysis plan."""
    return advanced_data_analyst.review_plan(analysis_id, approved, feedback)


@mcp.tool
def models_list() -> Dict[str, Any]:
    """List registered chat and embedding models without exposing credentials."""
    return {'models': model_registry.list_models()}


@mcp.tool
def rag_search(
    query: str,
    top_k: int = 5,
    namespace: str = 'business',
    embedding_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Search business metadata and terminology in the local vector store."""
    if top_k < 1 or top_k > 20:
        raise ValueError('top_k 必须在 1 到 20 之间')
    return {
        'results': rag_store.search(
            query,
            top_k,
            namespace,
            embedding_model,
        )
    }


@mcp.resource('analyst://models')
def registered_models() -> Dict[str, Any]:
    """Return the public model registry as an MCP resource."""
    return {'models': model_registry.list_models()}


def run_stdio_server() -> None:
    """Run the FastMCP server over stdio for local MCP clients."""
    logging.basicConfig(level=logging.WARNING)
    mcp.run(transport='stdio')


if __name__ == '__main__':
    run_stdio_server()
