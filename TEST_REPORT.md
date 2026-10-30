# 测试报告

日期：2026-10-30。环境：Python 3.12、MariaDB 10.11（本机元数据库与 Demo 库）、Node 22。命令在 `backend/` 下执行 `python3 -m pytest -q`。

## 结果

2026-10-30 验收复跑：**19 passed**，0 failed。命令：`cd backend && python3 -m pytest -q`。前端 `npx tsc --noEmit` 通过。

同日补上登录后，在没有元数据库的环境里再跑了一次：`19 passed`，`3 skipped`（`test_flow.py` 与 `test_catalog_profile_doris.py` 的 MySQL 集成）。新增 `tests/test_auth.py`：bcrypt 与 JWT、`GET /metric/list` 无令牌返回 28 条、未登录访问数据源分页为 401，`user` 看不到 `admin` 工作空间的数据源。前端 `npx tsc --noEmit` 再次通过。

| 测试 | 结果 | 内容 |
| --- | --- | --- |
| `tests/test_sqlgen.py` | 通过 | 28 个插件名齐全；空值、唯一、重复、Distinct、枚举、正则、长度、值域、及时性、直方图、自定义 SQL、跨表准确性、两表值比对的 SQL 片段；期望值 SQL 与上游 MetricScript 一致；非法标识符和分号被拒绝 |
| `tests/test_judge.py` | 通过 | 六个比较符；count/diff/percentage 的 4 位小数；负向 percentage 分数；diff-percentage 分数等于差异百分比；日/周/月/7 天/30 天窗口与空历史得 0 |
| `tests/test_sqlite_metrics.py` | 通过 | 在 SQLite 上执行空值、行数、Distinct、唯一、重复、求和、无值 SQL，并完成判定 |
| `tests/test_schema_parity.py` | 通过 | `scripts/sql/datavines-mysql.sql` 中每张 `dv_*` 表的列都在 SQLAlchemy 模型里 |
| `tests/test_spark_stub.py` | 通过 | `SparkEngine.execute` 抛出未实现，并提示改用 local |
| `tests/test_flow.py` | 通过 | 连接本机 MySQL：引导 Demo，跑空值作业（实际值 1、state=2、有错误行、飞书 mock 成功）和行数作业（实际值 8、state=1、执行状态 7） |
| `tests/test_connectors_alerts_cron.py` | 通过 | Doris 默认端口 9030 且 URL 为 `mysql+pymysql`；PostgreSQL/Hive 拒绝；飞书 mock 与 HTTP 成功/业务码失败；Cron 5/6 位与到点窗口 |
| `tests/test_catalog_profile_doris.py` | 通过 | 用 Doris 类型连上本机 MySQL 协议并列出 `demo`；加列与改类型写入 Schema 变更；探查 email 空值 1、无值 2、行数 8；作业挂到列实体；`insert into orders_mirror select * from orders` 写出血缘 |

元数据库不可达时 `test_flow.py` 与 `test_catalog_profile_doris.py` 里的集成用例会跳过。Doris 用例没有单独的 Doris 集群，用本机 MySQL 协议服务验证连接器路径。

## 验收中发现并已修

- Demo 引导创建作业后没有调用目录关联，列实体上看不到质量作业。现已在引导结束时 `bind_job`。
- `POST /job/execution/submit/data-reconciliation` 不会把作业类型写成比对（2），因为路径没有放进请求体。已拆成两个处理函数。
- 血缘解析只认全名，文档里的 `insert into orders_mirror select * from orders` 得不到边。现已在全库唯一时按表名匹配。
- 命令工人在跑作业时一直占着领取命令的数据库会话。现已提交并释放锁后再执行。
- 作业表单的「写回错误数据」开关没有提交。现已写入 `isErrorDataOutputToDatasource`。已有作业可单独保存 Cron。目录和概览页可以保存定时任务。详情增加血缘页。执行日志在成功、失败或终止后停止轮询。
- Compose：后端健康检查增加 40 秒启动宽限，前端等后端健康后再启动，三个服务 `restart: unless-stopped`。

## 验收走查（修复后的进程）

`POST /job/execute/1`（邮箱空值）经命令队列执行，实例 11：状态 7，实际值 1，state=2，错误样本 1 行，飞书 mock `success=1`。另建 `engineType=spark` 的作业，执行状态 6，日志为「Spark 执行引擎仅保留接口，未实现」。

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
