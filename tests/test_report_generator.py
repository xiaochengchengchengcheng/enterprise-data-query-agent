import os
import tempfile
import unittest

from report_generator import ReportGenerator


class ReportGeneratorTest(unittest.TestCase):
    def test_generates_html_markdown_and_automatic_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            result = ReportGenerator(directory).generate(
                'task-1',
                '销售分析',
                '华东区域表现最佳。',
                [{
                    'name': 'sales',
                    'rows': [
                        {'region': '华东', 'amount': 120},
                        {'region': '华南', 'amount': 80},
                    ],
                }],
            )
            self.assertTrue(os.path.isfile(result['html_path']))
            self.assertTrue(os.path.isfile(result['markdown_path']))
            self.assertEqual(result['chart_count'], 1)
            with open(result['html_path'], 'r', encoding='utf-8') as handle:
                content = handle.read()
            self.assertIn('echarts.init', content)
            self.assertIn('华东区域表现最佳', content)


if __name__ == '__main__':
    unittest.main()
