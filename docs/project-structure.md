# 项目结构

仓库是一个单体应用，不是多包 monorepo 工具链。后端和前端各一个目录，Compose 在根上把它们和 MySQL 拼起来。

```
backend/                 FastAPI 应用
  app/main.py            进程入口，启动时迁移、种子、可选 Demo、工人线程
  app/routes.py          /api/v1 路由
  app/models.py          dv_* 表以及三张扩展表
  app/connectors.py      MySQL 与 Doris
  app/metrics/           指标注册、SQL、期望值与公式
  app/engine/local.py    Local 执行
  app/engine/spark.py    Spark 接口桩
  app/runner.py          一次检查的编排
  app/scheduler.py       Cron 与命令队列
  app/catalog.py         目录、变更、血缘、标签
  app/profile.py         数据概览
  app/alerts.py          飞书
  app/demo.py            Demo 库和样例作业
  alembic/               元数据库迁移
  tests/                 pytest
frontend/                React + Ant Design
  src/pages/             与路由对应的页面
  src/api.ts             解包 {code,msg,data}
docker-compose.yml
scripts/sql/datavines-mysql.sql   上游 dv_* 与 QRTZ 脚本，种子数据与结构对照用
docs/                    本文档
```

后端不按 Java 多模块拆仓库，但职责和上游的 connector、metric、engine、server 对应：连接在 `connectors`，规则在 `metrics`，执行在 `engine` 与 `runner`，HTTP 在 `routes`。

三张扩展表不在上游脚本里，文档和测试都单独标明：

- `dv_error_data`：错误样本放在元数据库，界面不用再连外部存储也能看。
- `dv_alert_send_log`：飞书发送审计。
- `dv_metric_payload`：直方图等 LIST 结果。上游把直方图实际值类型标成 LIST，而 `dv_job_execution_result.actual_value` 仍是 `decimal(20,4)`，所以分布 JSON 不塞进那一列。

Quartz 的 `QRTZ_*` 表留在上游 SQL 文件中供对照，运行时不创建。调度见 [作业调度](modules/schedule.md)。

Alembic 只有一个版本 `0001_initial`，`upgrade()` 调用模型的 `create_all`。后续改表应新增版本，而不是改已发布的 0001。种子插入在迁移之后，由 `app/seed.py` 执行，避免把业务数据写进 DDL 版本。
