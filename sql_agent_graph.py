# -*- coding: utf-8 -*-
"""
LangGraph 自主取数智能体核心循环逻辑

功能：
  完整实现企业内网自主取数Agent的多轮交互闭环：
    1. 解析用户需求
    2. 调用MCP获取表名
    3. 匹配业务表并获取表结构
    4. 调用大模型生成SQL
    5. 安全校验并执行SQL
    6. SQL报错时自动重试改写（最多3次）
    7. 数据脱敏
    8. 大模型生成分析结论
    9. 完整审计日志记录

设计原则：
  - 基于 LangGraph 构建有状态图
  - 每个节点职责单一
  - 完整的错误处理与重试机制
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional, TypedDict

from security_middleware import (
    validate_sql,
    mask_dataframe,
    AuditLogger,
    secure_process_query_result,
)
from llm_gateway import LLMGateway, get_llm_gateway
from db_mcp_server import (
    mcp_list_tables,
    mcp_describe_table,
    mcp_execute_query,
)

logger = logging.getLogger(__name__)


# ============================================================
# 状态定义（LangGraph State）
# ============================================================


class AgentState(TypedDict):
    """
    Agent状态定义
    记录整个取数流程的完整上下文
    """
    user_query: str
    session_id: str
    all_tables: List[str]
    matched_tables: List[str]
    table_schemas: Dict[str, Any]
    generated_sql: str
    sql_retry_count: int
    sql_error: str
    raw_query_result: List[Dict[str, Any]]
    query_columns: List[str]
    query_duration_ms: float
    returned_rows: int
    masked_query_result: List[Dict[str, Any]]
    analysis_result: str
    status: str
    error_message: str
    steps: List[Dict[str, Any]]


def create_initial_state(user_query: str, session_id: str) -> AgentState:
    """创建初始Agent状态"""
    return {
        'user_query': user_query,
        'session_id': session_id,
        'all_tables': [],
        'matched_tables': [],
        'table_schemas': {},
        'generated_sql': '',
        'sql_retry_count': 0,
        'sql_error': '',
        'raw_query_result': [],
        'query_columns': [],
        'query_duration_ms': 0.0,
        'returned_rows': 0,
        'masked_query_result': [],
        'analysis_result': '',
        'status': 'running',
        'error_message': '',
        'steps': [],
    }
# ============================================================
# 图节点函数
# ============================================================


def _record_step(state: AgentState, step_name: str, detail: str, status: str = 'running'):
    """记录流程步骤"""
    steps = state.get('steps', [])
    steps.append({
        'step': step_name,
        'detail': detail,
        'status': status,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    })
    state['steps'] = steps
    logger.info('[%s] %s: %s', step_name, status, detail)


def node_list_tables(state: AgentState) -> Dict[str, Any]:
    """节点1：获取数据库中所有表名"""
    _record_step(state, 'list_tables', '正在获取数据库所有表名...')
    try:
        result = mcp_list_tables()
        if result.get('success'):
            tables = result.get('tables', [])
            _record_step(state, 'list_tables', '成功获取 %d 张数据表' % len(tables), 'success')
            return {'all_tables': tables}
        else:
            error = result.get('error', '获取表名失败')
            _record_step(state, 'list_tables', '获取表名失败: ' + error, 'failed')
            return {'status': 'failed', 'error_message': '获取数据库表名失败: ' + error}
    except Exception as e:
        _record_step(state, 'list_tables', '异常: ' + str(e), 'failed')
        return {'status': 'failed', 'error_message': '获取数据库表名异常: ' + str(e)}


def node_match_tables(state: AgentState) -> Dict[str, Any]:
    """节点2：根据用户需求匹配关联业务表"""
    user_query = state.get('user_query', '')
    all_tables = state.get('all_tables', [])
    _record_step(state, 'match_tables', '正在根据用户需求匹配业务表（共%d张表）...' % len(all_tables))
    if not all_tables:
        _record_step(state, 'match_tables', '数据库中没有数据表', 'failed')
        return {'status': 'failed', 'error_message': '数据库中没有数据表，无法继续'}
    try:
        llm = get_llm_gateway()
        system_prompt = (
            '你是一名企业数据库管理员。请根据用户的业务需求，从给定的数据表列表中'
            '选出最相关的1~5张业务表。\n\n'
            '规则：\n'
            '1. 只从提供的表名中选择\n'
            '2. 按相关度从高到低排序\n'
            '3. 仅返回JSON数组格式，不要其他文字\n'
            '4. 格式：["table1", "table2"]\n'
        )
        user_prompt = (
            '用户需求：' + user_query + '\n\n'
            '数据库中的表名列表：' + json.dumps(all_tables, ensure_ascii=False) + '\n\n'
            '请选出最相关的业务表（JSON数组格式）：'
        )
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        response = llm.chat(messages, temperature=0.1, max_tokens=1024)
        content = response['content'].strip()
        import re
        json_match = re.search(r'`(?:json)?\s*\n?(.*?)`', content, re.DOTALL)
        if json_match:
            content = json_match.group(1).strip()
        matched_tables = json.loads(content)
        if not isinstance(matched_tables, list):
            matched_tables = [matched_tables]
        matched_tables = [t for t in matched_tables if t in all_tables]
        if not matched_tables:
            matched_tables = all_tables[:5]
            _record_step(state, 'match_tables', '大模型匹配结果不在数据库中，使用默认前5张表: ' + str(matched_tables), 'warning')
        else:
            _record_step(state, 'match_tables', '匹配到 %d 张业务表: %s' % (len(matched_tables), str(matched_tables)), 'success')
        return {'matched_tables': matched_tables}
    except (json.JSONDecodeError, Exception) as e:
        _record_step(state, 'match_tables', '匹配失败: ' + str(e), 'failed')
        fallback_tables = all_tables[:3]
        _record_step(state, 'match_tables', '降级使用前%d张表: %s' % (len(fallback_tables), str(fallback_tables)), 'warning')
        return {'matched_tables': fallback_tables}


def node_describe_tables(state: AgentState) -> Dict[str, Any]:
    """节点3：获取匹配表的字段结构信息"""
    matched_tables = state.get('matched_tables', [])
    _record_step(state, 'describe_tables', '正在查询 %d 张表的字段结构...' % len(matched_tables))
    schemas = {}
    for table_name in matched_tables:
        try:
            result = mcp_describe_table(table_name)
            if result.get('success'):
                schemas[table_name] = result.get('columns', [])
                _record_step(state, 'describe_tables', '表 %s: %d 个字段' % (table_name, result.get('count', 0)), 'success')
            else:
                _record_step(state, 'describe_tables', '表 %s 结构查询失败: %s' % (table_name, result.get('error', '')), 'failed')
        except Exception as e:
            _record_step(state, 'describe_tables', '表 %s 查询异常: %s' % (table_name, str(e)), 'failed')
    if not schemas:
        return {'status': 'failed', 'error_message': '无法获取任何表的字段结构信息'}
    return {'table_schemas': schemas}


def node_generate_sql(state: AgentState) -> Dict[str, Any]:
    """节点4：调用大模型生成SQL语句"""
    user_query = state.get('user_query', '')
    schemas = state.get('table_schemas', {})
    sql_error = state.get('sql_error', '')
    retry_count = state.get('sql_retry_count', 0)
    _record_step(state, 'generate_sql', '正在生成SQL（第%d次尝试）...' % (retry_count + 1))
    try:
        llm = get_llm_gateway()
        schema_descriptions = []
        for table_name, columns in schemas.items():
            col_desc = []
            for col in columns:
                comment = col.get('comment', '')
                line = '  - %s (%s)' % (col['field'], col['type'])
                if comment:
                    line += ' : ' + comment
                col_desc.append(line)
            schema_descriptions.append('表名: ' + table_name + '\n' + '\n'.join(col_desc))
        schema_text = '\n\n'.join(schema_descriptions)
        system_prompt = (
            '你是一名专业的SQL数据分析师。请根据用户的需求和数据库表结构，'
            '生成一条只读SELECT查询SQL语句。\n\n'
            '严格规则：\n'
            '1. 仅生成 SELECT 查询语句，严禁生成 DELETE / DROP / ALTER / TRUNCATE / UPDATE / INSERT 等语句\n'
            '2. 不要使用 INTO OUTFILE 等文件导出语法\n'
            '3. 如果涉及多表关联，请使用 JOIN 并指定正确的关联条件\n'
            '4. 使用 LIMIT 限制结果行数，最多返回50行\n'
            '5. 如果涉及聚合统计，请使用 GROUP BY\n'
            '6. 字段名用反引号包裹\n'
            '7. 仅返回SQL语句，不要添加任何解释文字\n'
            '8. SQL语句放在 `sql 代码块中\n'
        )
        user_prompt = '用户需求：' + user_query + '\n\n数据库表结构：\n' + schema_text + '\n\n请生成SQL：'
        if sql_error:
            user_prompt += '\n\n注意：上次生成的SQL执行报错，请修正。错误信息：' + sql_error
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        response = llm.chat(messages, temperature=0.1, max_tokens=2048)
        content = response['content']
        sql = llm.extract_sql_from_response(content)
        if not sql:
            _record_step(state, 'generate_sql', '未能从大模型响应中提取SQL语句', 'failed')
            return {'status': 'failed', 'error_message': '大模型未返回有效的SQL语句'}
        _record_step(state, 'generate_sql', 'SQL生成成功', 'success')
        # 重试场景：检测到上次的 sql_error 时递增重试计数，避免 execute_sql -> generate_sql 无限循环
        retry_count = state.get('sql_retry_count', 0)
        if sql_error:
            retry_count = retry_count + 1
            _record_step(state, 'generate_sql', '检测到上次SQL报错，进入第 %d 次重试' % retry_count, 'warning')
        return {'generated_sql': sql, 'sql_error': '', 'sql_retry_count': retry_count}
    except Exception as e:
        _record_step(state, 'generate_sql', '生成SQL失败: ' + str(e), 'failed')
        return {'status': 'failed', 'error_message': '生成SQL失败: ' + str(e)}
def node_execute_sql(state: AgentState) -> Dict[str, Any]:
    """节点5：安全校验并执行SQL"""
    sql = state.get('generated_sql', '')
    user_query = state.get('user_query', '')
    _record_step(state, 'execute_sql', '正在校验并执行SQL...')
    if not sql:
        return {'status': 'failed', 'error_message': '没有可执行的SQL语句'}
    try:
        result = mcp_execute_query(sql, user_query)
        if result.get('intercepted'):
            _record_step(state, 'execute_sql', 'SQL被安全中间件拦截: ' + result.get('error', ''), 'intercepted')
            return {'status': 'intercepted', 'error_message': 'SQL被安全中间件拦截: ' + result.get('error', '')}
        if not result.get('success'):
            error = result.get('error', '执行失败')
            _record_step(state, 'execute_sql', 'SQL执行失败: ' + error, 'failed')
            # 清空旧SQL，强制下一轮重新生成；保留 sql_error 触发重试
            return {'sql_error': error, 'status': 'failed', 'error_message': error, 'generated_sql': ''}
        rows = result.get('rows', [])
        columns = result.get('columns', [])
        duration_ms = result.get('duration_ms', 0)
        _record_step(state, 'execute_sql', 'SQL执行成功，返回 %d 行，耗时 %.2fms' % (len(rows), duration_ms), 'success')
        return {
            'raw_query_result': rows,
            'query_columns': columns,
            'query_duration_ms': duration_ms,
            'returned_rows': len(rows),
        }
    except Exception as e:
        _record_step(state, 'execute_sql', '执行异常: ' + str(e), 'failed')
        return {'sql_error': str(e), 'status': 'failed', 'error_message': str(e), 'generated_sql': ''}


def node_mask_data(state: AgentState) -> Dict[str, Any]:
    """节点6：对查询结果进行脱敏处理"""
    raw_data = state.get('raw_query_result', [])
    _record_step(state, 'mask_data', '正在对 %d 行数据进行脱敏处理...' % len(raw_data))
    if not raw_data:
        _record_step(state, 'mask_data', '无数据需要脱敏', 'warning')
        return {'masked_query_result': []}
    try:
        masked_data = secure_process_query_result(raw_data)
        _record_step(state, 'mask_data', '脱敏完成，共处理 %d 行数据' % len(masked_data), 'success')
        return {'masked_query_result': masked_data}
    except Exception as e:
        _record_step(state, 'mask_data', '脱敏处理失败: ' + str(e), 'failed')
        return {'masked_query_result': raw_data}


def node_analyze(state: AgentState) -> Dict[str, Any]:
    """节点7：大模型生成业务分析结论"""
    user_query = state.get('user_query', '')
    sql = state.get('generated_sql', '')
    masked_data = state.get('masked_query_result', [])
    columns = state.get('query_columns', [])
    _record_step(state, 'analyze', '正在基于脱敏数据生成分析结论...')
    try:
        llm = get_llm_gateway()
        analysis = llm.generate_analysis(user_query, sql, masked_data, columns)
        _record_step(state, 'analyze', '分析结论生成完成', 'success')
        return {'analysis_result': analysis}
    except Exception as e:
        _record_step(state, 'analyze', '生成分析结论失败: ' + str(e), 'failed')
        return {'status': 'failed', 'error_message': '生成分析结论失败: ' + str(e)}


# ============================================================
# 条件路由函数
# ============================================================


def should_retry_sql(state: AgentState) -> str:
    """
    判断SQL执行失败后是否需要重试

    Returns:
        'retry' - 继续重试
        'fail'  - 超过最大重试次数，终止
    """
    retry_count = state.get('sql_retry_count', 0)
    max_retries = int(os.environ.get('LLM_MAX_RETRIES', '3'))
    if retry_count < max_retries:
        return 'retry'
    # 超过最大重试次数：标记终态，返回 END 终止流程
    return 'fail'


def is_sql_executed(state: AgentState) -> str:
    """
    判断SQL是否执行成功

    Returns:
        'executed' - SQL执行成功，继续后续流程
        'failed'   - SQL执行失败，进入重试判断
        'intercepted' - SQL被拦截，终止流程
    """
    status = state.get('status', 'running')
    if status == 'intercepted':
        return 'intercepted'
    sql_error = state.get('sql_error', '')
    if sql_error:
        return 'failed'
    return 'executed'


def is_analysis_done(state: AgentState) -> str:
    """判断分析是否完成"""
    status = state.get('status', 'running')
    if status == 'failed':
        return 'failed'
    return 'done'
# ============================================================
# LangGraph 图构建
# ============================================================


def build_agent_graph():
    """
    构建LangGraph取数智能体图

    节点流程：
      list_tables -> match_tables -> describe_tables -> generate_sql
      -> execute_sql -> [成功: mask_data -> analyze]
      -> [失败: should_retry? -> retry: generate_sql | fail: 终止]
      -> [拦截: 终止]
    """
    try:
        from langgraph.graph import StateGraph, END

        # 创建图
        workflow = StateGraph(AgentState)

        # 注册所有节点
        workflow.add_node('list_tables', node_list_tables)
        workflow.add_node('match_tables', node_match_tables)
        workflow.add_node('describe_tables', node_describe_tables)
        workflow.add_node('generate_sql', node_generate_sql)
        workflow.add_node('execute_sql', node_execute_sql)
        workflow.add_node('mask_data', node_mask_data)
        workflow.add_node('analyze', node_analyze)

        # 设置入口
        workflow.set_entry_point('list_tables')

        # 设置边：顺序流程
        workflow.add_edge('list_tables', 'match_tables')
        workflow.add_edge('match_tables', 'describe_tables')
        workflow.add_edge('describe_tables', 'generate_sql')
        workflow.add_edge('generate_sql', 'execute_sql')

        # 条件边：SQL执行结果判断（合并重试逻辑，避免中间节点）
        # executed -> 脱敏分析; intercepted -> 终止; failed -> 判断是否重试
        def _sql_result_router(state):
            route = is_sql_executed(state)
            if route == 'executed':
                return 'mask_data'
            elif route == 'intercepted':
                return END
            else:
                # failed: 判断是否重试
                return 'generate_sql' if should_retry_sql(state) == 'retry' else END

        workflow.add_conditional_edges(
            'execute_sql',
            _sql_result_router,
            {
                'mask_data': 'mask_data',
                'generate_sql': 'generate_sql',
                END: END,
            }
        )

        # 正常流程
        workflow.add_edge('mask_data', 'analyze')
        workflow.add_edge('analyze', END)

        # 编译图
        app = workflow.compile()
        logger.info('LangGraph 智能体图构建完成')
        return app

    except ImportError as e:
        logger.error('导入 LangGraph 失败: %s', e)
        raise
    except Exception as e:
        logger.error('构建LangGraph图失败: %s', e)
        raise


# ============================================================
# Agent 运行入口
# ============================================================


# 全局图实例
_agent_app = None


def get_agent_app():
    """获取LangGraph应用实例（单例）"""
    global _agent_app
    if _agent_app is None:
        _agent_app = build_agent_graph()
    return _agent_app


def run_agent(user_query: str, session_id: str = '') -> Dict[str, Any]:
    """
    运行取数智能体

    Args:
        user_query: 用户自然语言取数需求
        session_id: 会话ID（可选）

    Returns:
        完整结果字典，包含：
        - status: 状态
        - analysis: 分析结论
        - sql: 生成的SQL
        - steps: 执行步骤
        - error: 错误信息
    """
    if not session_id:
        session_id = 'session_' + str(int(time.time() * 1000))

    logger.info('=' * 60)
    logger.info('开始处理取数请求 | session: %s', session_id)
    logger.info('用户提问: %s', user_query)
    logger.info('=' * 60)

    # 创建初始状态
    initial_state = create_initial_state(user_query, session_id)

    try:
        # 获取图应用
        app = get_agent_app()

        # 执行图
        # 设置递归上限兜底：正常流程约7步，重试3次最多约 7+3*2=13 步，设50留足余量
        result = app.invoke(initial_state, config={'recursion_limit': 50})

        # 提取结果
        status = result.get('status', 'success')
        if status == 'running':
            status = 'success'

        response = {
            'status': status,
            'session_id': session_id,
            'user_query': user_query,
            'generated_sql': result.get('generated_sql', ''),
            'query_columns': result.get('query_columns', []),
            'returned_rows': result.get('returned_rows', 0),
            'query_duration_ms': result.get('query_duration_ms', 0),
            'analysis': result.get('analysis_result', ''),
            'steps': result.get('steps', []),
            'error': result.get('error_message', ''),
        }

        logger.info('取数流程完成 | status: %s | session: %s', status, session_id)
        return response

    except Exception as e:
        logger.error('Agent运行异常: %s', e)
        return {
            'status': 'failed',
            'session_id': session_id,
            'user_query': user_query,
            'generated_sql': '',
            'query_columns': [],
            'returned_rows': 0,
            'query_duration_ms': 0,
            'analysis': '',
            'steps': [],
            'error': 'Agent运行异常: ' + str(e),
        }


# ============================================================
# 直接运行入口（调试用）
# ============================================================

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    print('LangGraph 取数智能体模块加载完成')
    print('请通过 run_agent(user_query) 函数启动取数流程')