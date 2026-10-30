# DataVines（Python 复刻）文档

这是数据可观测平台 DataVines 的 Python 实现说明。产品范围对齐上游 [datavane/datavines](https://github.com/datavane/datavines)（Apache-2.0）：数据源、数据目录、数据概览、质量作业、调度、执行、质量报告与 SLA。技术栈按交付约定换成 FastAPI、MySQL 元数据库和 React / Ant Design。登录使用 JWT 与 bcrypt。Spark 实际执行不在本实现里。

阅读顺序建议：

1. [补充说明：已锁定的交付要求](requirements-from-call.md) — 每一条产品约束以及代码里怎么落地。
2. [部署和启动](deploy.md) — `docker compose up`、端口、Demo 路径。
3. [项目结构](project-structure.md) 与 [前端页面](frontend.md)。
4. 功能模块（每篇都包含业务背景、功能点、业务规则、数据流、接口与页面、使用示例）：
   - [数据源管理](modules/datasource.md)
   - [质量规则配置](modules/quality-rules.md)
   - [作业调度](modules/schedule.md)
   - [检查执行](modules/execution.md)
   - [结果报告](modules/report.md)
   - [SLA 告警](modules/sla.md)
   - [数据概览 Profile](modules/profile.md)
   - [数据目录 Catalog](modules/catalog.md)
5. [API 接口](api.md)、[数据库表](database.md)、[质量规则与判定](metrics.md)。

本地开发时前端是 [DataVines](http://127.0.0.1:5680)，后端健康检查是 `GET http://127.0.0.1:5600/api/v1/health`。Docker Compose 对外同样是前端 `5680`、后端 `5600`、MySQL `33306`。
