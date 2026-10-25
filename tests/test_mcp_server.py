import unittest

from mcp_server_v2 import handle_message


class MCPServerTest(unittest.TestCase):
    def test_initialize_and_list_tools(self):
        initialized = handle_message({
            'jsonrpc': '2.0',
            'id': 1,
            'method': 'initialize',
            'params': {'protocolVersion': '2024-11-05'},
        })
        self.assertEqual(initialized['result']['serverInfo']['version'], '2.0.0')
        tools = handle_message({
            'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {},
        })
        names = {item['name'] for item in tools['result']['tools']}
        self.assertIn('analysis_plan', names)
        self.assertIn('nl2sql_query', names)


if __name__ == '__main__':
    unittest.main()
