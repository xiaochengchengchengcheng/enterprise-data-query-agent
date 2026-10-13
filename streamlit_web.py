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
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, timeout=30)
        else:
            resp = requests.post(url, json=data, timeout=300)  # 取数请求可能耗时较长
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'error': '无法连接到后端服务，请确认 FastAPI 服务已启动'}
    except requests.exceptions.Timeout:
        return {'status': 'error', 'error': '请求超时，请稍后重试'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


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
    st.title(':bar_chart: 取数智能体')
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
    st.caption('企业内网自主取数智能体 v1.0.0')


# ============================================================
# 主页面
# ============================================================

st.title(':bar_chart: 企业内网自主取数智能体')
st.markdown('输入您的业务需求，AI自动完成查表、生成SQL、执行查询、数据分析全流程')

# 输入区域
col1, col2 = st.columns([4, 1])
with col1:
    user_query = st.text_input(
        '请输入您的取数需求',
        placeholder='例如：查询上个月各地区的销售额排名',
        label_visibility='collapsed',
    )
with col2:
    submit_btn = st.button('开始取数', type='primary', use_container_width=True)

# 会话历史（使用st.session_state保持状态）
if 'history' not in st.session_state:
    st.session_state.history = []

if 'current_result' not in st.session_state:
    st.session_state.current_result = None


# ============================================================
# 处理取数请求
# ============================================================

if submit_btn and user_query.strip():
    with st.spinner('智能体正在处理您的请求...'):
        # 调用后端API
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
    if status == 'success':
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

    # 使用Tabs展示不同内容
    tab1, tab2, tab3, tab4 = st.tabs(['分析结论', '查询结果', '执行SQL', '执行步骤'])

    with tab1:
        """分析结论"""
        analysis = current.get('analysis', '')
        if analysis:
            st.markdown(analysis)
        else:
            st.info('暂无分析结论')

    with tab2:
        """查询结果"""
        columns = current.get('query_columns', [])
        returned_rows = current.get('returned_rows', 0)

        if columns:
            st.caption('返回 %d 行数据（已脱敏）' % returned_rows)
            st.caption('列名: ' + ', '.join(columns))
            # 注意：实际数据通过API获取，这里仅展示元信息
            st.info('详细数据请查看审计日志或通过API获取')
        else:
            st.info('无查询结果')

    with tab3:
        """执行SQL"""
        sql = current.get('generated_sql', '')
        if sql:
            st.code(sql, language='sql')
        else:
            st.info('未生成SQL')

    with tab4:
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