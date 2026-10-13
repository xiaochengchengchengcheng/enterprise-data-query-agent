# -*- coding: utf-8 -*-
"""
FastAPI 统一后端接口服务

功能：
  1. 串联全部模块，提供内网RESTful API接口
  2. 内网IP白名单访问限制
  3. 健康检查与状态监控
  4. 多用户并发请求处理

设计原则：
  - 所有配置从 .env 环境变量读取
  - 仅监听内网IP，屏蔽公网访问
  - 跨平台兼容（Windows / Linux）
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, Optional, List

# 加载 .env 环境变量（必须在其他模块导入之前执行）
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from security_middleware import is_ip_allowed, AuditLogger
from sql_agent_graph import run_agent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


# ============================================================
# 请求/响应模型定义
# ============================================================


class QueryRequest(BaseModel):
    """取数查询请求模型"""
    user_query: str = Field(..., description='用户自然语言取数需求', min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, description='会话ID（可选，不传则自动生成）')


class QueryResponse(BaseModel):
    """取数查询响应模型"""
    status: str = Field(..., description='状态: success / failed / intercepted')
    session_id: str = Field(..., description='会话ID')
    user_query: str = Field(..., description='用户原始提问')
    generated_sql: str = Field('', description='生成的SQL语句')
    query_columns: List[str] = Field([], description='查询结果列名')
    returned_rows: int = Field(0, description='返回数据行数')
    query_duration_ms: float = Field(0.0, description='查询耗时（毫秒）')
    analysis: str = Field('', description='业务分析结论')
    steps: List[Dict[str, Any]] = Field([], description='执行步骤记录')
    error: str = Field('', description='错误信息（如有）')


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description='服务状态')
    version: str = Field(..., description='版本号')
    timestamp: str = Field(..., description='当前时间戳')
    uptime_seconds: float = Field(..., description='服务运行时长（秒）')


# ============================================================
# FastAPI 应用初始化
# ============================================================

# 服务启动时间
_start_time = time.time()

# 创建FastAPI应用
app = FastAPI(
    title='企业内网自主取数智能体 API',
    description='基于LangGraph + DeepSeek的企业内网智能取数服务，仅限内网访问',
    version='1.0.0',
    docs_url='/docs',
    redoc_url='/redoc',
)

# 配置CORS（仅允许内网来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # 实际由IP白名单控制
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 审计日志记录器
audit_logger = AuditLogger()


# ============================================================
# IP白名单中间件
# ============================================================


@app.middleware('http')
async def ip_whitelist_middleware(request: Request, call_next):
    """
    IP白名单校验中间件

    屏蔽所有公网访问，仅允许内网IP白名单中的地址访问
    """
    # 放行健康检查端点
    if request.url.path in ['/health', '/docs', '/openapi.json', '/redoc']:
        response = await call_next(request)
        return response

    # 获取客户端IP
    client_ip = request.client.host if request.client else 'unknown'

    # 检查X-Forwarded-For（内网代理场景）
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        client_ip = forwarded.split(',')[0].strip()

    # IP白名单校验
    if not is_ip_allowed(client_ip):
        logger.warning('IP白名单拦截: %s -> %s', client_ip, request.url.path)
        return JSONResponse(
            status_code=403,
            content={
                'detail': '访问被拒绝：IP地址不在内网白名单中',
                'client_ip': client_ip,
            },
        )

    # 继续处理请求
    response = await call_next(request)
    return response


# ============================================================
# API 路由
# ============================================================


@app.get('/health', response_model=HealthResponse, tags=['系统'])
async def health_check():
    """
    健康检查接口

    返回服务运行状态、版本号、运行时长等信息
    """
    uptime = time.time() - _start_time
    return HealthResponse(
        status='running',
        version='1.0.0',
        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
        uptime_seconds=round(uptime, 2),
    )


@app.post('/api/query', response_model=QueryResponse, tags=['取数'])
async def execute_query(request: QueryRequest):
    """
    执行取数查询

    接收用户自然语言需求，启动Agent自主取数流程，
    返回SQL、脱敏数据和业务分析结论。

    Args:
        request: 查询请求体

    Returns:
        包含完整取数结果的响应
    """
    user_query = request.user_query.strip()
    session_id = request.session_id or str(uuid.uuid4())

    logger.info('收到取数请求 | session: %s | query: %s', session_id, user_query[:100])

    try:
        # 启动Agent取数流程
        result = run_agent(user_query, session_id)

        # 构建响应
        response = QueryResponse(
            status=result.get('status', 'failed'),
            session_id=result.get('session_id', session_id),
            user_query=result.get('user_query', user_query),
            generated_sql=result.get('generated_sql', ''),
            query_columns=result.get('query_columns', []),
            returned_rows=result.get('returned_rows', 0),
            query_duration_ms=result.get('query_duration_ms', 0),
            analysis=result.get('analysis', ''),
            steps=result.get('steps', []),
            error=result.get('error', ''),
        )

        logger.info('取数请求完成 | session: %s | status: %s', session_id, response.status)
        return response

    except Exception as e:
        logger.error('取数请求异常 | session: %s | error: %s', session_id, e)
        return QueryResponse(
            status='failed',
            session_id=session_id,
            user_query=user_query,
            error='服务器内部错误: ' + str(e),
        )


@app.get('/api/history', tags=['审计'])
async def get_audit_logs(lines: int = 50):
    """
    获取审计日志（最近N行）

    Args:
        lines: 返回行数，默认50行

    Returns:
        审计日志内容列表
    """
    log_path = audit_logger.get_log_path()
    if not os.path.exists(log_path):
        return {'logs': [], 'total': 0}

    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        recent_lines = all_lines[-lines:]
        return {
            'logs': [line.strip() for line in recent_lines],
            'total': len(all_lines),
            'returned': len(recent_lines),
        }
    except Exception as e:
        return {'logs': [], 'total': 0, 'error': str(e)}


# ============================================================
# 服务启动入口
# ============================================================


def start_server():
    """
    启动FastAPI服务

    使用 uvicorn 启动，监听配置的地址和端口
    """
    import uvicorn

    host = os.environ.get('SERVER_HOST', '0.0.0.0')
    port = int(os.environ.get('SERVER_PORT', '8000'))

    logger.info('=' * 50)
    logger.info('企业内网自主取数智能体服务启动')
    logger.info('监听地址: %s:%d', host, port)
    logger.info('API文档: http://%s:%d/docs', host if host != '0.0.0.0' else '127.0.0.1', port)
    logger.info('=' * 50)

    uvicorn.run(
        'fastapi_server:app',
        host=host,
        port=port,
        reload=False,
        log_level='info',
    )


if __name__ == '__main__':
    start_server()