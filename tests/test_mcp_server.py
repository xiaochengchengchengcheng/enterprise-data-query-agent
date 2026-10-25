import unittest

from fastmcp import Client

from db_mcp_server import create_mcp_server
from mcp_server_v2 import mcp


class MCPServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_fastmcp_in_memory_client_lists_tools_and_resources(self):
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {item.name for item in tools}
            self.assertIn('analysis_plan', names)
            self.assertIn('nl2sql_query', names)
            self.assertIn('rag_search', names)

            resources = await client.list_resources()
            uris = {str(item.uri) for item in resources}
            self.assertIn('analyst://models', uris)

    async def test_database_fastmcp_server_lists_read_only_tools(self):
        async with Client(create_mcp_server()) as client:
            tools = await client.list_tools()
            names = {item.name for item in tools}
            self.assertEqual(
                names,
                {'list_tables', 'describe_table', 'execute_query'},
            )


if __name__ == '__main__':
    unittest.main()
