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

from fastapi import Depends, FastAPI, Header, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from security_middleware import is_ip_allowed, AuditLogger
from sql_agent_graph import run_agent
from advanced_agent_graph import advanced_data_analyst
from api_key_manager import api_key_manager
from conversation_store import analysis_task_store
from model_registry import ModelSpec, model_registry
from rag_store import rag_store
from report_generator import report_generator

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
    query_columns: List[str] = Field(default_factory=list, description='查询结果列名')
    returned_rows: int = Field(0, description='返回数据行数')
    query_duration_ms: float = Field(0.0, description='查询耗时（毫秒）')
    analysis: str = Field('', description='业务分析结论')
    data: List[Dict[str, Any]] = Field(default_factory=list, description='脱敏后的查询结果')
    steps: List[Dict[str, Any]] = Field(default_factory=list, description='执行步骤记录')
    error: str = Field('', description='错误信息（如有）')


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description='服务状态')
    version: str = Field(..., description='版本号')
    timestamp: str = Field(..., description='当前时间戳')
    uptime_seconds: float = Field(..., description='服务运行时长（秒）')


class AnalysisPlanRequest(BaseModel):
    user_query: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None


class AnalysisReviewRequest(BaseModel):
    approved: bool
    feedback: str = Field('', max_length=4000)


class RAGDocument(BaseModel):
    id: Optional[str] = None
    content: str = Field(..., min_length=1, max_length=20000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RAGUpsertRequest(BaseModel):
    documents: List[RAGDocument]
    namespace: str = Field('business', min_length=1, max_length=100)
    embedding_model: Optional[str] = None


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: List[str] = Field(default_factory=lambda: ['analysis'])
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650)


class ModelRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    kind: str = Field(..., pattern='^(chat|embedding|embedding-local)$')
    model: str = Field(..., min_length=1, max_length=200)
    api_base: str = ''
    api_key_env: str = ''
    dimensions: int = Field(256, ge=8, le=65536)


# ============================================================
# FastAPI 应用初始化
# ============================================================

# 服务启动时间
_start_time = time.time()

# 创建FastAPI应用
app = FastAPI(
    title='Enterprise AI Data Analyst API',
    description='基于 LangChain + LangGraph 的 Text-to-SQL、Python 深度分析、RAG 与智能报告服务',
    version='2.1.0',
    docs_url='/docs',
    redoc_url='/redoc',
)

# 配置CORS（仅允许内网来源）
cors_origins = [
    item.strip()
    for item in os.environ.get(
        'CORS_ALLOW_ORIGINS',
        'http://127.0.0.1:8501,http://localhost:8501',
    ).split(',')
    if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 审计日志记录器
audit_logger = AuditLogger()


def require_scope(scope: str):
    async def dependency(x_api_key: Optional[str] = Header(None, alias='X-API-Key')):
        if os.environ.get('API_KEY_AUTH_ENABLED', 'false').lower() != 'true':
            return {'id': 'auth-disabled', 'scopes': ['*']}
        identity = api_key_manager.verify(x_api_key or '', scope)
        if not identity:
            raise HTTPException(status_code=401, detail='API Key 无效、已过期或缺少权限: ' + scope)
        return identity
    return dependency


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
        version='2.1.0',
        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
        uptime_seconds=round(uptime, 2),
    )


@app.post('/api/query', response_model=QueryResponse, tags=['取数'], dependencies=[Depends(require_scope('query'))])
def execute_query(request: QueryRequest):
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
            data=result.get('data', []),
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
def get_audit_logs(lines: int = 50, _identity: Dict[str, Any] = Depends(require_scope('audit:read'))):
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


@app.post('/api/v2/analyses/plan', tags=['AI 数据分析师'])
def create_analysis_plan(
    request: AnalysisPlanRequest,
    _identity: Dict[str, Any] = Depends(require_scope('analysis')),
):
    try:
        return advanced_data_analyst.create_plan(
            request.user_query.strip(),
            request.session_id,
            request.chat_model,
            request.embedding_model,
        )
    except Exception as exc:
        logger.exception('生成分析计划失败')
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/v2/analyses/{analysis_id}/review', tags=['AI 数据分析师'])
def review_analysis_plan(
    analysis_id: str,
    request: AnalysisReviewRequest,
    _identity: Dict[str, Any] = Depends(require_scope('analysis')),
):
    try:
        return advanced_data_analyst.review_plan(
            analysis_id,
            request.approved,
            request.feedback.strip(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception('执行分析任务失败')
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/v2/analyses/{analysis_id}', tags=['AI 数据分析师'])
def get_analysis_task(
    analysis_id: str,
    _identity: Dict[str, Any] = Depends(require_scope('analysis')),
):
    try:
        return advanced_data_analyst.get_task(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _report_file(analysis_id: str, report_type: str) -> FileResponse:
    task = analysis_task_store.get(analysis_id)
    if not task or not task.get('report'):
        raise HTTPException(status_code=404, detail='报告尚未生成')
    key = 'html_path' if report_type == 'html' else 'markdown_path'
    path = os.path.abspath(task['report'].get(key, ''))
    root = os.path.abspath(report_generator.output_root)
    if not path or os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='报告文件不存在')
    media_type = 'text/html' if report_type == 'html' else 'text/markdown'
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))


@app.get('/api/v2/analyses/{analysis_id}/report/html', tags=['智能报告'])
def get_html_report(
    analysis_id: str,
    _identity: Dict[str, Any] = Depends(require_scope('reports:read')),
):
    return _report_file(analysis_id, 'html')


@app.get('/api/v2/analyses/{analysis_id}/report/markdown', tags=['智能报告'])
def get_markdown_report(
    analysis_id: str,
    _identity: Dict[str, Any] = Depends(require_scope('reports:read')),
):
    return _report_file(analysis_id, 'markdown')


@app.get('/api/v2/models', tags=['模型管理'])
def list_models(_identity: Dict[str, Any] = Depends(require_scope('models:read'))):
    return {'models': model_registry.list_models()}


@app.post('/api/v2/models', tags=['模型管理'])
def register_model(
    request: ModelRegistrationRequest,
    _identity: Dict[str, Any] = Depends(require_scope('admin')),
):
    try:
        model_registry.register(ModelSpec(**request.model_dump()))
        return {'registered': request.name, 'models': model_registry.list_models()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/v2/rag/sync', tags=['RAG'])
def sync_rag_metadata(
    embedding_model: Optional[str] = None,
    _identity: Dict[str, Any] = Depends(require_scope('rag:write')),
):
    try:
        return advanced_data_analyst.sync_metadata(embedding_model)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/v2/rag/documents', tags=['RAG'])
def upsert_rag_documents(
    request: RAGUpsertRequest,
    _identity: Dict[str, Any] = Depends(require_scope('rag:write')),
):
    count = rag_store.upsert(
        [item.model_dump() for item in request.documents],
        request.namespace,
        request.embedding_model,
    )
    return {'upserted': count, 'namespace': request.namespace}


@app.get('/api/v2/rag/search', tags=['RAG'])
def search_rag(
    query: str,
    top_k: int = 5,
    namespace: str = 'business',
    embedding_model: Optional[str] = None,
    _identity: Dict[str, Any] = Depends(require_scope('rag:read')),
):
    return {'results': rag_store.search(query, top_k, namespace, embedding_model)}


@app.post('/api/v2/api-keys', tags=['API Key 管理'])
def create_api_key(
    request: APIKeyCreateRequest,
    _identity: Dict[str, Any] = Depends(require_scope('admin')),
):
    token, metadata = api_key_manager.create_key(
        request.name,
        request.scopes,
        request.expires_in_days,
    )
    return {'api_key': token, 'metadata': metadata, 'warning': 'API Key 仅本次返回，请立即安全保存'}


@app.get('/api/v2/api-keys', tags=['API Key 管理'])
def list_api_keys(_identity: Dict[str, Any] = Depends(require_scope('admin'))):
    return {'keys': api_key_manager.list_keys()}


@app.delete('/api/v2/api-keys/{key_id}', tags=['API Key 管理'])
def revoke_api_key(
    key_id: str,
    _identity: Dict[str, Any] = Depends(require_scope('admin')),
):
    if not api_key_manager.revoke(key_id):
        raise HTTPException(status_code=404, detail='API Key 不存在或已撤销')
    return {'revoked': True, 'id': key_id}


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
    logger.info('企业 AI 智能数据分析师 v2.1.0 服务启动')
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
