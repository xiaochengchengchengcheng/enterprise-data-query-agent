# -*- coding: utf-8 -*-
"""Dependency-free MCP stdio tool server for Python 3.9 deployments."""

import json
import logging
import sys
from typing import Any, Dict

from advanced_agent_graph import advanced_data_analyst
from model_registry import model_registry
from rag_store import rag_store
from sql_agent_graph import run_agent

logger = logging.getLogger(__name__)


TOOLS = [
    {
        'name': 'nl2sql_query',
        'description': 'Convert a natural-language question to read-only SQL and return masked data.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'user_query': {'type': 'string'},
                'session_id': {'type': 'string'},
            },
            'required': ['user_query'],
        },
    },
    {
        'name': 'analysis_plan',
        'description': 'Create a RAG-enhanced analysis plan that requires human approval.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'user_query': {'type': 'string'},
                'session_id': {'type': 'string'},
                'chat_model': {'type': 'string'},
                'embedding_model': {'type': 'string'},
            },
            'required': ['user_query'],
        },
    },
    {
        'name': 'analysis_review',
        'description': 'Approve, reject, or revise a pending analysis plan.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'analysis_id': {'type': 'string'},
                'approved': {'type': 'boolean'},
                'feedback': {'type': 'string'},
            },
            'required': ['analysis_id', 'approved'],
        },
    },
    {
        'name': 'models_list',
        'description': 'List registered chat and embedding models.',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'rag_search',
        'description': 'Search business metadata and terminology in the local vector store.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string'},
                'top_k': {'type': 'integer', 'minimum': 1, 'maximum': 20},
                'namespace': {'type': 'string'},
                'embedding_model': {'type': 'string'},
            },
            'required': ['query'],
        },
    },
]


def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if name == 'nl2sql_query':
        return run_agent(arguments['user_query'], arguments.get('session_id', ''))
    if name == 'analysis_plan':
        return advanced_data_analyst.create_plan(
            arguments['user_query'],
            arguments.get('session_id'),
            arguments.get('chat_model'),
            arguments.get('embedding_model'),
        )
    if name == 'analysis_review':
        return advanced_data_analyst.review_plan(
            arguments['analysis_id'],
            bool(arguments['approved']),
            arguments.get('feedback', ''),
        )
    if name == 'models_list':
        return {'models': model_registry.list_models()}
    if name == 'rag_search':
        return {'results': rag_store.search(
            arguments['query'],
            int(arguments.get('top_k', 5)),
            arguments.get('namespace', 'business'),
            arguments.get('embedding_model'),
        )}
    raise KeyError('未知工具: ' + name)


def handle_message(message: Dict[str, Any]) -> Dict[str, Any]:
    request_id = message.get('id')
    method = message.get('method', '')
    params = message.get('params') or {}
    if method == 'initialize':
        return {
            'jsonrpc': '2.0',
            'id': request_id,
            'result': {
                'protocolVersion': params.get('protocolVersion', '2024-11-05'),
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': {'name': 'enterprise-data-analyst', 'version': '2.0.0'},
            },
        }
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': request_id, 'result': {}}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': request_id, 'result': {'tools': TOOLS}}
    if method == 'tools/call':
        try:
            value = _call_tool(params.get('name', ''), params.get('arguments') or {})
            return {
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'content': [{
                        'type': 'text',
                        'text': json.dumps(value, ensure_ascii=False, default=str),
                    }],
                    'isError': False,
                },
            }
        except Exception as exc:
            return {
                'jsonrpc': '2.0',
                'id': request_id,
                'result': {
                    'content': [{'type': 'text', 'text': str(exc)}],
                    'isError': True,
                },
            }
    return {
        'jsonrpc': '2.0',
        'id': request_id,
        'error': {'code': -32601, 'message': 'Method not found: ' + method},
    }


def run_stdio_server() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if 'id' not in message:
                continue
            response = handle_message(message)
        except Exception as exc:
            response = {
                'jsonrpc': '2.0',
                'id': None,
                'error': {'code': -32700, 'message': str(exc)},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    run_stdio_server()
