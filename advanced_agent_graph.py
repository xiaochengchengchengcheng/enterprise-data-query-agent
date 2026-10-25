# -*- coding: utf-8 -*-
"""V2 AI data analyst: planning, HITL approval, Python, RAG and reports."""

import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from conversation_store import analysis_task_store, conversation_store
from db_mcp_server import mcp_describe_table, mcp_list_tables
from model_registry import ModelRegistry, model_registry
from python_executor import PythonExecutor, extract_python_code
from rag_store import SQLiteVectorStore, rag_store
from report_generator import ReportGenerator, report_generator
from sql_agent_graph import run_agent

logger = logging.getLogger(__name__)


class AnalysisState(TypedDict, total=False):
    analysis_id: str
    session_id: str
    user_query: str
    plan: Dict[str, Any]
    chat_model: str
    embedding_model: str
    datasets: List[Dict[str, Any]]
    python_code: str
    python_result: Dict[str, Any]
    python_error: str
    summary: str
    report: Dict[str, Any]
    status: str
    error: str
    steps: List[Dict[str, Any]]


def _json_object(content: str) -> Dict[str, Any]:
    text = (content or '').strip()
    fenced = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            text = text[start:end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('模型未返回 JSON 对象')
    return value


def _step(state: AnalysisState, name: str, detail: str, status: str = 'success') -> None:
    steps = state.setdefault('steps', [])
    steps.append({
        'step': name,
        'detail': detail,
        'status': status,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    })


class AdvancedDataAnalyst:
    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        vector_store: Optional[SQLiteVectorStore] = None,
        reporter: Optional[ReportGenerator] = None,
    ):
        self.registry = registry or model_registry
        self.vector_store = vector_store or rag_store
        self.reporter = reporter or report_generator

    def sync_metadata(self, embedding_model: Optional[str] = None) -> Dict[str, Any]:
        tables_result = mcp_list_tables()
        if not tables_result.get('success'):
            raise RuntimeError(tables_result.get('error', '无法读取数据库表'))
        documents = []
        for table in tables_result.get('tables', []):
            schema_result = mcp_describe_table(table)
            if not schema_result.get('success'):
                continue
            columns = schema_result.get('columns', [])
            column_text = '; '.join(
                '%s %s %s' % (
                    column.get('field', ''),
                    column.get('type', ''),
                    column.get('comment', ''),
                ) for column in columns
            )
            documents.append({
                'id': 'schema:' + table,
                'content': '数据表 %s。字段：%s' % (table, column_text),
                'metadata': {'type': 'schema', 'table': table, 'columns': columns},
            })
        count = self.vector_store.upsert(
            documents,
            namespace='business',
            embedding_model=embedding_model,
        )
        return {'indexed_documents': count, 'tables': len(documents)}

    def create_plan(
        self,
        user_query: str,
        session_id: Optional[str] = None,
        chat_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        analysis_id = str(uuid.uuid4())
        chat_name = chat_model or 'default-chat'
        embedding_name = embedding_model or self.registry.default_embedding_name()

        if self.vector_store.count('business') == 0 and os.environ.get('RAG_AUTO_SYNC', 'true').lower() == 'true':
            try:
                self.sync_metadata(embedding_name)
            except Exception as exc:
                logger.warning('自动同步 RAG 元数据失败: %s', exc)

        rag_context = self.vector_store.search(
            user_query,
            top_k=int(os.environ.get('RAG_TOP_K', '5')),
            namespace='business',
            embedding_model=embedding_name,
        )
        history = conversation_store.get_messages(session_id)
        llm = self.registry.get_chat_gateway(chat_name)
        prompt = '''你是一名企业 AI 数据分析师。请先制定分析计划，不要执行 SQL。
必须只返回 JSON 对象，结构如下：
{
  "objective": "分析目标",
  "sql_tasks": [{"name": "数据集名称", "question": "可独立执行的自然语言取数问题"}],
  "python_analysis": {"enabled": true, "goals": ["统计或预测目标"]},
  "recommended_charts": [{"title": "图表名", "type": "bar|line|pie|scatter"}],
  "assumptions": ["需要用户确认的假设"],
  "expected_output": "最终交付内容"
}
规则：sql_tasks 为 1~3 项；问题必须具体且可转换为只读 SQL；只有确实需要统计、预测或组合分析时才启用 Python。'''
        user_content = (
            '用户需求：%s\n\n最近对话：%s\n\nRAG 业务上下文：%s'
            % (
                user_query,
                json.dumps(history[-8:], ensure_ascii=False, default=str),
                json.dumps(rag_context, ensure_ascii=False, default=str),
            )
        )
        response = llm.chat([
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': user_content},
        ], temperature=0.1, max_tokens=3000)
        plan = self._normalize_plan(_json_object(response['content']), user_query)
        task: AnalysisState = {
            'analysis_id': analysis_id,
            'session_id': session_id,
            'user_query': user_query,
            'plan': plan,
            'chat_model': chat_name,
            'embedding_model': embedding_name,
            'datasets': [],
            'python_code': '',
            'python_result': {},
            'python_error': '',
            'summary': '',
            'report': {},
            'status': 'awaiting_approval',
            'error': '',
            'steps': [],
        }
        _step(task, 'create_plan', '已生成分析计划，等待人工确认')
        analysis_task_store.put(analysis_id, task)
        conversation_store.append(session_id, 'user', user_query)
        return self._public_task(task)

    def review_plan(
        self,
        analysis_id: str,
        approved: bool,
        feedback: str = '',
    ) -> Dict[str, Any]:
        task = analysis_task_store.get(analysis_id)
        if not task:
            raise KeyError('分析任务不存在或已过期')
        task.pop('_updated_at', None)
        if task.get('status') not in ('awaiting_approval', 'revision_required'):
            raise ValueError('当前任务状态不允许再次确认: %s' % task.get('status'))
        if not approved:
            if not feedback.strip():
                task['status'] = 'revision_required'
                _step(task, 'human_feedback', '用户拒绝计划，等待修改意见', 'warning')
                analysis_task_store.put(analysis_id, task)
                return self._public_task(task)
            task['plan'] = self._revise_plan(task, feedback)
            task['status'] = 'awaiting_approval'
            _step(task, 'human_feedback', '已根据人工反馈更新计划')
            analysis_task_store.put(analysis_id, task)
            return self._public_task(task)

        task['status'] = 'running'
        _step(task, 'human_feedback', '计划已获人工确认')
        analysis_task_store.put(analysis_id, task)
        try:
            app = self._build_execution_graph()
            result = app.invoke(task, config={'recursion_limit': 30})
            result['status'] = 'success' if not result.get('error') else 'failed'
        except Exception as exc:
            logger.exception('高级分析任务失败')
            result = task
            result['status'] = 'failed'
            result['error'] = str(exc)
            _step(result, 'failed', '分析失败: %s' % exc, 'failed')
        analysis_task_store.put(analysis_id, result)
        if result.get('summary'):
            conversation_store.append(result['session_id'], 'assistant', result['summary'])
        return self._public_task(result)

    def get_task(self, analysis_id: str) -> Dict[str, Any]:
        task = analysis_task_store.get(analysis_id)
        if not task:
            raise KeyError('分析任务不存在或已过期')
        return self._public_task(task)

    def _revise_plan(self, task: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        llm = self.registry.get_chat_gateway(task.get('chat_model'))
        response = llm.chat([
            {'role': 'system', 'content': '根据人工反馈修改分析计划。只返回与原计划相同结构的 JSON 对象。'},
            {'role': 'user', 'content': '原计划：%s\n\n人工反馈：%s' % (
                json.dumps(task['plan'], ensure_ascii=False), feedback,
            )},
        ], temperature=0.1, max_tokens=3000)
        return self._normalize_plan(_json_object(response['content']), task['user_query'])

    @staticmethod
    def _normalize_plan(plan: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        tasks = plan.get('sql_tasks') or []
        normalized_tasks = []
        for index, item in enumerate(tasks[:3]):
            if isinstance(item, str):
                item = {'name': 'dataset_%d' % (index + 1), 'question': item}
            question = str(item.get('question', '')).strip()
            if question:
                normalized_tasks.append({
                    'name': str(item.get('name') or 'dataset_%d' % (index + 1)),
                    'question': question,
                })
        if not normalized_tasks:
            normalized_tasks = [{'name': 'primary_dataset', 'question': user_query}]
        python_plan = plan.get('python_analysis') or {'enabled': False, 'goals': []}
        return {
            'objective': str(plan.get('objective') or user_query),
            'sql_tasks': normalized_tasks,
            'python_analysis': {
                'enabled': bool(python_plan.get('enabled', False)),
                'goals': [str(item) for item in python_plan.get('goals', [])][:5],
            },
            'recommended_charts': list(plan.get('recommended_charts') or [])[:6],
            'assumptions': [str(item) for item in plan.get('assumptions', [])][:10],
            'expected_output': str(plan.get('expected_output') or '数据分析结论与可视化报告'),
        }

    def _build_execution_graph(self):
        from langgraph.graph import END, StateGraph

        workflow = StateGraph(AnalysisState)
        workflow.add_node('execute_sql_tasks', self._node_execute_sql_tasks)
        workflow.add_node('generate_python', self._node_generate_python)
        workflow.add_node('execute_python', self._node_execute_python)
        workflow.add_node('summarize', self._node_summarize)
        workflow.add_node('render_report', self._node_report)
        workflow.set_entry_point('execute_sql_tasks')
        workflow.add_conditional_edges(
            'execute_sql_tasks',
            lambda state: 'python' if state.get('plan', {}).get('python_analysis', {}).get('enabled') and state.get('datasets') else 'summary',
            {'python': 'generate_python', 'summary': 'summarize'},
        )
        workflow.add_edge('generate_python', 'execute_python')
        workflow.add_edge('execute_python', 'summarize')
        workflow.add_edge('summarize', 'render_report')
        workflow.add_edge('render_report', END)
        return workflow.compile()

    def _node_execute_sql_tasks(self, state: AnalysisState) -> Dict[str, Any]:
        datasets = []
        for index, item in enumerate(state['plan']['sql_tasks']):
            result = run_agent(item['question'], '%s_sql_%d' % (state['session_id'], index + 1))
            if result.get('status') != 'success':
                raise RuntimeError('数据集 %s 查询失败: %s' % (item['name'], result.get('error', '未知错误')))
            datasets.append({
                'name': item['name'],
                'question': item['question'],
                'sql': result.get('generated_sql', ''),
                'columns': result.get('query_columns', []),
                'rows': result.get('data', []),
                'analysis': result.get('analysis', ''),
            })
        _step(state, 'execute_sql_tasks', '已完成 %d 个只读数据查询' % len(datasets))
        return {'datasets': datasets, 'steps': state['steps']}

    def _node_generate_python(self, state: AnalysisState) -> Dict[str, Any]:
        llm = self.registry.get_chat_gateway(state.get('chat_model'))
        previews = []
        for dataset in state.get('datasets', []):
            previews.append({
                'name': dataset['name'],
                'rows': dataset['rows'][:100],
                'columns': dataset['columns'],
            })
        system_prompt = '''你是安全的 Python 数据分析代码生成器。只返回一个 python 代码块。
运行环境已经提供变量 rows（全部脱敏记录）和 df（pandas DataFrame，若 pandas 可用）。
禁止文件、网络、进程和系统操作。允许 pandas/numpy/scipy/sklearn/math/statistics。
代码必须最终给 analysis_result 赋一个可 JSON 序列化的字典，并给 charts 赋 ECharts option 列表。
不要读取文件，不要调用 print 代替结果变量。'''
        prompt = '分析目标：%s\nPython 分析要求：%s\n建议图表：%s\n数据预览：%s' % (
            state['plan']['objective'],
            json.dumps(state['plan']['python_analysis'], ensure_ascii=False),
            json.dumps(state['plan'].get('recommended_charts', []), ensure_ascii=False),
            json.dumps(previews, ensure_ascii=False, default=str),
        )
        response = llm.chat([
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ], temperature=0.1, max_tokens=5000)
        code = extract_python_code(response['content'])
        _step(state, 'generate_python', '已生成受控 Python 分析代码')
        return {'python_code': code, 'steps': state['steps']}

    def _node_execute_python(self, state: AnalysisState) -> Dict[str, Any]:
        rows = []
        for dataset in state.get('datasets', []):
            for row in dataset.get('rows', []):
                value = dict(row)
                value['_dataset'] = dataset.get('name', '')
                rows.append(value)
        try:
            result = PythonExecutor().execute(state.get('python_code', ''), rows)
            _step(state, 'execute_python', 'Python 深度分析执行完成')
            return {'python_result': result, 'python_error': '', 'steps': state['steps']}
        except Exception as exc:
            _step(state, 'execute_python', 'Python 分析降级: %s' % exc, 'warning')
            return {'python_result': {}, 'python_error': str(exc), 'steps': state['steps']}

    def _node_summarize(self, state: AnalysisState) -> Dict[str, Any]:
        llm = self.registry.get_chat_gateway(state.get('chat_model'))
        compact = [{
            'name': item['name'],
            'sql': item['sql'],
            'rows': item['rows'][:50],
            'analysis': item['analysis'],
        } for item in state.get('datasets', [])]
        response = llm.chat([
            {'role': 'system', 'content': '你是企业数据分析师。基于给定事实生成 Markdown 分析报告摘要，必须区分事实、推断和建议，不得编造数据。'},
            {'role': 'user', 'content': '用户需求：%s\n计划：%s\n数据：%s\nPython结果：%s\nPython错误：%s' % (
                state['user_query'],
                json.dumps(state['plan'], ensure_ascii=False),
                json.dumps(compact, ensure_ascii=False, default=str),
                json.dumps(state.get('python_result', {}), ensure_ascii=False, default=str),
                state.get('python_error', ''),
            )},
        ], temperature=0.2, max_tokens=5000)
        _step(state, 'summarize', '已汇总业务结论')
        return {'summary': response['content'], 'steps': state['steps']}

    def _node_report(self, state: AnalysisState) -> Dict[str, Any]:
        report = self.reporter.generate(
            state['analysis_id'],
            state['plan']['objective'],
            state.get('summary', ''),
            state.get('datasets', []),
            state.get('python_result'),
        )
        _step(state, 'report', '已生成 HTML/Markdown 报告')
        return {'report': report, 'steps': state['steps']}

    @staticmethod
    def _public_task(task: Dict[str, Any]) -> Dict[str, Any]:
        value = dict(task)
        value.pop('_updated_at', None)
        report = dict(value.get('report') or {})
        if report:
            report.pop('html_path', None)
            report.pop('markdown_path', None)
            report['html_url'] = '/api/v2/analyses/%s/report/html' % value['analysis_id']
            report['markdown_url'] = '/api/v2/analyses/%s/report/markdown' % value['analysis_id']
            value['report'] = report
        return value


advanced_data_analyst = AdvancedDataAnalyst()
