# -*- coding: utf-8 -*-
"""Restricted Docker/local executor for LLM-generated analytical Python."""

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional


ALLOWED_IMPORT_ROOTS = {
    'collections', 'datetime', 'decimal', 'itertools', 'json', 'math',
    'numpy', 'pandas', 'scipy', 'sklearn', 'statistics',
}
BLOCKED_CALLS = {
    '__import__', 'breakpoint', 'compile', 'eval', 'exec', 'exit',
    'delattr', 'getattr', 'globals', 'help', 'input', 'locals', 'open',
    'quit', 'setattr', 'vars',
}
BLOCKED_ATTRIBUTES = {
    'system', 'popen', 'spawn', 'fork', 'remove', 'unlink', 'rmdir',
    'rmtree', 'rename', 'replace', 'chmod', 'chown', 'connect', 'request',
    'fetch_openml', 'load', 'save', 'savez',
    'read_csv', 'read_excel', 'read_feather', 'read_fwf', 'read_hdf',
    'read_html', 'read_json', 'read_orc', 'read_parquet', 'read_pickle',
    'read_sas', 'read_spss', 'read_sql', 'read_stata', 'read_table',
    'read_xml', 'to_csv', 'to_excel', 'to_feather', 'to_hdf', 'to_html',
    'to_json', 'to_orc', 'to_parquet', 'to_pickle', 'to_sql', 'to_stata',
}


class UnsafePythonCode(ValueError):
    pass


def validate_python_code(code: str) -> None:
    if not code or len(code) > int(os.environ.get('PYTHON_MAX_CODE_CHARS', '20000')):
        raise UnsafePythonCode('Python 代码为空或过长')
    try:
        tree = ast.parse(code, mode='exec')
    except SyntaxError as exc:
        raise UnsafePythonCode('Python 代码语法错误: %s' % exc)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] not in ALLOWED_IMPORT_ROOTS:
                    raise UnsafePythonCode('禁止导入模块: %s' % alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or '').split('.')[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                raise UnsafePythonCode('禁止导入模块: %s' % (node.module or ''))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
                raise UnsafePythonCode('禁止调用: %s' % node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_ATTRIBUTES:
                raise UnsafePythonCode('禁止调用属性: %s' % node.func.attr)
        elif isinstance(node, ast.Attribute) and node.attr.startswith('__'):
            raise UnsafePythonCode('禁止访问双下划线属性')


def _runner_source(user_code: str) -> str:
    return '''# -*- coding: utf-8 -*-
import json
from decimal import Decimal
from datetime import date, datetime

with open("input.json", "r", encoding="utf-8") as handle:
    rows = json.load(handle)

try:
    import pandas as pd
    df = pd.DataFrame(rows)
except ImportError:
    df = rows

analysis_result = {}
charts = []

%s

def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)

with open("result.json", "w", encoding="utf-8") as handle:
    json.dump({"analysis_result": analysis_result, "charts": charts}, handle,
              ensure_ascii=False, default=_json_default)
''' % user_code


class PythonExecutor:
    def __init__(self, mode: Optional[str] = None):
        self.mode = (mode or os.environ.get('PYTHON_EXECUTOR_MODE', 'docker')).lower()
        self.timeout = int(os.environ.get('PYTHON_EXECUTION_TIMEOUT', '60'))
        self.max_rows = int(os.environ.get('PYTHON_MAX_ROWS', '5000'))

    def execute(self, code: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        validate_python_code(code)
        safe_rows = rows[:self.max_rows]
        started = time.time()
        with tempfile.TemporaryDirectory(prefix='data_analyst_') as directory:
            input_path = os.path.join(directory, 'input.json')
            runner_path = os.path.join(directory, 'runner.py')
            with open(input_path, 'w', encoding='utf-8') as handle:
                json.dump(safe_rows, handle, ensure_ascii=False, default=str)
            with open(runner_path, 'w', encoding='utf-8') as handle:
                handle.write(_runner_source(code))

            if self.mode == 'docker':
                completed = self._run_docker(directory)
            elif self.mode == 'local':
                completed = self._run_local(directory)
            else:
                raise ValueError('不支持的 PYTHON_EXECUTOR_MODE: %s' % self.mode)

            result_path = os.path.join(directory, 'result.json')
            if completed.returncode != 0:
                raise RuntimeError('Python 分析执行失败: %s' % completed.stderr[-2000:])
            if not os.path.exists(result_path):
                raise RuntimeError('Python 分析未生成 result.json')
            with open(result_path, 'r', encoding='utf-8') as handle:
                result = json.load(handle)
        result['mode'] = self.mode
        result['duration_ms'] = round((time.time() - started) * 1000, 2)
        result['stdout'] = completed.stdout[-2000:]
        return result

    def _run_local(self, directory: str) -> subprocess.CompletedProcess:
        if os.environ.get('ALLOW_LOCAL_PYTHON_EXECUTION', 'false').lower() != 'true':
            raise PermissionError(
                'Local Python 执行默认关闭；仅在可信内网环境设置 '
                'ALLOW_LOCAL_PYTHON_EXECUTION=true 后启用'
            )
        safe_environment = {
            key: os.environ[key]
            for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP')
            if key in os.environ
        }
        safe_environment['PYTHONIOENCODING'] = 'utf-8'
        return subprocess.run(
            [sys.executable, '-I', 'runner.py'],
            cwd=directory,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=self.timeout,
            env=safe_environment,
            check=False,
        )

    def _run_docker(self, directory: str) -> subprocess.CompletedProcess:
        docker = shutil.which('docker')
        if not docker:
            raise RuntimeError('未找到 Docker；请安装 Docker 或显式启用受信任的 Local 模式')
        image = os.environ.get('PYTHON_DOCKER_IMAGE', 'enterprise-data-analyst-python:latest')
        command = [
            docker, 'run', '--rm', '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', os.environ.get('PYTHON_MEMORY_LIMIT', '512m'),
            '--cpus', os.environ.get('PYTHON_CPU_LIMIT', '1.0'),
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
            '-v', '%s:/workspace:rw' % os.path.abspath(directory),
            '-w', '/workspace', image, 'python', 'runner.py',
        ]
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=self.timeout,
            check=False,
        )


def extract_python_code(content: str) -> str:
    import re
    match = re.search(r'```(?:python)?\s*(.*?)```', content or '', re.DOTALL | re.IGNORECASE)
    return (match.group(1) if match else content or '').strip()
