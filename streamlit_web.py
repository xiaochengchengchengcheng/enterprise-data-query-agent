# -*- coding: utf-8 -*-
"""
Streamlit 轻量化网页交互前端

功能：
  1. 简洁的取数需求输入页面
  2. 实时展示Agent执行步骤
  3. 展示脱敏后的查询结果
  4. 展示业务分析结论
  5. 历史查询记录查看

设计原则：
  - 轻量化设计，无需复杂前端框架
  - 仅内网IP可访问
  - 简洁直观的用户体验
"""

import os
import json
import time
import logging
from typing import Dict, Any, List, Optional

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv()

import streamlit as st
import streamlit.components.v1 as components
import requests

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# 页面配置
# ============================================================

st.set_page_config(
    page_title='企业内网自主取数智能体',
    page_icon=':bar_chart:',
    layout='wide',
    initial_sidebar_state='expanded',
)

# API基础地址（从环境变量或默认值读取）
API_BASE = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000')
APP_API_KEY = os.environ.get('APP_API_KEY', '')


# ============================================================
# 辅助函数
# ============================================================


def call_api(endpoint: str, method: str = 'GET', data: Optional[Dict] = None) -> Dict:
    """
    调用后端API

    Args:
        endpoint: API端点路径
        method: HTTP方法
        data: 请求体数据（POST时使用）

    Returns:
        API响应字典
    """
    url = API_BASE.rstrip('/') + '/' + endpoint.lstrip('/')
    headers = {'X-API-Key': APP_API_KEY} if APP_API_KEY else {}
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        else:
            resp = requests.post(url, json=data, headers=headers, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'error': '无法连接到后端服务，请确认 FastAPI 服务已启动'}
    except requests.exceptions.Timeout:
        return {'status': 'error', 'error': '请求超时，请稍后重试'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def fetch_report(endpoint: str):
    """下载需要 API Key 请求头的报告文件。"""
    url = API_BASE.rstrip('/') + '/' + endpoint.lstrip('/')
    headers = {'X-API-Key': APP_API_KEY} if APP_API_KEY else {}
    return requests.get(url, headers=headers, timeout=60)


def get_step_icon(status: str) -> str:
    """根据步骤状态返回对应图标"""
    icons = {
        'running': ':arrows_counterclockwise:',
        'success': ':white_check_mark:',
        'failed': ':x:',
        'intercepted': ':warning:',
        'warning': ':warning:',
    }
    return icons.get(status, ':grey_question:')


# ============================================================
# 侧边栏
# ============================================================

with st.sidebar:
    st.title(':bar_chart: AI 数据分析师')
    st.markdown('---')
    st.markdown('**系统状态**')

    # 健康检查
    health = call_api('/health')
    if health.get('status') == 'running':
        st.success(':green[服务运行中]')
        st.caption('运行时长: %.1f 秒' % health.get('uptime_seconds', 0))
    else:
        st.error(':red[服务未连接]')
        st.caption(health.get('error', ''))

    st.markdown('---')
    st.markdown('**安全提示**')
    st.caption(
        ':lock: 所有数据发送前已脱敏\n\n'
        ':no_entry: 仅支持SELECT只读查询\n\n'
        ':page_facing_up: 完整审计日志记录'
    )

    st.markdown('---')
    st.caption('Enterprise AI Data Analyst v2.0.0')


# ============================================================
# 主页面
# ============================================================

st.title(':bar_chart: 企业 AI 智能数据分析师')
st.markdown('从自然语言取数升级为可规划、可干预、可执行 Python 并生成图表报告的分析智能体')

analysis_mode = st.radio(
    '分析模式',
    ['AI 数据分析师（计划确认）', '快速 Text-to-SQL'],
    horizontal=True,
)

# 输入区域
col1, col2 = st.columns([4, 1])
with col1:
    user_query = st.text_input(
        '请输入您的取数需求',
        placeholder='例如：查询上个月各地区的销售额排名',
        label_visibility='collapsed',
    )
with col2:
    submit_btn = st.button('开始分析', type='primary', use_container_width=True)

# 会话历史（使用st.session_state保持状态）
if 'history' not in st.session_state:
    st.session_state.history = []

if 'current_result' not in st.session_state:
    st.session_state.current_result = None


# ============================================================
# 处理取数请求
# ============================================================

if submit_btn and user_query.strip():
    with st.spinner('智能体正在理解需求并生成分析计划...'):
        if analysis_mode.startswith('AI'):
            result = call_api(
                '/api/v2/analyses/plan',
                method='POST',
                data={'user_query': user_query.strip()},
            )
        else:
            result = call_api('/api/query', method='POST', data={'user_query': user_query.strip()})

        # 保存到会话状态
        st.session_state.current_result = result
        st.session_state.history.append({
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'query': user_query.strip(),
            'result': result,
        })

        # 强制刷新
        st.rerun()

elif submit_btn and not user_query.strip():
    st.warning('请输入取数需求')


# ============================================================
# 显示结果
# ============================================================

current = st.session_state.current_result

if current:
    status = current.get('status', '')
    session_id = current.get('session_id', '')

    # 状态显示
    if status == 'awaiting_approval':
        st.warning(':memo: 分析计划等待确认')
    elif status == 'revision_required':
        st.warning(':pencil2: 请填写修改意见')
    elif status == 'success':
        st.success(':white_check_mark: 取数完成')
    elif status == 'intercepted':
        st.error(':warning: SQL被安全中间件拦截')
    elif status == 'failed':
        st.error(':x: 取数失败')
    else:
        st.info(':arrows_counterclockwise: 处理中...')

    # 错误信息
    error = current.get('error', '')
    if error:
        st.error('错误信息: ' + error)

    if status in ('awaiting_approval', 'revision_required'):
        st.subheader('分析计划')
        plan = current.get('plan', {})
        st.markdown('**目标：** ' + plan.get('objective', ''))
        for index, task in enumerate(plan.get('sql_tasks', []), 1):
            st.markdown('%d. **%s** — %s' % (index, task.get('name', ''), task.get('question', '')))
        python_plan = plan.get('python_analysis', {})
        st.markdown('**Python 深度分析：** ' + ('启用' if python_plan.get('enabled') else '不启用'))
        for goal in python_plan.get('goals', []):
            st.markdown('- ' + goal)
        assumptions = plan.get('assumptions', [])
        if assumptions:
            st.markdown('**需要确认的假设：**')
            for item in assumptions:
                st.markdown('- ' + item)

        feedback = st.text_area('调整意见（如需修改计划）', key='plan_feedback')
        approve_col, revise_col = st.columns(2)
        with approve_col:
            if st.button('确认并执行', type='primary', use_container_width=True):
                with st.spinner('正在执行查询、Python 分析并生成报告...'):
                    st.session_state.current_result = call_api(
                        '/api/v2/analyses/%s/review' % current.get('analysis_id', ''),
                        method='POST',
                        data={'approved': True, 'feedback': ''},
                    )
                st.rerun()
        with revise_col:
            if st.button('提交修改意见', use_container_width=True):
                if not feedback.strip():
                    st.warning('请先填写修改意见')
                else:
                    with st.spinner('正在根据反馈调整计划...'):
                        st.session_state.current_result = call_api(
                            '/api/v2/analyses/%s/review' % current.get('analysis_id', ''),
                            method='POST',
                            data={'approved': False, 'feedback': feedback.strip()},
                        )
                    st.rerun()
        st.stop()

    # 使用Tabs展示不同内容
    tab1, tab2, tab3, tab4, tab5 = st.tabs(['分析结论', '查询结果', 'SQL / Python', '图表报告', '执行步骤'])

    with tab1:
        """分析结论"""
        analysis = current.get('summary') or current.get('analysis', '')
        if analysis:
            st.markdown(analysis)
        else:
            st.info('暂无分析结论')

    with tab2:
        """查询结果"""
        datasets = current.get('datasets', [])
        rows = current.get('data', [])
        if datasets:
            for dataset in datasets:
                st.markdown('**%s**' % dataset.get('name', 'dataset'))
                st.dataframe(dataset.get('rows', []), use_container_width=True)
        elif rows:
            st.dataframe(rows, use_container_width=True)
        else:
            st.info('无查询结果')

    with tab3:
        """执行SQL"""
        datasets = current.get('datasets', [])
        sql = current.get('generated_sql', '')
        if datasets:
            for dataset in datasets:
                st.markdown('**%s**' % dataset.get('name', 'dataset'))
                st.code(dataset.get('sql', ''), language='sql')
            if current.get('python_code'):
                st.markdown('**Python 分析代码**')
                st.code(current.get('python_code'), language='python')
        elif sql:
            st.code(sql, language='sql')
        else:
            st.info('未生成SQL')

    with tab4:
        report = current.get('report', {})
        if report:
            html_response = fetch_report(report.get('html_url', ''))
            markdown_response = fetch_report(report.get('markdown_url', ''))
            if html_response.ok:
                components.html(html_response.text, height=760, scrolling=True)
                st.download_button(
                    '下载 HTML 报告',
                    html_response.content,
                    file_name='analysis_report.html',
                    mime='text/html',
                    use_container_width=True,
                )
            if markdown_response.ok:
                st.download_button(
                    '下载 Markdown 报告',
                    markdown_response.content,
                    file_name='analysis_report.md',
                    mime='text/markdown',
                    use_container_width=True,
                )
            st.caption('图表数量: ' + str(report.get('chart_count', 0)))
        else:
            st.info('暂无报告')

    with tab5:
        """执行步骤"""
        steps = current.get('steps', [])
        if steps:
            for step in steps:
                step_name = step.get('step', '')
                detail = step.get('detail', '')
                step_status = step.get('status', '')
                timestamp = step.get('timestamp', '')
                icon = get_step_icon(step_status)
                st.markdown('%s **%s** — %s' % (icon, step_name, detail))
                st.caption(timestamp)
                st.divider()
        else:
            st.info('暂无执行步骤记录')

    # 会话信息
    with st.expander('会话信息'):
        st.caption('会话ID: ' + session_id)
        st.caption('查询耗时: %.2f ms' % current.get('query_duration_ms', 0))
        st.caption('返回行数: %d' % current.get('returned_rows', 0))


# ============================================================
# 历史记录
# ============================================================

with st.expander('查询历史记录'):
    if st.session_state.history:
        for i, record in enumerate(reversed(st.session_state.history)):
            col1, col2, col3 = st.columns([2, 3, 1])
            with col1:
                st.caption(record['time'])
            with col2:
                st.write(record['query'][:50] + ('...' if len(record['query']) > 50 else ''))
            with col3:
                status = record['result'].get('status', '')
                if status == 'success':
                    st.success(':white_check_mark: 成功')
                elif status == 'failed':
                    st.error(':x: 失败')
                elif status == 'intercepted':
                    st.warning(':warning: 拦截')
            st.divider()
    else:
        st.info('暂无查询历史')


# ============================================================
# 页脚
# ============================================================

st.markdown('---')
st.caption(
    ':lock: 所有数据脱敏处理 | '
    ':no_entry: 仅SELECT只读查询 | '
    ':page_facing_up: 完整审计日志 | '
    ':computer: 仅限内网访问'
)
