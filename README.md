# 企业 AI 智能数据分析师

> **English project name:** Enterprise AI Data Analyst · v2.0

这不再只是一个 Text-to-SQL 工具。系统以 StateGraph 编排“需求理解 → RAG 检索 → 分析计划 → 人工确认 → 多数据集查询 → Python 深度分析 → ECharts 报告”的完整工作流，同时保留 v1 `/api/query` 接口用于快速取数。

## 项目概述

### 核心能力

| 能力 | 说明 |
|------|------|
| 智能数据分析 | StateGraph 驱动多表 Text-to-SQL，并利用会话历史理解多轮意图 |
| Python 深度分析 | Docker 默认隔离执行，Local 模式需显式开启；支持统计分析与机器学习 |
| 智能报告生成 | 自动生成包含 ECharts 图表的 HTML 与 Markdown 报告 |
| 人工反馈机制 | 先展示分析计划，用户可以批准、驳回或提出修改意见 |
| RAG 检索增强 | SQLite 持久化向量库检索业务元数据和术语；可接 OpenAI 兼容 Embedding API |
| 多模型调度 | Chat/Embedding 模型注册表支持请求级动态选择 |
| MCP 服务器 | Python 3.9 可运行的 MCP stdio Tool Server |
| API Key 管理 | Key 仅保存 PBKDF2 哈希，支持 Scope、过期时间、撤销和使用记录 |
| 安全合规 | 只读 SQL、数据脱敏、IP 白名单、审计日志和 Python 资源隔离 |

### 技术栈

- **Python 3.9 / LangGraph** — 兼容既有部署环境的 StateGraph 工作流
- **FastAPI / Streamlit** — REST API 与人工确认界面
- **MySQL / PyMySQL** — 数据库只读查询
- **SQLite Vector Store** — 零额外服务的业务元数据向量库
- **Docker / pandas / NumPy / SciPy / scikit-learn** — 隔离的深度分析运行时
- **ECharts** — 交互式 HTML 图表报告
- **OpenAI-compatible APIs** — 支持 DeepSeek 等 Chat/Embedding 模型

### V2 工作流

```mermaid
flowchart LR
    Q[自然语言需求] --> R[RAG 业务检索]
    R --> P[生成分析计划]
    P --> H{人工确认}
    H -->|修改| P
    H -->|批准| S[多数据集 Text-to-SQL]
    S --> D[脱敏数据]
    D --> X[Docker/Local Python 分析]
    X --> A[分析结论]
    A --> E[HTML/Markdown + ECharts 报告]
```

---

## 项目文件结构

```
project_root/
├── .env                        # 环境变量配置模板
├── security_middleware.py      # 安全工具包：脱敏、SQL拦截、审计日志
├── llm_gateway.py              # 大模型统一调用网关
├── model_registry.py           # Chat / Embedding 模型注册与动态切换
├── rag_store.py                # SQLite 持久化向量库
├── db_mcp_server.py            # 数据库MCP工具服务
├── sql_agent_graph.py          # LangGraph 取数智能体核心循环
├── advanced_agent_graph.py     # V2 计划、HITL、Python 与报告编排
├── python_executor.py          # Docker / Local 受控 Python 执行器
├── report_generator.py         # ECharts HTML / Markdown 报告
├── api_key_manager.py          # API Key 生命周期与 Scope 管理
├── conversation_store.py       # 多轮对话与分析任务状态
├── mcp_server_v2.py            # MCP stdio Tool Server
├── fastapi_server.py           # FastAPI 后端接口服务
├── streamlit_web.py            # Streamlit 轻量化Web页面
├── docker/                     # Python 分析沙箱镜像
├── tests/                      # V2 自动化测试
├── requirements.txt            # 依赖包清单
├── rebuild_db.py               # 数据库一键初始化重建脚本（建库建表建账号+测试数据）
├── start.bat                   # Windows 一键启动脚本（FastAPI + Streamlit）
├── start.sh                    # Linux 一键启动脚本（FastAPI + Streamlit）
├── README.md                   # 本文档
└── logs/
    └── audit.log               # 审计日志文件（自动生成）
```

---

## V2 快速体验

复制配置并填写数据库与模型参数：

```bash
copy .env.example .env
pip install -r requirements.txt
```

Docker 是 Python 深度分析的默认执行方式。首次使用需要构建分析镜像：

```bash
docker build -f docker/Dockerfile.analysis -t enterprise-data-analyst-python:latest .
```

启动后端和前端：

```bash
python fastapi_server.py
streamlit run streamlit_web.py --server.port 8501
```

### 人工确认分析流程

1. 调用 `POST /api/v2/analyses/plan` 生成分析计划；
2. 前端展示 SQL 子任务、Python 目标、图表建议和假设；
3. 调用 `POST /api/v2/analyses/{analysis_id}/review`，可提交修改意见或批准执行；
4. 执行完成后，通过任务响应中的 `report.html_url` 和 `report.markdown_url` 获取报告。

```bash
curl -X POST http://127.0.0.1:8000/api/v2/analyses/plan \
  -H "Content-Type: application/json" \
  -d '{"user_query":"分析各地区销售趋势，识别异常并预测下月销售额"}'
```

### MCP Server

```json
{
  "mcpServers": {
    "enterprise-data-analyst": {
      "command": "python",
      "args": ["mcp_server_v2.py"]
    }
  }
}
```

### 安全说明

- Python 默认在 `--network none`、只读根文件系统、CPU/内存/PID 限制的 Docker 容器中运行；
- Local 模式不是强安全沙箱，只有设置 `ALLOW_LOCAL_PYTHON_EXECUTION=true` 才能启用；
- `.env`、向量库、API Key 数据库、报告、日志和缓存均不会提交到 Git；
- 开启 `API_KEY_AUTH_ENABLED=true` 前必须设置高强度 `ADMIN_API_KEY`，客户端通过 `X-API-Key` 传递凭据。

---

## 基础部署（Windows Miniconda3）

### 1. 安装 Miniconda3

从 https://docs.conda.io/en/latest/miniconda.html 下载并安装 Miniconda3（Python 3.9 版本）。

### 2. 创建虚拟环境

```bash
# 打开 Anaconda Prompt (Miniconda3)
conda create -n data_agent python=3.9 -y
conda activate data_agent
```

### 3. 进入项目目录

```bash
cd C:\path\to\project
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

如果安装速度慢，可使用国内镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5. 初始化数据库（首次部署必做）

> **重要**：这一步会在 MySQL 里创建业务数据库、5 张业务表、测试数据、只读账号。
> **必须先做这一步，再启动服务**，否则服务启动后无表可查、连接报错。
>
> **为什么必须用 rebuild_db.py 而不是 mysql 命令行导入 .sql？**
> Windows cmd 默认字符集是 gbk/latin1，用 `mysql -u root -p < init_db.sql`
> 直接导入含中文的脚本时，中文会在传输过程中被替换成 `?` 永久写入磁盘，
> 后续无论怎么改连接编码都无法还原。`rebuild_db.py` 用 pymysql 强制
> `utf8mb4` 连接执行，彻底绕开这个编码陷阱，Windows/Linux 通用。

复制配置模板并填写本地真实值（`.env` 已被 Git 忽略，不会上传）：

```bash
copy .env.example .env
```

然后在 `.env` 中设置 `ADMIN_PASSWORD`，并让 `READONLY_PASSWORD` 与
`DB_PASSWORD` 保持一致。请勿把真实密码写回源码。

执行重建：

```bash
conda activate data_agent
cd C:\path\to\project
python rebuild_db.py
```

看到 `重建完成！中文已恢复正常。` 即表示成功，会自动：
- 创建 `enterprise_data` 数据库（utf8mb4）
- 创建 5 张表：employees / departments / products / customers / sales_orders
- 插入测试数据（中文正常）
- 创建只读账号 `readonly_user`（仅 SELECT 权限）
- 验证中文与只读账号

> **关于数据库连接的说明**：你不需要手动去"连接 MySQL"。
> 代码内部（`db_mcp_server.py` 的 `_get_connection`）在每次查询时
> 会自动用 `.env` 里的只读账号连接数据库，查完自动关闭（`finally: connection.close()`）。
> 所以你只要保证：① MySQL 服务在运行 ② `.env` 里的 `DB_USER/DB_PASSWORD` 与
> `rebuild_db.py` 建的只读账号一致 —— 服务就能自动连上取数。

### 6. 配置环境变量

从模板创建 `.env`（注意文件名以点开头），再填写真实配置：

```bash
copy .env.example .env
```

编辑 .env 文件，填写以下必要配置：

| 配置项 | 说明 | 示例值 |
|--------|------|--------|
| DB_HOST | 数据库内网IP | 192.168.1.100 |
| DB_PORT | 数据库端口 | 3306 |
| DB_NAME | 数据库名称 | your_database |
| DB_USER | 只读账号 | readonly_user |
| DB_PASSWORD | 只读密码 | your_password |
| LLM_API_BASE | DeepSeek API地址 | http://192.168.1.200:8000/v1 |
| LLM_API_KEY | API Key | sk-xxxxx |
| LLM_MODEL_NAME | 模型名称 | deepseek-chat |

> **安全警告**：已填写真实值的 .env 文件严禁提交到版本控制系统，已加入 .gitignore。

### 7. 启动服务

> 启动前确认：① MySQL 已运行且已执行 `rebuild_db.py`  ② `.env` 已配置  ③ 依赖已安装

#### 方式一：一键启动脚本（推荐）

Windows（双击或命令行执行 `start.bat`）：

```bash
start.bat
```

Linux：

```bash
chmod +x start.sh
./start.sh
```

脚本会自动按顺序启动 FastAPI 后端（8000）和 Streamlit 前端（8501），
Linux 下日志写入 `logs/fastapi.log` 和 `logs/streamlit.log`。

#### 方式二：手动分步启动（便于调试）

#### 第一步：启动 FastAPI 后端服务

```bash
# 在项目目录下执行
python fastapi_server.py
```

服务默认监听 0.0.0.0:8000，API 文档地址：http://127.0.0.1:8000/docs

#### 第二步：启动 Streamlit 前端页面（新开终端）

```bash
# 新开一个 Anaconda Prompt，激活环境
conda activate data_agent
cd C:\path\to\project

# 启动 Streamlit
streamlit run streamlit_web.py --server.port 8501 --server.address 0.0.0.0
```

访问 http://127.0.0.1:8501 即可使用 Web 页面。

---

## Linux 内网服务器部署

### 1. 安装 Miniconda3

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc
```

### 2. 创建环境并安装依赖

```bash
conda create -n data_agent python=3.9 -y
conda activate data_agent
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env .env
vim .env
```

### 4. 使用 systemd 管理服务（推荐）

创建服务文件 /etc/systemd/system/data-agent-api.service：

```ini
[Unit]
Description=Data Agent API Service
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/project
Environment=PATH=/home/your_user/miniconda3/envs/data_agent/bin
ExecStart=/home/your_user/miniconda3/envs/data_agent/bin/python fastapi_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

创建服务文件 /etc/systemd/system/data-agent-web.service：

```ini
[Unit]
Description=Data Agent Web UI
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/project
Environment=PATH=/home/your_user/miniconda3/envs/data_agent/bin
ExecStart=/home/your_user/miniconda3/envs/data_agent/bin/streamlit run streamlit_web.py --server.port 8501 --server.address 0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable data-agent-api
sudo systemctl enable data-agent-web
sudo systemctl start data-agent-api
sudo systemctl start data-agent-web
```

### 5. 使用 screen / tmux（简易方式）

```bash
# 终端1：启动API服务
conda activate data_agent
cd /path/to/project
python fastapi_server.py

# 终端2：启动Web页面
conda activate data_agent
cd /path/to/project
streamlit run streamlit_web.py --server.port 8501 --server.address 0.0.0.0
```

---

## 项目启动顺序

1. **确保 MySQL 服务已启动**，且已用 `rebuild_db.py` 初始化数据库、表、测试数据、只读账号
2. **确保 DeepSeek API 服务已部署并可访问**
3. **配置 .env 环境变量文件**（DB_USER/DB_PASSWORD 与 rebuild_db.py 建的只读账号一致）
4. **启动 FastAPI 后端服务**（python fastapi_server.py，或用 start.bat / start.sh 一键启动）
5. **启动 Streamlit 前端页面**（streamlit run streamlit_web.py）
6. **访问 Web 页面**（http://127.0.0.1:8501）

---

## API 接口文档

启动 FastAPI 后，访问 http://127.0.0.1:8000/docs 查看完整的 Swagger API 文档。

### 核心接口

| 接口 | 方法 | 说明 |
|------|------|------|
| /health | GET | 健康检查 |
| /api/query | POST | 执行取数查询 |
| /api/history | GET | 获取审计日志 |

### 请求示例

```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"user_query": "查询上个月各地区的销售额排名"}'
```

### 响应示例

```json
{
  "status": "success",
  "session_id": "session_1234567890",
  "user_query": "查询上个月各地区的销售额排名",
  "generated_sql": "SELECT region, SUM(amount) as total FROM sales WHERE month = DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 1 MONTH), '%Y-%m') GROUP BY region ORDER BY total DESC LIMIT 50",
  "query_columns": ["region", "total"],
  "returned_rows": 10,
  "query_duration_ms": 152.34,
  "analysis": "根据查询结果，上个月销售额排名前三的地区分别是：华东区（1,250万元）、华南区（980万元）、华北区（750万元）。",
  "steps": [...],
  "error": ""
}
```

---

## 安全规范说明

### 1. 数据库安全
- 数据库账号仅分配只读（SELECT）权限
- 代码强制校验 SQL，拦截所有写操作
- 单次查询限制最大返回 50 行

### 2. 数据脱敏
- 手机号：138****5678
- 身份证：1101************34
- 银行卡号：6222****7890
- 所有发送给大模型的数据提前脱敏

### 3. 访问控制
- 内网 IP 白名单限制
- 屏蔽所有公网访问入口
- 支持 CIDR 网段配置

### 4. 审计日志
- 全操作不可删除审计日志
- 仅追加写入，不覆盖
- 记录：提问原文、生成SQL、查询耗时、返回行数、操作时间

### 5. 配置安全
- 所有配置项统一存放 .env 文件
- 代码内无任何明文配置
- 密钥、数据库配置不硬编码

---

## 扩展开发指南

### 对接飞书/钉钉 SSO 登录

在 `fastapi_server.py` 中添加认证中间件：

```python
# 示例：添加认证依赖
from fastapi import Depends, HTTPException

async def verify_token(request: Request):
    token = request.headers.get('Authorization', '')
    # 调用飞书/钉钉 SSO 验证接口
    if not valid_token(token):
        raise HTTPException(status_code=401, detail='未授权')
    return True
```

### 多员工 RBAC 数据源权限管控

在 security_middleware.py 中扩展权限模型：

```python
class RBACManager:
    def __init__(self):
        self.permissions = {}  # user -> [allowed_databases]

    def check_permission(self, user: str, database: str) -> bool:
        return database in self.permissions.get(user, [])
```

---

## 常见问题

### Q: 启动时提示 "LLM_API_BASE 未配置"
A: 请检查 .env 文件是否已正确配置，确保文件名为 .env（以点开头）。

### Q: 查询结果中文全是问号（???）
A: 这是初始化时字符集不对导致中文永久损坏。**切勿用 `mysql -u root -p < init_db.sql`
在 Windows cmd 里直接导入含中文的脚本**（cmd 默认 gbk/latin1，中文会被替换成 `?` 永久写入）。
正确做法是用 `python rebuild_db.py`（pymysql 强制 utf8mb4 连接），Windows/Linux 通用。
若数据已损坏，重新执行 `rebuild_db.py` 即可重建。

### Q: 数据库连接失败
A: 确认 MySQL 服务已启动，只读账号已创建，且内网网络互通。

### Q: Streamlit 页面无法连接 API
A: 确认 FastAPI 服务已启动，检查 API_BASE_URL 环境变量或默认地址是否正确。

### Q: 如何查看审计日志？
A: 审计日志默认保存在 logs/audit.log 文件，也可通过 /api/history 接口查看。

---

## 许可证

本项目仅供企业内部使用，遵循数据安全合规要求。
