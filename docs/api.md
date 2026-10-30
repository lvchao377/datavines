# API 接口

前缀 `/api/v1`。除健康检查、指标目录和静态文档外，业务接口需要 JWT。成功响应都是：

```json
{"code": 200, "msg": "Success", "data": {}}
```

失败时 HTTP 状态与 `code` 同为 4xx/5xx，`data` 为 null，`msg` 是原因。列表分页的 `data` 形如：

```json
{"records": [], "total": 0, "size": 10, "current": 1, "pages": 0}
```

字段名是 camelCase。下面按模块列出方法、路径和关键字段。交互式文档在 `/docs`。

## 系统

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | `data.status=up`，并带 `engine.local=true`、`engine.spark=false` |
| POST | `/login` | 体：`username`、`password`。成功时顶层和 `data.token` 都是 JWT |
| POST | `/register` | 体：`username`、`email`、`password`。创建用户和默认工作空间 |
| GET | `/user/info` | 当前登录用户，需 JWT |
| GET | `/user/list` | 当前工作空间的成员。查询 `workspaceId`，需 JWT |
| GET | `/workspace/list` | 只返回当前用户加入的工作空间 |
| GET | `/token/page` | 当前工作空间的访问令牌；登录 JWT 不写这张表 |
| GET | `/metric/*` | 指标目录公开，不需要 JWT。一共 28 条规则 |
| GET | `/config/page` | 查询 `searchVal`、`pageNumber`、`pageSize` |
| POST/PUT | `/config` | `varKey`、`varValue`、`workspaceId` |
| DELETE | `/config/{id}` | |
| GET | `/env/list/{workspaceId}` | |
| POST/PUT/DELETE | `/env`、`/env/{id}` | `name`、`env` 对象 |
| GET/POST | `/tenant/list/{workspaceId}`、`/tenant` | `tenant` |

## 指标

`GET /metric/list` 返回全部插件：`label` 中文名，`value` 插件名，另有 `dimension`、`level`。

| 方法 | 路径 | 关键参数 |
| --- | --- | --- |
| GET | `/metric/list/{type}` | `DATA_QUALITY` 或 `DATA_RECONCILIATION` |
| GET | `/metric/quality/list/{level}` | `column` 或 `table`，不含直方图 |
| GET | `/metric/reconciliation/list` | 两个跨表指标 |
| GET | `/metric/configs/{name}` | `[{label,key,supportMultiple}]` |
| GET | `/metric/expectedValue/list/{type}` | 质量类不含 `target_table_total_rows` |
| GET | `/metric/resultFormula/list` | count、diff、diff-actual-expected、percentage、diff-percentage |
| GET | `/metric/operator/list` | eq、lt、lte、gt、gte、neq |
| GET | `/metric/engine/list` | local 已实现，spark `implemented=false` |
| POST | `/metric/sql/preview` | 体：`metricType`、`metricParameter`。回 `actualSql`、`invalidateSql`、`expectedSql` |

## 数据源

| 方法 | 路径 | 关键字段 |
| --- | --- | --- |
| GET | `/datasource/type/list` | `supported`、`defaultPort` |
| GET | `/datasource/config/{type}` | 表单字段 |
| POST | `/datasource/test` | `type`、`param{host,port,database,user,password}` |
| GET | `/datasource/page` | `workspaceId`、`searchVal`、`pageNumber`、`pageSize`。只返回成员可见的数据源，密码掩码 |
| GET | `/datasource/{id}` | 含明文密码，供编辑 |
| POST | `/datasource` | `name`、`type`、`param` |
| PUT | `/datasource` | `id` 加要改的字段 |
| DELETE | `/datasource/{id}` | |
| GET | `/datasource/{id}/databases` | 库名数组 |
| GET | `/datasource/{id}/{database}/tables` | `{name,comment,rows}` |
| GET | `/datasource/{id}/{database}/{table}/columns` | `{name,dataType,columnType,nullable,comment}` |
| GET | `.../preview?limit=` | `{columns,records,sql}` |
| POST | `/datasource/execute` | `datasourceId`、`script`，只读 |

## 作业与调度

创建/更新体的关键字段：`name`、`type`、`datasourceId`、`schemaName`、`tableName`、`columnName`、`metricType`、`engineType`、`parameter`（对象，含 `metricParameter`、`expectedType`、`expectedParameter.expected_value`、`resultFormula`、`operator`、`threshold`）、`retryTimes`、`retryInterval`、`timeout`、`preSql`、`postSql`、`cronExpression`。

| 方法 | 路径 |
| --- | --- |
| POST/PUT | `/job` |
| GET | `/job/page`、`/job/list/{datasourceId}`、`/job/{id}`、`/job/config/{id}`、`/job/execute/config/{id}` |
| DELETE | `/job/{id}` |
| POST | `/job/execute/{id}` | 返回执行 id |
| POST | `/job/schedule/createOrUpdate` | `jobId`、`cronExpression`、`status` |
| GET | `/job/schedule/{jobId}` |
| POST | `/job/schedule/cron` | 返回 `valid`、`dueNow` |
| POST | `/job/schedule/cron/future/list` | 返回时间字符串数组 |

## 执行与报告

| 方法 | 路径 | 关键字段 |
| --- | --- | --- |
| POST | `/job/execution/page` | 体：`datasourceId`、`jobId`、`status`、`pageNumber` |
| GET | `/job/execution/list/{jobId}` | |
| GET | `/job/execution/status/{id}` | `status`、`statusLabel` |
| GET | `/job/execution/log/{id}` | `log`、`path`、`status` |
| GET | `/job/execution/result/{id}` | 第一条结果 |
| GET | `/job/execution/list/result/{id}` | `actualValue`、`expectedValue`、`state`、`score`、`payload` |
| GET | `/job/execution/errorDataPage` | 查询 `executionId`。`rowData` 为对象 |
| DELETE | `/job/execution/kill/{id}` | |
| POST | `/job/execution/agg-pie` | `[{state,name,value}]` |
| POST | `/job/execution/trend-bar` | `[{date,success,fail}]` |
| POST | `/job/execution/submit/data-quality` | 同创建作业，并返回 `jobId`、`executionId` |
| POST | `/job/execution/submit/data-reconciliation` | 同上 |
| POST | `/job/quality-report/page` | `datasourceId`、`entityLevel` |
| POST | `/job/quality-report/score` | 最新一行或 `{score:null}` |
| POST | `/job/quality-report/score-trend` | `[{date,score}]` |
| GET | `/job/quality-report/listColumnExecution` | 查询库表列 |

## 目录、概览、标签、血缘

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/catalog/refresh` | 异步，`data.taskId` |
| POST | `/catalog/refresh/sync` | `{added,deleted,changed}` |
| GET | `/catalog/databases/{datasourceId}` | 实体列表 |
| GET | `/catalog/list/database/{uuid}` | 也接受把数据源 id 放在路径里 |
| GET | `/catalog/list/table/{parentUuid}` | |
| GET | `/catalog/list/column/{parentUuid}` | |
| GET | `/catalog/detail/{uuid}` | 含 `tags` |
| GET | `/catalog/page/schema-change` | 查询 `datasourceId` |
| GET | `/catalog/list/schema-change/{uuid}` | |
| POST | `/catalog/profile/execute` | `datasourceId`、`database`、`table`、`columns` |
| GET | `/catalog/profile/table/{uuid}` | |
| GET | `/catalog/profile/column/{uuid}` | 直方图 `actualValue` 为数组 |
| GET | `/catalog/profile/table/records` | 查询 `uuid`、`metric` |
| GET | `/catalog/lineage/getByUUID/{uuid}` | `{nodes,edges}` |
| POST | `/catalog/lineage/add` | `fromUUID`、`toUUID` |
| POST | `/catalog/lineage/addByParseSql` | `datasourceId`、`sql`，返回 `edges` |
| DELETE | `/catalog/lineage/{from}/{to}` | |
| POST | `/catalog/tag/category` | `name`、`workspaceId` |
| GET | `/catalog/tag/category/list/{workspaceId}` | |
| DELETE | `/catalog/tag/category/{uuid}` | |
| POST | `/catalog/tag` | `name`、`categoryUuid` |
| GET | `/catalog/tag/list-in-category/{uuid}` | |
| GET | `/catalog/tag/list-in-workspace/{workspaceId}` | |
| GET | `/catalog/tag/list-in-entity/{uuid}` | |
| DELETE | `/catalog/tag/{uuid}` | |
| POST | `/catalog/tag/entity-tag` | `entityUuid`、`tagUuid` |
| DELETE | `/catalog/tag/entity-tag` | 查询参数 `entityUuid`、`tagUuid` |
| GET | `/catalog/page/entity/issue` | 问题分页，含 `jobId` |
| POST | `/catalog/issue/update-status` | `id`、`status` |

## 通用任务

| 方法 | 路径 |
| --- | --- |
| GET | `/common-task/page` | 查询 `datasourceId` |
| POST | `/common-task/schedule` | `taskType`、`datasourceId`、`cronExpression`、`status`、`param` |
| GET | `/common-task/schedule/page` |
| DELETE | `/common-task/schedule/{id}` |

## SLA 与错误存储

发送器 `config.webhook`。SLA 创建字段 `name`、`description`。挂接作业体：`slaId`、`jobId`。

| 方法 | 路径 |
| --- | --- |
| GET | `/sla/plugin/support` | 只有飞书 |
| GET | `/sla/sender/config/{type}` | 非飞书会 400 |
| GET | `/sla/page`、`/sla/{id}`、POST/PUT `/sla`、DELETE `/sla/{id}` |
| POST/PUT/DELETE | `/sla/sender`、`/sla/sender/{id}` |
| GET | `/sla/sender/list`、`/sla/sender/page` |
| POST | `/sla/sender/test` | `id` 或 `webhook`，返回 `success`、`response` |
| POST/PUT/DELETE | `/sla/notification` |
| GET | `/sla/notification/page` |
| POST | `/sla/job/createOrUpdate` |
| GET | `/sla/job/list`、`/sla/job/{jobId}` |
| DELETE | `/sla/job/{id}` |
| GET | `/sla/test/{slaId}` |
| POST | `/sla/mock/receive` |
| GET | `/sla/mock/messages` | `memory` 与 `logs` |
| GET | `/errorDataStorage/type/list` | mysql 可用，local 文件未实现 |
| POST | `/errorDataStorage/test`、`/errorDataStorage`、`/errorDataStorage/page` |
| PUT/DELETE | `/errorDataStorage`、`/errorDataStorage/{id}` |
| GET | `/errorDataStorage/list/{workspaceId}` |

## Demo

| 方法 | 路径 | 返回 |
| --- | --- | --- |
| POST | `/demo/bootstrap` | `datasourceId`、`jobs`、`slaId`、`webhook`。密码已掩码 |
| POST | `/demo/schema-change` | 目录同步统计。要求 Demo 数据源已存在 |
