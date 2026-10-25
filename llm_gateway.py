# -*- coding: utf-8 -*-
"""
大模型统一调用网关模块

功能：
  1. 封装国内DeepSeek（兼容OpenAI格式）API请求
  2. 数据发送前强制脱敏预处理
  3. 统一异常捕获与重试机制
  4. 所有配置从 .env 环境变量读取，无硬编码

设计原则：
  - 仅对接国内大模型API，不调用任何境外服务
  - 所有发送给大模型的数据提前脱敏
  - 原始业务明细永久仅保存在内网服务器
"""

import os
import json
import logging
import re
from typing import Optional, List, Dict, Any
from decimal import Decimal
from datetime import datetime, date

from langchain_openai import ChatOpenAI

from security_middleware import mask_sensitive_text, mask_dataframe

logger = logging.getLogger(__name__)

# JSON序列化辅助函数：处理Decimal等非标准JSON类型
def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return str(obj)
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')




# ============================================================
# 自定义异常类
# ============================================================


class LLMGatewayError(Exception):
    """大模型调用网关基础异常"""
    pass


class LLMRequestError(LLMGatewayError):
    """大模型API请求异常"""
    pass


class LLMResponseError(LLMGatewayError):
    """大模型API响应解析异常"""
    pass


# ============================================================
# LLM 网关核心类
# ============================================================


class LLMGateway:
    """
    大模型统一调用网关

    封装国内DeepSeek（兼容OpenAI格式）API的请求与响应处理，
    自动进行数据脱敏预处理。
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        request_timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        初始化LLM网关

        所有参数优先从构造参数读取，否则从环境变量读取

        Args:
            api_base: API地址，如 http://192.168.1.100:8000/v1
            api_key: API Key
            model_name: 模型名称
            request_timeout: 请求超时秒数
            max_retries: 最大重试次数
        """
        self.api_base = (api_base or os.environ.get('LLM_API_BASE', '')).rstrip('/')
        self.api_key = api_key or os.environ.get('LLM_API_KEY', '')
        self.model_name = model_name or os.environ.get('LLM_MODEL_NAME', 'deepseek-chat')
        self.request_timeout = request_timeout or int(os.environ.get('LLM_REQUEST_TIMEOUT', '60'))
        self.max_retries = max_retries or int(os.environ.get('LLM_MAX_RETRIES', '3'))

        # 校验必要配置
        if not self.api_base:
            raise LLMGatewayError('LLM_API_BASE 未配置，请在 .env 文件中设置')
        if not self.api_key:
            raise LLMGatewayError('LLM_API_KEY 未配置，请在 .env 文件中设置')

        # LangChain 统一模型接口；兼容 DeepSeek 等 OpenAI-compatible API。
        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.api_base,
            timeout=self.request_timeout,
            max_retries=self.max_retries,
        )

        logger.info(
            'LLM网关初始化完成，API地址: %s, 模型: %s, 超时: %ds, 最大重试: %d',
            self.api_base, self.model_name, self.request_timeout, self.max_retries
        )

    def _mask_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        对发送给大模型的消息进行脱敏预处理

        确保所有敏感数据在离开内网前已被脱敏

        Args:
            messages: 原始消息列表

        Returns:
            脱敏后的消息列表
        """
        masked_messages = []
        for msg in messages:
            masked_msg = {}
            for key, value in msg.items():
                if isinstance(value, str):
                    masked_msg[key] = mask_sensitive_text(value)
                else:
                    masked_msg[key] = value
            masked_messages.append(masked_msg)
        return masked_messages

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        enable_mask: bool = True,
    ) -> Dict[str, Any]:
        """
        调用大模型API进行对话

        Args:
            messages: 对话消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 生成温度，取数场景建议低值（0.1）
            max_tokens: 最大生成token数
            enable_mask: 是否启用数据脱敏预处理（默认开启）

        Returns:
            API响应字典，包含 content 等字段

        Raises:
            LLMRequestError: API请求失败
            LLMResponseError: 响应解析失败
        """
        # 数据脱敏预处理（发送前强制脱敏）
        if enable_mask:
            messages = self._mask_messages(messages)

        try:
            response = self._client.bind(
                temperature=temperature,
                max_tokens=max_tokens,
            ).invoke(messages)
            raw_content = response.content
            if isinstance(raw_content, str):
                content = raw_content.strip()
            else:
                content = json.dumps(raw_content, ensure_ascii=False, default=str)
            if not content:
                raise LLMResponseError('LangChain 模型响应为空')

            metadata = response.response_metadata or {}
            usage = response.usage_metadata or metadata.get('token_usage', {})
            logger.info('LangChain 模型调用成功，生成内容长度: %d', len(content))
            return {
                'content': content,
                'finish_reason': metadata.get('finish_reason', 'stop'),
                'usage': usage,
                'model': metadata.get('model_name', self.model_name),
            }
        except LLMGatewayError:
            raise
        except Exception as exc:
            logger.exception('LangChain 模型调用失败')
            raise LLMRequestError('LangChain 模型调用失败: %s' % exc) from exc

    def extract_sql_from_response(self, content: str) -> Optional[str]:
        """
        从大模型响应中提取SQL语句

        支持格式：
          - ```sql ... ``` 代码块
          - ``` ... ``` 代码块
          - 纯文本SQL（直接返回）

        Args:
            content: 大模型返回的文本内容

        Returns:
            提取的SQL语句，未找到则返回 None
        """
        if not content:
            return None

        # 尝试匹配 ```sql ... ``` 代码块
        sql_block_pattern = re.compile(
            r'```(?:sql|SQL)?\s*\n?(.*?)```',
            re.DOTALL
        )
        match = sql_block_pattern.search(content)
        if match:
            sql = match.group(1).strip()
            if sql:
                return sql

        # 尝试匹配 ``` ... ``` 代码块（不指定语言）
        code_block_pattern = re.compile(r'```\s*\n?(.*?)```', re.DOTALL)
        match = code_block_pattern.search(content)
        if match:
            sql = match.group(1).strip()
            if sql and sql.upper().startswith(('SELECT', 'WITH')):
                return sql

        # 如果内容本身看起来是SQL，直接返回
        content_stripped = content.strip()
        if content_stripped.upper().startswith(('SELECT', 'WITH')):
            return content_stripped

        return None

    def generate_analysis(
        self,
        user_query: str,
        sql: str,
        query_result: List[Dict[str, Any]],
        columns: List[str],
    ) -> str:
        """
        基于脱敏后的查询结果，让大模型生成业务分析结论

        Args:
            user_query: 用户原始提问
            sql: 执行的SQL语句
            query_result: 脱敏后的查询结果数据
            columns: 查询结果列名列表

        Returns:
            大模型生成的分析结论文本
        """
        # 对查询结果再次脱敏（确保安全）
        safe_result = mask_dataframe(query_result)

        # 构建分析提示词
        system_prompt = (
            '你是一名专业的企业数据分析师。请根据用户的问题、执行的SQL语句以及查询结果，'
            '生成一份通俗易懂的业务分析结论。\n\n'
            '要求：\n'
            '1. 用中文回答，语言简洁明了\n'
            '2. 直接给出业务结论，不要重复SQL语句\n'
            '3. 如果数据中有异常值或明显问题，请指出\n'
            '4. 如果数据为空，请如实说明\n'
            '5. 不要编造数据，只基于提供的结果进行分析\n'
        )

        user_prompt = (
            f'用户问题：{user_query}\n\n'
            f'执行的SQL：{sql}\n\n'
            f'查询结果列：{columns}\n\n'
            f'查询结果（共{len(safe_result)}行）：\n'
            f'{json.dumps(safe_result, ensure_ascii=False, indent=2, default=_json_default)}\n\n'
            f'请给出业务分析结论：'
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]

        response = self.chat(messages, temperature=0.3, max_tokens=4096)
        return response['content']


# ============================================================
# 便捷函数：快速获取LLM网关实例
# ============================================================


def get_llm_gateway() -> LLMGateway:
    """
    获取LLM网关实例（单例模式）

    从环境变量读取配置，快速创建网关实例

    Returns:
        LLMGateway 实例
    """
    return LLMGateway()
