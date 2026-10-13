#!/bin/bash
# ============================================================
# Linux 一键启动脚本
# 使用前请先创建 conda 环境: conda create -n agent-env python=3.9 -y
# 然后安装依赖: pip install -r requirements.txt
# ============================================================

set -e
cd "$(dirname "$0")"

PYTHON=$(conda run -n agent-env which python 2>/dev/null || echo "python3")

echo "===== 启动 FastAPI 后端 (8000) ====="
nohup $PYTHON fastapi_server.py > logs/fastapi.log 2>&1 &
echo "FastAPI PID: $!"

sleep 2

echo "===== 启动 Streamlit 前端 (8501) ====="
nohup $PYTHON -m streamlit run streamlit_web.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    > logs/streamlit.log 2>&1 &
echo "Streamlit PID: $!"

echo ""
echo "===== 启动完成 ====="
echo "  FastAPI:  http://127.0.0.1:8000"
echo "  前端页面: http://127.0.0.1:8501"
