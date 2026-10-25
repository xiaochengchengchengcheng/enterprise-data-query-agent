# -*- coding: utf-8 -*-
"""HTML/Markdown report generation with embedded ECharts configurations."""

import html
import json
import os
import re
from typing import Any, Dict, List, Optional


class ReportGenerator:
    def __init__(self, output_root: Optional[str] = None):
        self.output_root = os.path.abspath(output_root or os.environ.get('REPORT_OUTPUT_DIR', './outputs'))
        os.makedirs(self.output_root, exist_ok=True)

    def generate(
        self,
        analysis_id: str,
        title: str,
        summary: str,
        datasets: List[Dict[str, Any]],
        python_result: Optional[Dict[str, Any]] = None,
        charts: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        safe_id = re.sub(r'[^A-Za-z0-9_-]', '_', analysis_id)
        report_dir = os.path.abspath(os.path.join(self.output_root, safe_id))
        if os.path.commonpath([self.output_root, report_dir]) != self.output_root:
            raise ValueError('非法报告目录')
        os.makedirs(report_dir, exist_ok=True)

        chart_list = list(charts or [])
        if not chart_list and python_result:
            chart_list = python_result.get('charts', []) or []
        if not chart_list:
            chart_list = self._automatic_charts(datasets)

        markdown = self._build_markdown(title, summary, datasets, python_result)
        html_content = self._build_html(title, summary, datasets, python_result, chart_list)
        markdown_path = os.path.join(report_dir, 'report.md')
        html_path = os.path.join(report_dir, 'report.html')
        with open(markdown_path, 'w', encoding='utf-8') as handle:
            handle.write(markdown)
        with open(html_path, 'w', encoding='utf-8') as handle:
            handle.write(html_content)
        return {
            'markdown_path': markdown_path,
            'html_path': html_path,
            'chart_count': len(chart_list),
        }

    @staticmethod
    def _build_markdown(
        title: str,
        summary: str,
        datasets: List[Dict[str, Any]],
        python_result: Optional[Dict[str, Any]],
    ) -> str:
        lines = ['# ' + title, '', '## 分析结论', '', summary or '暂无结论', '']
        if python_result and python_result.get('analysis_result'):
            lines.extend([
                '## Python 深度分析', '',
                '```json',
                json.dumps(python_result['analysis_result'], ensure_ascii=False, indent=2),
                '```', '',
            ])
        lines.extend(['## 数据集概览', ''])
        for item in datasets:
            lines.append('- **%s**：%d 行' % (
                item.get('name', 'dataset'), len(item.get('rows', []))
            ))
        lines.append('')
        return '\n'.join(lines)

    def _build_html(
        self,
        title: str,
        summary: str,
        datasets: List[Dict[str, Any]],
        python_result: Optional[Dict[str, Any]],
        charts: List[Dict[str, Any]],
    ) -> str:
        echarts_url = os.environ.get(
            'ECHARTS_SCRIPT_URL',
            'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js',
        )
        chart_blocks = []
        scripts = []
        for index, option in enumerate(charts):
            chart_id = 'chart_%d' % index
            chart_blocks.append('<section class="chart-card"><div id="%s" class="chart"></div></section>' % chart_id)
            option_json = json.dumps(option, ensure_ascii=False, default=str).replace('<', '\\u003c')
            scripts.append(
                'const c%d=echarts.init(document.getElementById(%s));c%d.setOption(%s);'
                % (index, json.dumps(chart_id), index, option_json)
            )
        dataset_cards = ''.join(
            '<li><strong>%s</strong>：%d 行</li>' % (
                html.escape(str(item.get('name', 'dataset'))),
                len(item.get('rows', [])),
            ) for item in datasets
        )
        python_json = ''
        if python_result and python_result.get('analysis_result'):
            python_json = '<h2>Python 深度分析</h2><pre>%s</pre>' % html.escape(
                json.dumps(python_result['analysis_result'], ensure_ascii=False, indent=2)
            )
        return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title><script src="%s"></script>
<style>
body{font-family:Inter,"Microsoft YaHei",sans-serif;background:#f4f7fb;color:#172033;margin:0}
main{max-width:1180px;margin:32px auto;padding:0 20px}.hero,.card,.chart-card{background:#fff;border-radius:16px;padding:24px;margin-bottom:18px;box-shadow:0 8px 30px #1c35580d}
h1{margin:0 0 10px;color:#102a43}.summary{line-height:1.8;white-space:pre-wrap}.chart{height:420px}pre{white-space:pre-wrap;overflow:auto;background:#102a43;color:#e6edf3;padding:18px;border-radius:10px}
</style></head><body><main>
<section class="hero"><h1>%s</h1><div class="summary">%s</div></section>
%s
<section class="card"><h2>数据集概览</h2><ul>%s</ul></section>
%s
</main><script>%s window.addEventListener('resize',()=>{%s});</script></body></html>''' % (
            html.escape(title), html.escape(echarts_url, quote=True), html.escape(title),
            html.escape(summary or '暂无结论'), python_json, dataset_cards,
            ''.join(chart_blocks), ''.join(scripts),
            ''.join('c%d.resize();' % index for index in range(len(charts))),
        )

    @staticmethod
    def _automatic_charts(datasets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for dataset in datasets:
            rows = dataset.get('rows', [])
            if not rows:
                continue
            columns = list(rows[0].keys())
            numeric = [
                column for column in columns
                if any(isinstance(row.get(column), (int, float)) for row in rows)
            ]
            categories = [column for column in columns if column not in numeric]
            if numeric:
                category = categories[0] if categories else columns[0]
                value = numeric[0]
                return [{
                    'title': {'text': '%s - %s' % (dataset.get('name', '数据'), value)},
                    'tooltip': {'trigger': 'axis'},
                    'xAxis': {'type': 'category', 'data': [str(row.get(category, '')) for row in rows]},
                    'yAxis': {'type': 'value'},
                    'series': [{
                        'name': value,
                        'type': 'bar',
                        'data': [row.get(value, 0) for row in rows],
                    }],
                }]
        return []


report_generator = ReportGenerator()
