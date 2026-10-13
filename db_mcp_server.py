# -*- coding: utf-8 -*-
"""
数据库MCP工具服务模块

功能：
  1. 查询数据库全部表名
  2. 查询指定表的字段名、字段类型、字段注释
  3. 执行只读SQL查询（前置安全校验拦截）
  4. 单次查询限制最大返回行数

通信方式：
  - FastMCP stdio 本地进程通信
  - 不对外暴露额外端口，降低内网安全风险

设计原则：
  - 仅使用只读数据库账号
  - 所有SQL执行前经过安全校验
  - 查询结果自动限制行数
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

# 加载 .env 环境变量
from dotenv import load_dotenv
load_dotenv()

import pymysql
from pymysql.cursors import DictCursor

from security_middleware import validate_sql, AuditLogger

logger = logging.getLogger(__name__)


# ============================================================
# 数据库连接管理
# ============================================================


class DatabaseManager:
    """
    数据库连接管理器

    负责MySQL数据库连接的创建、查询执行和资源释放。
    所有配置从环境变量读取，不硬编码任何敏感信息。
    """

    def __init__(self):
        """初始化数据库连接配置（从环境变量读取）"""
        self.host = os.environ.get('DB_HOST', '127.0.0.1')
        self.port = int(os.environ.get('DB_PORT', '3306'))
        self.database = os.environ.get('DB_NAME', '')
        self.user = os.environ.get('DB_USER', '')
        self.password = os.environ.get('DB_PASSWORD', '')
        self.charset = os.environ.get('DB_CHARSET', 'utf8mb4')
        self.connect_timeout = int(os.environ.get('DB_CONNECT_TIMEOUT', '10'))
        self.max_rows = int(os.environ.get('QUERY_MAX_ROWS', '50'))

        # 校验必要配置
        if not all([self.host, self.database, self.user]):
            raise ValueError(
                '数据库配置不完整，请检查 .env 文件中的 DB_HOST / DB_NAME / DB_USER 配置'
            )

    def _get_connection(self) -> pymysql.Connection:
        """
        创建数据库连接

        Returns:
            pymysql.Connection 对象
        """
        connection = pymysql.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            charset=self.charset,
            connect_timeout=self.connect_timeout,
            cursorclass=DictCursor,
            # 强制只读设置
            autocommit=False,
            # 禁止自动提交，防止意外写入
        )
        return connection

    def get_table_names(self) -> List[str]:
        """
        获取数据库中所有表名

        Returns:
            表名列表
        """
        connection = None
        try:
            connection = self._get_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                               "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' "
                               "ORDER BY TABLE_NAME", (self.database,))
                results = cursor.fetchall()
                tables = [row['TABLE_NAME'] for row in results]
                logger.info('获取到 %d 张数据表', len(tables))
                return tables
        except pymysql.Error as e:
            error_msg = f'查询表名失败: {e}'
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        finally:
            if connection:
                connection.close()

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """
        获取指定表的字段信息

        Args:
            table_name: 表名

        Returns:
            字段信息列表，每项包含：
            - Field: 字段名
            - Type: 字段类型
            - Null: 是否可为空
            - Key: 索引类型
            - Default: 默认值
            - Extra: 额外信息
            - Comment: 字段注释
        """
        connection = None
        try:
            connection = self._get_connection()
            with connection.cursor() as cursor:
                cursor.execute("SHOW FULL COLUMNS FROM `{}`".format(
                    table_name.replace('`', '``')
                ))
                results = cursor.fetchall()
                logger.info('获取表 %s 的字段信息，共 %d 个字段', table_name, len(results))
                return results
        except pymysql.Error as e:
            error_msg = f'查询表结构失败（{table_name}）: {e}'
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        finally:
            if connection:
                connection.close()

    def execute_query(self, sql: str) -> Tuple[List[Dict[str, Any]], List[str], float]:
        """
        执行只读SQL查询

        流程：
          1. 前置安全校验（拦截高危SQL）
          2. 执行查询
          3. 限制返回行数

        Args:
            sql: 待执行的SQL语句

        Returns:
            (rows: List[Dict], columns: List[str], duration_ms: float)
            - rows: 查询结果行列表
            - columns: 列名列表
            - duration_ms: 查询耗时（毫秒）

        Raises:
            ValueError: SQL安全校验未通过
            RuntimeError: 数据库执行异常
        """
        # 前置安全校验
        is_safe, error_msg = validate_sql(sql)
        if not is_safe:
            raise ValueError(f'SQL安全校验未通过: {error_msg}')

        connection = None
        start_time = time.time()

        try:
            connection = self._get_connection()
            with connection.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchmany(self.max_rows)

            duration_ms = round((time.time() - start_time) * 1000, 2)

            # 提取列名
            columns = list(results[0].keys()) if results else []

            logger.info(
                '查询执行成功，返回 %d 行，耗时 %.2fms',
                len(results), duration_ms
            )

            return results, columns, duration_ms

        except pymysql.Error as e:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            error_msg = f'SQL执行失败: {e}'
            logger.error('%s（耗时 %.2fms）', error_msg, duration_ms)
            raise RuntimeError(error_msg)

        finally:
            if connection:
                connection.close()


# ============================================================
# FastMCP 服务定义（stdio 本地进程通信）
# ============================================================

# 全局数据库管理器实例
_db_manager: Optional[DatabaseManager] = None
_audit_logger: Optional[AuditLogger] = None


def get_db_manager() -> DatabaseManager:
    """获取数据库管理器单例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器单例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# ============================================================
# MCP 工具函数（供 FastMCP 注册）
# ============================================================


def mcp_list_tables() -> Dict[str, Any]:
    """
    MCP工具：获取数据库中所有表名

    Returns:
        {"success": True, "tables": [...], "count": N}
        或 {"success": False, "error": "..."}
    """
    try:
        db = get_db_manager()
        tables = db.get_table_names()
        return {
            'success': True,
            'tables': tables,
            'count': len(tables),
        }
    except Exception as e:
        logger.error('MCP list_tables 失败: %s', e)
        return {
            'success': False,
            'error': str(e),
        }


def mcp_describe_table(table_name: str) -> Dict[str, Any]:
    """
    MCP工具：获取指定表的字段信息

    Args:
        table_name: 表名

    Returns:
        {"success": True, "table_name": "...", "columns": [...]}
        或 {"success": False, "error": "..."}
    """
    try:
        db = get_db_manager()
        schema = db.get_table_schema(table_name)
        # 格式化输出
        columns = []
        for col in schema:
            columns.append({
                'field': col.get('Field', ''),
                'type': col.get('Type', ''),
                'nullable': col.get('Null', 'YES') == 'YES',
                'key': col.get('Key', ''),
                'default': col.get('Default', None),
                'comment': col.get('Comment', ''),
            })
        return {
            'success': True,
            'table_name': table_name,
            'columns': columns,
            'count': len(columns),
        }
    except Exception as e:
        logger.error('MCP describe_table 失败: %s', e)
        return {
            'success': False,
            'error': str(e),
        }


def mcp_execute_query(sql: str, user_query: str = '') -> Dict[str, Any]:
    """
    MCP工具：执行只读SQL查询

    流程：
      1. 安全校验SQL
      2. 执行查询
      3. 记录审计日志

    Args:
        sql: SQL语句
        user_query: 用户原始提问（用于审计日志）

    Returns:
        {"success": True, "columns": [...], "rows": [...], "row_count": N, "duration_ms": N}
        或 {"success": False, "error": "..."}
    """
    audit = get_audit_logger()
    operation_time = time.strftime('%Y-%m-%d %H:%M:%S')

    try:
        # 安全校验
        is_safe, error_msg = validate_sql(sql)
        if not is_safe:
            # 记录拦截日志
            audit.log({
                'user_query': user_query,
                'generated_sql': sql,
                'query_duration_ms': 0,
                'returned_rows': 0,
                'operation_time': operation_time,
                'status': 'intercepted',
                'error_message': error_msg,
            })
            return {
                'success': False,
                'error': error_msg,
                'intercepted': True,
            }

        # 执行查询
        db = get_db_manager()
        rows, columns, duration_ms = db.execute_query(sql)

        # 记录成功日志
        audit.log({
            'user_query': user_query,
            'generated_sql': sql,
            'query_duration_ms': duration_ms,
            'returned_rows': len(rows),
            'operation_time': operation_time,
            'status': 'success',
        })

        return {
            'success': True,
            'columns': columns,
            'rows': rows,
            'row_count': len(rows),
            'duration_ms': duration_ms,
        }

    except ValueError as e:
        # 安全校验异常
        audit.log({
            'user_query': user_query,
            'generated_sql': sql,
            'query_duration_ms': 0,
            'returned_rows': 0,
            'operation_time': operation_time,
            'status': 'failed',
            'error_message': str(e),
        })
        return {
            'success': False,
            'error': str(e),
        }

    except Exception as e:
        # 执行异常
        error_msg = str(e)
        audit.log({
            'user_query': user_query,
            'generated_sql': sql,
            'query_duration_ms': 0,
            'returned_rows': 0,
            'operation_time': operation_time,
            'status': 'failed',
            'error_message': error_msg,
        })
        return {
            'success': False,
            'error': error_msg,
        }


# ============================================================
# FastMCP 服务启动入口
# ============================================================


def create_mcp_server():
    """
    创建并配置 FastMCP 服务实例

    使用 stdio 传输方式，不对外暴露端口

    Returns:
        FastMCP 服务实例
    """
    try:
        from mcp.server.fastmcp import FastMCP

        # 创建MCP服务实例
        mcp = FastMCP(
            'db-query-agent',
            description='企业内网数据库查询MCP服务 - 仅支持只读SELECT操作',
        )

        # 注册工具
        @mcp.tool()
        def list_tables() -> Dict[str, Any]:
            """获取数据库中所有数据表名列表"""
            return mcp_list_tables()

        @mcp.tool()
        def describe_table(table_name: str) -> Dict[str, Any]:
            """获取指定表的字段名、字段类型、字段注释等结构信息"""
            return mcp_describe_table(table_name)

        @mcp.tool()
        def execute_query(sql: str, user_query: str = '') -> Dict[str, Any]:
            """执行只读SELECT查询，自动校验安全性和限制返回行数"""
            return mcp_execute_query(sql, user_query)

        logger.info('FastMCP 服务创建完成，传输方式: stdio')
        return mcp

    except ImportError as e:
        logger.error('导入 FastMCP 失败，请安装 mcp 包: %s', e)
        raise


def run_mcp_server():
    """
    启动MCP服务（stdio模式）

    此函数供主进程调用，以子进程方式启动MCP服务
    """
    mcp = create_mcp_server()
    logger.info('MCP服务启动，传输方式: stdio')
    # 以stdio模式运行
    mcp.run(transport='stdio')


# ============================================================
# 直接运行入口（调试用）
# ============================================================

if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
    logger.info('启动数据库MCP服务（stdio模式）...')
    run_mcp_server()
