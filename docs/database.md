# 数据库表结构

元数据库是 MySQL（开发机上用过 MariaDB 10.11，Compose 用 MySQL 8.0）。表结构以 `scripts/sql/datavines-mysql.sql` 里的 `dv_*` 为对照，SQLAlchemy 模型在 `backend/app/models.py`。`tests/test_schema_parity.py` 断言每张上游 `dv_*` 表的列都在模型里。字符集 utf8mb4。

上游脚本里的 `QRTZ_*` 是 Quartz 用的，本实现不建这些表。调度数据在 `dv_job_schedule` 与 `dv_common_task_schedule`。

下面只写各表在本系统里的用途和关键列。完整列名以 SQL 文件为准。时间列均为 `datetime`。

## 身份与配置

这些表存在，是为了和上游种子数据对齐。接口不校验登录。

| 表 | 用途 | 关键列 |
| --- | --- | --- |
| dv_user | 默认用户 admin，id=1 | username、password（上游 bcrypt，本系统不校验）、email、admin |
| dv_workspace | 默认空间 `admin's default`，id=1 | name |
| dv_user_workspace | 用户与空间 | user_id、workspace_id、role_id |
| dv_access_token | 令牌表，页面说明鉴权关闭 | token、expire_time |
| dv_config | 系统参数，种子来自上游 INSERT | workspace_id、var_key、var_value、is_default |
| dv_env | 运行环境 JSON | name、env |
| dv_tenant | 租户名，执行不依赖它 | tenant |
| dv_server | 节点登记，单机可空 | host、port |
| dv_registry_lock | 锁表，单机工人用行锁而不是这张表 | lock_key、lock_owner |

## 数据源与错误存储

| 表 | 关键列 |
| --- | --- |
| dv_datasource | uuid、name（唯一）、type（mysql/doris）、param（JSON 文本）、workspace_id |
| dv_error_data_storage | name+workspace 唯一、type、param。作业可选把它当作错误行的外部 MySQL |

## 作业、调度、执行、报告

| 表 | 关键列 |
| --- | --- |
| dv_job | type（0 质量 / 1 概览 / 2 比对）、datasource_id、datasource_id_2、schema_name、table_name、column_name、metric_type、engine_type、parameter（规则 JSON）、retry_times、retry_interval、timeout、pre_sql、post_sql、error_data_storage_id、is_error_data_output_to_datasource |
| dv_job_schedule | job_id、cron_expression、status（1 启用）、start_time、end_time |
| dv_command | type（0 启动 / 1 停止）、job_execution_id、priority |
| dv_job_execution | 一次运行。status：0 提交、1 运行、6 失败、7 成功、9 终止。log_path、parameter、engine_type、submit_time、schedule_time、start_time、end_time |
| dv_job_execution_result | metric_type、actual_value、expected_value、expected_type、result_formula、operator、threshold、score、state（1 通过 / 2 未通过）。(job_execution_id, metric_unique_key) 唯一 |
| dv_actual_values | 历史实际值。unique_code、actual_value、data_time。供日均/周均 |
| dv_job_quality_report | entity_level（DATASOURCE/DATABASE/TABLE/COLUMN）、score、report_date |
| dv_job_execution_result_report_rel | 报告与结果 |
| dv_issue | title、content、status（bad/good） |
| dv_job_issue_rel | job_id、issue_id |

## 目录

| 表 | 关键列 |
| --- | --- |
| dv_catalog_entity_definition | 实体类型定义，当前同步逻辑不依赖自定义类型 |
| dv_catalog_entity_instance | uuid、type（database/table/column）、fully_qualified_name、properties、status（active 或 deleted-随机串） |
| dv_catalog_entity_rel | type：child 表示父子，downstream 表示血缘 |
| dv_catalog_entity_metric_job_rel | 实体与作业 |
| dv_catalog_entity_profile | entity_uuid、metric_name、actual_value（文本，直方图是 JSON）、data_date |
| dv_catalog_schema_change | change_type、change_before、change_after |
| dv_catalog_tag_category | 标签分类，带 workspace_id |
| dv_catalog_tag | category_uuid、name |
| dv_catalog_entity_tag_rel | 实体与标签 |

## 通用任务与 SLA

| 表 | 关键列 |
| --- | --- |
| dv_common_task | task_type（CATALOG_METADATA / DATA_PROFILE）、status（0 等待 1 运行 2 成功 3 失败）、parameter、datasource_id |
| dv_common_task_command | task_id |
| dv_common_task_schedule | cron_expression、status、datasource_id |
| dv_sla | name、description |
| dv_sla_job | sla_id、job_id，三者加 workspace 唯一 |
| dv_sla_sender | type=feishu、config JSON（webhook） |
| dv_sla_notification | sla_id、sender_id、config |

## 扩展表

| 表 | 列 |
| --- | --- |
| dv_error_data | job_execution_id、storage_type、row_data（JSON 文本） |
| dv_alert_send_log | sla_id、job_id、job_execution_id、sender_id、channel、webhook、title、content、success、response_body |
| dv_metric_payload | job_execution_result_id、payload |

外部错误库上的表名是 `datavines_error_data`（id、job_execution_id、row_data、create_time），由执行器 `CREATE TABLE IF NOT EXISTS`，不在元数据库迁移里。
