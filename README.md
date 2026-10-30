> **分支说明：** 当前分支 `fastapi-python` 是 DataVines 的 Python / FastAPI 重实现（后端、前端、文档与 Docker 部署都在本分支根目录）。Java 版本仍在 [`dev`](https://github.com/lvchao377/datavines/tree/dev) 分支，两条线互不覆盖。

# DataVines

数据可观测平台的 Python 实现，对照开源项目 [DataVines](https://github.com/datavane/datavines)。包含数据源（MySQL、Doris）、数据目录、数据概览、质量作业、Cron 调度、Local 执行、质量报告和飞书 SLA。Spark 只保留接口。没有登录。

文档在 [docs/index.md](docs/index.md)。部署细节、端口和 Demo 步骤在 [docs/deploy.md](docs/deploy.md)。模块说明在 [docs/modules](docs/modules)。

## 用 Docker 启动

```bash
docker compose up --build
```

| 入口 | 地址 |
| --- | --- |
| 页面 | http://127.0.0.1:5680 |
| API 健康检查 | http://127.0.0.1:5600/api/v1/health |
| 元数据库 | `127.0.0.1:33306`，库 `datavines`，用户 `root`，密码 `datavines` |

后端启动后会建表，并创建 Demo：数据源 `demo-mysql`，作业 `demo_email_null_check`（邮箱空值，预期未通过）和 `demo_orders_row_count`（8 行，预期通过）。打开页面即可运行，不必再准备一台业务库。

## 本地开发

```bash
# 元数据库账号见 docs/deploy.md
cd backend
pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://datavines:datavines@127.0.0.1:3306/datavines?charset=utf8mb4'
uvicorn app.main:app --host 0.0.0.0 --port 5600
```

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器同样是 http://127.0.0.1:5680 ，并把 `/api` 转到 5600。没有自动 Demo 时，在首页点「初始化 Demo」。

```bash
cd backend && pytest -q
```

## 技术栈

FastAPI、SQLAlchemy 2、Alembic、MySQL、React、TypeScript、Ant Design、ECharts。执行引擎是本地 SQLAlchemy/PyMySQL。告警是飞书 Webhook，内置 mock 接收地址 `/api/v1/sla/mock/receive`。
