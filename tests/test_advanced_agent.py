import json
import unittest
from unittest import mock

from advanced_agent_graph import AdvancedDataAnalyst


class FakeGateway:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.calls == 1:
            content = json.dumps({
                'objective': '销售趋势分析',
                'sql_tasks': [{'name': 'sales', 'question': '查询月度销售额'}],
                'python_analysis': {'enabled': True, 'goals': ['计算增长率']},
                'recommended_charts': [{'title': '趋势', 'type': 'line'}],
                'assumptions': [],
                'expected_output': '趋势报告',
            }, ensure_ascii=False)
        elif self.calls == 2:
            content = '```python\nanalysis_result={"growth": 0.2}\ncharts=[]\n```'
        else:
            content = '## 结论\n销售额增长 20%。'
        return {'content': content}


class FakeRegistry:
    def __init__(self):
        self.gateway = FakeGateway()

    def default_embedding_name(self):
        return 'local-hashing'

    def get_chat_gateway(self, name=None):
        return self.gateway


class FakeVectorStore:
    def count(self, namespace=None):
        return 1

    def search(self, *args, **kwargs):
        return []


class FakeReporter:
    def generate(self, *args, **kwargs):
        return {
            'html_path': 'X:/outputs/report.html',
            'markdown_path': 'X:/outputs/report.md',
            'chart_count': 1,
        }


class FakeExecutor:
    def execute(self, code, rows):
        return {'analysis_result': {'growth': 0.2}, 'charts': [], 'mode': 'test'}


class AdvancedAgentTest(unittest.TestCase):
    def test_plan_approve_execute_and_report(self):
        analyst = AdvancedDataAnalyst(FakeRegistry(), FakeVectorStore(), FakeReporter())
        sql_result = {
            'status': 'success',
            'generated_sql': 'SELECT month, amount FROM sales LIMIT 50',
            'query_columns': ['month', 'amount'],
            'data': [{'month': '2026-09', 'amount': 100}],
            'analysis': '销售额为 100',
        }
        with mock.patch('advanced_agent_graph.run_agent', return_value=sql_result), \
                mock.patch('advanced_agent_graph.PythonExecutor', return_value=FakeExecutor()):
            planned = analyst.create_plan('分析销售趋势', session_id='test-session')
            self.assertEqual(planned['status'], 'awaiting_approval')
            completed = analyst.review_plan(planned['analysis_id'], True)
        self.assertEqual(completed['status'], 'success')
        self.assertEqual(completed['datasets'][0]['name'], 'sales')
        self.assertEqual(completed['python_result']['analysis_result']['growth'], 0.2)
        self.assertIn('/report/html', completed['report']['html_url'])


if __name__ == '__main__':
    unittest.main()
