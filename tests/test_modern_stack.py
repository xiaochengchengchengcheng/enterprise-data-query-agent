import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastmcp import Client
from langchain_openai import ChatOpenAI

from db_mcp_server import create_mcp_server
from fastapi_server import app
from llm_gateway import LLMGateway
from sql_agent_graph import build_agent_graph


class ModernStackTest(unittest.IsolatedAsyncioTestCase):
    def test_langgraph_compiles(self):
        self.assertEqual(type(build_agent_graph()).__name__, 'CompiledStateGraph')

    def test_langchain_gateway_uses_chat_openai(self):
        with patch.dict(os.environ, {
            'LLM_API_BASE': 'http://127.0.0.1:9999/v1',
            'LLM_API_KEY': 'test-only-key',
        }):
            self.assertIsInstance(LLMGateway()._client, ChatOpenAI)

    def test_fastapi_health(self):
        client = TestClient(app, client=('127.0.0.1', 50000))
        response = client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], '1.1.0')

    async def test_fastmcp_lists_read_only_tools(self):
        async with Client(create_mcp_server()) as client:
            tools = await client.list_tools()
            self.assertEqual(
                {item.name for item in tools},
                {'list_tables', 'describe_table', 'execute_query'},
            )


if __name__ == '__main__':
    unittest.main()
