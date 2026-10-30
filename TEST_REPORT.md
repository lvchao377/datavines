# 测试报告

日期：2026-10-30。环境：Python 3.12、MariaDB 10.11（本机元数据库与 Demo 库）、Node 22。命令在 `backend/` 下执行 `python3 -m pytest -q`。

## 结果

**13 passed**，1 条 Alembic `path_separator` 弃用警告（已在 `alembic.ini` 补上 `path_separator = os`，警告来自跑测试时的旧进程缓存或首次读取，复跑迁移不再因此失败）。

| 测试 | 结果 | 内容 |
| --- | --- | --- |
| `tests/test_sqlgen.py` | 通过 | 28 个插件名齐全；空值、唯一、重复、Distinct、枚举、正则、长度、值域、及时性、直方图、自定义 SQL、跨表准确性、两表值比对的 SQL 片段；期望值 SQL 与上游 MetricScript 一致；非法标识符和分号被拒绝 |
| `tests/test_judge.py` | 通过 | 六个比较符；count/diff/percentage 的 4 位小数；负向 percentage 分数；diff-percentage 分数等于差异百分比；日/周/月/7 天/30 天窗口与空历史得 0 |
| `tests/test_sqlite_metrics.py` | 通过 | 在 SQLite 上执行空值、行数、Distinct、唯一、重复、求和、无值 SQL，并完成判定 |
| `tests/test_schema_parity.py` | 通过 | `scripts/sql/datavines-mysql.sql` 中每张 `dv_*` 表的列都在 SQLAlchemy 模型里 |
| `tests/test_spark_stub.py` | 通过 | `SparkEngine.execute` 抛出未实现，并提示改用 local |
| `tests/test_flow.py` | 通过 | 连接本机 MySQL：引导 Demo，跑空值作业（实际值 1、state=2、有错误行、飞书 mock 成功）和行数作业（实际值 8、state=1、执行状态 7） |

元数据库不可达时 `test_flow.py` 会跳过，其余测试不依赖 MySQL。

## 手工冒烟（同日，同一套库）

- `POST` 引导后存在数据源 `demo-mysql`。
- 跨表准确性 `orders` 对 `orders_mirror`：实际值 2（缺 id=8，且 id=7 金额 100 对 90），state=2，错误样本 2 行，执行状态 7。未挂 SLA 时日志写明跳过飞书。
- 对 `demo.orders` 的 email、amount、status 做探查：行数 8；email 上有空值、无值、Distinct、长度和直方图。
- 前端 `http://127.0.0.1:5680` 返回 200。经 Vite 代理访问 `/api/v1/datasource/page` 与 `/api/v1/job/page` 能看到 Demo 数据源和作业。
- 后端 `GET /api/v1/health` 返回 `engine.local=true`、`engine.spark=false`、`alerts=["feishu"]`。

## 浏览器走查

用本机 Chrome（headless）打开 http://127.0.0.1:5680 ：

- 首页直接是「数据源」，有 `demo-mysql` 卡片，没有登录墙。
- 进入详情后，质量概览、规则作业、执行记录、执行日志、数据目录、数据概览、Schema 变更都能打开。
- 在规则作业点击 `demo_orders_row_count` 的「运行」，跳到执行日志。执行实例 6 状态为成功，结果 `actualValue=8`、`expectedValue=8`、`state=1`、`score=100`。
- 告警管理和参数配置能打开。
- 视口 390 宽时首页仍能看到 Demo 卡片和「新建数据源」。

走查时控制台有一条 favicon 404，已补 `frontend/public/favicon.svg`。另有 Ant Design 静态 `message` 的主题警告，不影响操作。

## 未在本环境执行的项

`docker compose up` 的文件已按 MySQL 8 + 后端 5600 + 前端 5680 写好，并设置 `AUTO_BOOTSTRAP_DEMO=true`。本环境未安装 Docker 守护进程（有 `google-chrome`，没有 `docker`），没有在这里执行 `docker compose up`。本地等价路径是 MariaDB + `uvicorn` + `npm run dev`，见 README。

## 如何复现

```bash
# 准备库 datavines，用户 datavines/datavines，见 docs/deploy.md
cd backend
pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://datavines:datavines@127.0.0.1:3306/datavines?charset=utf8mb4'
pytest -q
```

页面：

```bash
# 终端 1
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 5600
# 终端 2
cd frontend && npm install && npm run dev
```

打开 http://127.0.0.1:5680 ，进入 `demo-mysql`，运行 `demo_orders_row_count` 与 `demo_email_null_check`。
