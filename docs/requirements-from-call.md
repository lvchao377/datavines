# 补充说明：已锁定的交付要求

下面每一节对应一条已经锁定、不再改口的产品要求。正文说明本仓库如何实现它，并指向对应的功能章节。假设与上游 Java 代码不一致时，以仓库里实际跑通的行为为准，并在相关模块文档里写明。

## 1. 被检数据源：MySQL + Doris

连接器在 `backend/app/connectors.py`。`mysql` 与 `doris` 都通过 SQLAlchemy + PyMySQL 连接。Doris 使用 MySQL 协议，默认端口 9030，库表列查询走 `information_schema`，和 MySQL 同一套 SQL。`GET /api/v1/datasource/type/list` 还会列出 PostgreSQL、ClickHouse、Presto、Trino、StarRocks、Impala、Hive，这些项 `supported=false`，创建接口会拒绝保存。页面上的类型下拉把它们标成「未实现」并禁用。

数据源参数是 JSON：`host`、`port`、`database`、`user`、`password`。标识符只允许字母、数字和下划线，过滤条件不允许分号。详细流程见 [数据源管理](modules/datasource.md)。

## 2. 执行引擎：Local 完整实现，Spark 仅预留接口

Local 引擎在 `backend/app/engine/local.py`。它在被检库上执行指标 SQL、前置/后置 SQL，并在失败时捞取最多 100 行错误样本。调度线程把 `dv_command` 交给 `backend/app/runner.py`，由它完成期望值、公式、阈值、写结果、报告和告警。

Spark 在 `backend/app/engine/spark.py`。`SparkEngine.execute()` 固定抛出 `NotImplementedError`，文案要求改用 `local`。引擎列表里仍返回 `spark`，并带 `implemented: false`。作业可以保存成 spark，一旦运行，执行实例状态变为失败（6），日志里是这段说明，不会去连 Livy 或提交 Spark 作业。见 [检查执行](modules/execution.md)。

## 3. 告警渠道：仅飞书

发送器类型只接受 `feishu`（别名 `lark` 会记成飞书）。请求体是飞书自定义机器人的 `post` 富文本。Webhook 若是 `mock://` 或以 `/api/v1/sla/mock/receive` 结尾，则写入内存收件箱和 `dv_alert_send_log`，不访问外网。邮件、钉钉、企微没有发送实现；插件列表接口只返回飞书。见 [SLA 告警](modules/sla.md)。

## 4. 部署：单机

`docker-compose.yml` 启动三个服务：MySQL 8、后端、前端。没有 ZooKeeper，没有多副本抢锁之外的协调。调度是进程内的 cron 线程加 `dv_command` / `dv_common_task_command` 队列，单节点启动时会把上次残留的「运行中」实例标成失败。端口与步骤见 [部署和启动](deploy.md)。

## 5. 登录与工作空间隔离

`POST /api/v1/login` 校验 bcrypt 密码并签发 JWT，请求头用 `Authorization: Bearer <token>`。`POST /api/v1/register` 创建用户和「用户名's default」工作空间。启动时保证两个账号：`admin` / `123456`（管理员，空间 `admin's default`）和 `user` / `123456`（空间 `user's default`）。`AuthMiddleware` 挡住 `/api/v1` 下的业务接口。`GET /metric/*` 仍公开，目录是 28 条规则。数据源分页、详情和写入只允许当前用户所属的工作空间。前端有登录、注册、用户页，顶栏可以切换工作空间并退出。

## 6. 界面与接口与原版 DataVines 对应

API 前缀是 `/api/v1`，路径对齐上游 Controller：`/datasource`、`/job`、`/job/execution`、`/job/schedule`、`/metric`、`/catalog`、`/sla`、`/config`、`/env`、`/errorDataStorage`、`/common-task`。前端路由对齐 datavines-ui：`/main/home`、`/main/detail/:id/dashboard|editor|jobs|jobExecutionLogs`，并补了目录、概览、Schema 变更，避免主流程 404。

响应统一包成 `{code, msg, data}`。上游有的接口直接返回对象或列表，本实现一律放在 `data` 里，前端 axios 拦截器解包。字段使用 camelCase，表列仍是上游的 snake_case。完整清单见 [API 接口](api.md) 和 [前端页面](frontend.md)。

## 7. 全功能对齐

质量侧覆盖 4 类检查和上游插件名（含 `freshness`，并接受别名 `table_freshness`）。期望值、5 个结果公式、6 个比较符、错误数据、重试、超时、前置/后置 SQL 都在执行器里。目录有元数据同步、Schema 变更、标签、作业关联和简化血缘。血缘页面在 `/main/detail/:id/lineage`，只做一跳和 SQL 表名提取。概览按列类型挑选指标并保留行数趋势。调度同时覆盖质量作业和通用任务。报告按数据源/库/表/列汇总当天分数。SLA 在质量失败或执行失败时发飞书。这些行为分别写在 `docs/modules/` 各篇，规则语义写在 [质量规则与判定](metrics.md)。

直方图 `column_histogram` 已实现，但和上游 `MetricController` 一样，不出现在质量作业的规则下拉里，只给概览用。

## 8. 技术栈：Python FastAPI + MySQL 元库 + React / Ant Design

后端：FastAPI、SQLAlchemy 2、Alembic、PyMySQL、croniter。元数据表由 Alembic 版本 `0001_initial` 按模型建出，列名与 `scripts/sql/datavines-mysql.sql` 的 `dv_*` 对齐（测试 `test_schema_parity.py` 校验）。前端：Vite、React 18、TypeScript、Ant Design 5、ECharts。图表用 ECharts；自定义 SQL 使用多行文本框，而不是 Monaco。

## 9. 每个功能模块须有详细说明

`docs/modules/` 下八篇文档各自包含：业务背景、核心功能点、关键业务规则、数据流转过程、前后端接口与页面、使用示例。本文件只做索引，不代替那些章节。

## 10. 交付物：可运行代码 + 测试报告 + docs/

仓库根目录有 `backend/`、`frontend/`、`docker-compose.yml`、`README.md`、`TEST_REPORT.md` 和本 `docs/` 目录。测试覆盖指标 SQL、公式与比较符、期望值窗口、SQLite 上的核心指标、Spark 桩、表结构对齐，以及在本机 MySQL 上的 Demo 作业判定。

## 11. 中途自行解决问题、交付前自测通过

实现过程中没有把产品问题抛回。本地用 MariaDB 10.11 验证了迁移、Demo 引导、空值检查（实际值 1、未通过、错误样本、飞书 mock）、表行数（实际值 8、通过）和跨表准确性（实际值 2）。`pytest` 结果写在 `TEST_REPORT.md`。Docker Compose 文件按同一端口和同一引导开关编写；本环境若未安装 Docker 引擎，则以 README 中的本地命令作为等价验证，并在测试报告里注明。
