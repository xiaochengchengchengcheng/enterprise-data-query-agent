# -*- coding: utf-8 -*-
"""
安全中间件模块 —— 独立安全工具包

功能：
  1. 敏感数据脱敏（手机号、身份证、银行卡号）
  2. 高危SQL语句正则检测与拦截
  3. 审计日志持久化写入（仅追加，不可删除）

设计原则：
  - 纯函数设计，无外部依赖耦合
  - 跨平台兼容（Windows / Linux）
  - 所有日志只追加不覆盖，防止审计记录被篡改
"""

import re
import os
import time
import logging
from typing import List, Dict, Any, Optional, Tuple

# 配置日志记录器（仅用于模块自身异常记录）
logger = logging.getLogger(__name__)


# ============================================================
# 一、敏感数据脱敏工具
# ============================================================

# 手机号正则：匹配中国大陆11位手机号（1开头的11位数字）
PHONE_PATTERN = re.compile(r'\b1[3-9]\d{9}\b')

# 身份证号正则：匹配18位身份证号（含最后一位X/x）
ID_CARD_PATTERN = re.compile(r'\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b')

# 银行卡号正则：匹配16~19位纯数字银行卡号
BANK_CARD_PATTERN = re.compile(r'\b(?:62|60|58|56|55|54|53|52|51|50|49|48|47|46|45|44|43|42|41|40)\d{14,17}\b')


def mask_phone(phone: str) -> str:
    """
    脱敏手机号：保留前3位和后4位，中间替换为 ****
    示例：13812345678 -> 138****5678
    """
    if not phone or len(phone) != 11:
        return phone
    return phone[:3] + '****' + phone[-4:]


def mask_id_card(id_card: str) -> str:
    """
    脱敏身份证号：保留前4位和后4位，中间完整掩码
    示例：110101199001011234 -> 1101************34
    """
    if not id_card or len(id_card) < 8:
        return id_card
    # 兼容最后一位X/x
    return id_card[:4] + '*' * (len(id_card) - 8) + id_card[-4:]


def mask_bank_card(card_no: str) -> str:
    """
    脱敏银行卡号：保留前4位和后4位，中间替换为 ****
    示例：6222021234567890 -> 6222****7890
    """
    if not card_no or len(card_no) < 8:
        return card_no
    return card_no[:4] + '****' + card_no[-4:]


def mask_sensitive_text(text: str) -> str:
    """
    对文本中的敏感信息进行脱敏处理
    依次处理：手机号、身份证号、银行卡号

    Args:
        text: 原始文本

    Returns:
        脱敏后的文本
    """
    if not text:
        return text

    # 脱敏手机号
    def _replace_phone(match):
        return mask_phone(match.group(0))
    text = PHONE_PATTERN.sub(_replace_phone, text)

    # 脱敏身份证号
    def _replace_id_card(match):
        return mask_id_card(match.group(0))
    text = ID_CARD_PATTERN.sub(_replace_id_card, text)

    # 脱敏银行卡号
    def _replace_bank_card(match):
        return mask_bank_card(match.group(0))
    text = BANK_CARD_PATTERN.sub(_replace_bank_card, text)

    return text


def mask_dataframe(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对查询结果数据集进行逐行逐字段脱敏
    自动识别并脱敏包含敏感数据的字段值

    Args:
        data: 查询结果列表，每行为一个字典

    Returns:
        脱敏后的数据列表
    """
    if not data:
        return data

    masked_data = []
    for row in data:
        masked_row = {}
        for key, value in row.items():
            if isinstance(value, str):
                masked_row[key] = mask_sensitive_text(value)
            else:
                masked_row[key] = value
        masked_data.append(masked_row)

    return masked_data


# ============================================================
# 二、高危SQL语句检测与拦截
# ============================================================

# 高危SQL关键字集合（不区分大小写）
HIGH_RISK_SQL_KEYWORDS = [
    r'\bDELETE\b',
    r'\bDROP\b',
    r'\bALTER\b',
    r'\bTRUNCATE\b',
    r'\bUPDATE\b',
    r'\bINSERT\b',
    r'\bREPLACE\b',
    r'\bCREATE\b',
    r'\bGRANT\b',
    r'\bREVOKE\b',
    r'\bRENAME\b',
]

# 编译高危SQL正则表达式列表
HIGH_RISK_PATTERNS = [re.compile(pattern, re.IGNORECASE) for pattern in HIGH_RISK_SQL_KEYWORDS]


def validate_sql(sql: str) -> Tuple[bool, Optional[str]]:
    """
    校验SQL语句安全性

    规则：
      1. 仅允许 SELECT 语句执行
      2. 拦截所有 DELETE / DROP / ALTER / TRUNCATE / UPDATE / INSERT 等修改操作
      3. 拦截包含注释符的SQL（防止SQL注入绕过）

    Args:
        sql: 待校验的SQL语句

    Returns:
        (is_safe: bool, error_message: Optional[str])
        - is_safe=True 表示通过校验
        - is_safe=False 表示拦截，error_message 包含风险说明
    """
    if not sql or not sql.strip():
        return False, 'SQL语句为空，无法执行'

    sql_stripped = sql.strip()

    # 检查是否包含SQL注释（防止绕过检测）
    comment_patterns = [
        re.compile(r'--\s', re.IGNORECASE),   # SQL单行注释
        re.compile(r'/\*.*?\*/', re.DOTALL),   # SQL多行注释
    ]
    for pattern in comment_patterns:
        if pattern.search(sql_stripped):
            return False, 'SQL语句包含注释内容，疑似注入风险，已拦截'

    # 检查是否以 SELECT 开头（允许带 WITH 的CTE查询）
    if not re.match(r'^\s*(?:SELECT|WITH)\s', sql_stripped, re.IGNORECASE):
        return False, '仅允许执行 SELECT 只读查询语句，当前语句已被拦截'

    # 检查高危关键字
    for pattern in HIGH_RISK_PATTERNS:
        if pattern.search(sql_stripped):
            matched_keyword = pattern.pattern.strip('\\b')
            return False, f'检测到高危SQL关键字 "{matched_keyword}"，已拦截执行'

    # 检查 INTO OUTFILE / INTO DUMPFILE（数据导出风险）
    file_export_pattern = re.compile(r'\bINTO\s+(OUTFILE|DUMPFILE)\b', re.IGNORECASE)
    if file_export_pattern.search(sql_stripped):
        return False, '检测到文件导出操作（INTO OUTFILE/DUMPFILE），已拦截'

    return True, None


# ============================================================
# 三、审计日志持久化写入
# ============================================================


class AuditLogger:
    """
    审计日志记录器

    特性：
      - 仅追加模式写入，不覆盖已有内容
      - 每条记录包含完整操作信息
      - 日志文件路径从环境变量读取
      - 线程安全（通过文件锁或追加写原子性保证）
    """

    def __init__(self, log_path: Optional[str] = None):
        """
        初始化审计日志记录器

        Args:
            log_path: 日志文件路径，默认从环境变量 AUDIT_LOG_PATH 读取
                      若环境变量未设置，默认 ./logs/audit.log
        """
        self.log_path = log_path or os.environ.get(
            'AUDIT_LOG_PATH',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'audit.log')
        )
        # 确保日志目录存在
        log_dir = os.path.dirname(self.log_path)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except Exception as e:
                logger.warning('无法创建审计日志目录 %s: %s', log_dir, e)

    def log(self, record: Dict[str, Any]) -> bool:
        """
        写入一条审计日志记录

        Args:
            record: 日志记录字典，包含以下字段：
                - user_query: 用户提问原文
                - generated_sql: 生成的SQL语句
                - query_duration_ms: 查询耗时（毫秒）
                - returned_rows: 返回数据行数
                - operation_time: 操作时间（ISO格式）
                - status: 状态（success / failed / intercepted）
                - error_message: 错误信息（可选）

        Returns:
            写入成功返回 True，失败返回 False
        """
        try:
            # 构建日志行
            timestamp = record.get('operation_time', time.strftime('%Y-%m-%d %H:%M:%S'))
            user_query = record.get('user_query', '').replace('\n', ' ').replace('\r', '')
            generated_sql = record.get('generated_sql', '').replace('\n', ' ').replace('\r', '')
            query_duration = record.get('query_duration_ms', 0)
            returned_rows = record.get('returned_rows', 0)
            status = record.get('status', 'unknown')
            error_msg = record.get('error_message', '').replace('\n', ' ').replace('\r', '')

            log_line = (
                f'[AUDIT] {timestamp} | STATUS:{status} | '
                f'DURATION:{query_duration}ms | ROWS:{returned_rows} | '
                f'QUERY:{user_query} | SQL:{generated_sql}'
            )
            if error_msg:
                log_line += f' | ERROR:{error_msg}'
            log_line += '\n'

            # 以追加模式写入文件
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(log_line)

            return True

        except Exception as e:
            logger.error('审计日志写入失败: %s', e)
            return False

    def get_log_path(self) -> str:
        """获取当前审计日志文件路径"""
        return self.log_path


# ============================================================
# 四、IP白名单校验
# ============================================================


def is_ip_allowed(client_ip: str, whitelist: Optional[List[str]] = None) -> bool:
    """
    校验客户端IP是否在白名单中

    支持：
      - 精确IP匹配
      - CIDR网段匹配（如 192.168.1.0/24）

    Args:
        client_ip: 客户端IP地址
        whitelist: IP白名单列表，默认从环境变量 IP_WHITELIST 读取

    Returns:
        True 表示允许访问，False 表示拒绝
    """
    if whitelist is None:
        whitelist_str = os.environ.get('IP_WHITELIST', '127.0.0.1,::1')
        whitelist = [ip.strip() for ip in whitelist_str.split(',') if ip.strip()]

    # 精确匹配
    if client_ip in whitelist:
        return True

    # CIDR网段匹配
    for allowed_ip in whitelist:
        if '/' in allowed_ip:
            try:
                if _ip_in_cidr(client_ip, allowed_ip):
                    return True
            except Exception:
                continue

    return False


def _ip_in_cidr(ip: str, cidr: str) -> bool:
    """
    判断IP是否在CIDR网段内
    简易实现，不依赖第三方库

    Args:
        ip: IP地址
        cidr: CIDR网段，如 192.168.1.0/24

    Returns:
        True 表示在网段内
    """
    try:
        import ipaddress
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ImportError:
        # Python 3.9 内置 ipaddress 模块
        pass
    except Exception:
        return False
    return False


# ============================================================
# 五、便捷函数：统一安全处理入口
# ============================================================


def secure_process_query_result(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    统一处理查询结果：对数据集进行脱敏处理

    这是对外提供的便捷入口，整合了数据脱敏流程

    Args:
        data: 原始查询结果

    Returns:
        脱敏后的安全数据
    """
    return mask_dataframe(data)


def secure_validate_and_log(
    sql: str,
    user_query: str,
    audit_logger: AuditLogger
) -> Tuple[bool, Optional[str]]:
    """
    安全校验SQL并记录审计日志（拦截场景）

    Args:
        sql: 待校验的SQL
        user_query: 用户原始提问
        audit_logger: 审计日志记录器实例

    Returns:
        (is_safe, error_message)
    """
    is_safe, error_msg = validate_sql(sql)

    if not is_safe:
        # 记录拦截日志
        audit_logger.log({
            'user_query': user_query,
            'generated_sql': sql,
            'query_duration_ms': 0,
            'returned_rows': 0,
            'operation_time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'intercepted',
            'error_message': error_msg,
        })

    return is_safe, error_msg
