# 数据概览（Profile）

## 业务背景

质量规则是人指定的阈值。概览回答另一类问题：这张表有多少行、这一列空多少、取值怎么分布、数字列的最小最大和均值是多少。上游按列的数据类型自动配指标，并把结果放在 `dv_catalog_entity_profile`，按实体、指标名和数据日期唯一。本实现同样先要求目录里已经有这张表，否则探查不知道列类型。

## 核心功能点

- 对指定库表发起探查。可选列清单；不传则探查全部列。
- 按类型选指标：
  - 数值：空值、Distinct、最小、最大、平均、总和、标准差、直方图。
  - 字符串：空值、无值（NULL 或空串）、Distinct、最小/最大/平均长度、直方图。
  - 时间：空值、Distinct、最小、最大。
- 每次探查额外记表的 `table_row_count`，概览页用它画行数趋势。
- 直方图保存为 JSON 列表 `[{key, count}, ...]`，最多 50 个取值，按频次降序。`actual_value_type` 为 `list`，接口会把字符串解析回数组。
- 探查走通用任务队列，和手动点的质量作业互不阻塞对方的命令表。

## 关键业务规则

- 探查前必须同步过元数据。表实体的全名是 `库.表`，列是 `库.表.列`。找不到表实体会失败，任务状态变为 3。
- 同一天同一列同一指标再次探查会覆盖 `actual_value`，不会堆多行。趋势图因此是「每天一个点」。
- 数值类型认定：`int/bigint/tinyint/smallint/mediumint/decimal/numeric/float/double/real`。时间：`date/datetime/timestamp/time/year`。其余当字符串，包括 Doris 里常见的 `varchar`、`string`、`text`。
- 标准差使用 MySQL 的 `stddev`（总体标准差）。Doris 的 MySQL 协议同样提供该函数；若某版本不支持，这一列的探查任务会失败并在通用任务的 `parameter` 里留下错误文本。
- 直方图 SQL 把 `count` 别名写成 `cnt`，避免和函数名冲突，分隔符仍是上游的 `\001`。
- 概览不写质量结果表，也不触发 SLA。它不是一次通过/失败判定。

## 数据流转过程

1. 用户在 `/main/detail/:id/profile` 选择库和表，点「运行探查」。
2. `POST /catalog/profile/execute` 插入 `dv_common_task`（`task_type=DATA_PROFILE`，状态 0）和 `dv_common_task_command`。
3. 工人把任务改成运行中，调用 `profile_table`：先 `count(1)` 写到表实体，再按列类型循环 `build_sql`，在业务库执行，写入 `dv_catalog_entity_profile`。
4. 成功则任务状态 2，失败为 3。用户点「查看结果」时前端再读表实体的行数序列和每个列实体的指标。
5. 定时探查则在 `dv_common_task_schedule` 里把 `taskType` 设为 `DATA_PROFILE`，`param` 里带 `database`、`table`、可选 `columns`。到点后走同一条队列。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 数据概览 | `/main/detail/:id/profile` | `POST /catalog/profile/execute`、`GET /catalog/profile/table/records?uuid=&metric=table_row_count`、`GET /catalog/profile/column/{uuid}` |
| 表实体上的全部指标 | 调试 | `GET /catalog/profile/table/{uuid}` |
| 任务是否跑完 | 目录页底部或 `common-task` | `GET /common-task/page?datasourceId=` |
| 定时探查 | 概览页「定时探查」 | `POST /common-task/schedule`，`taskType=DATA_PROFILE`，`param` 含 `database` 与 `table` |

## 使用示例

```http
POST /api/v1/catalog/profile/execute
{"datasourceId":1,"database":"demo","table":"orders","columns":["email","amount","status"]}
```

返回 `{"taskId": 3}`。等任务成功后，假设 `orders` 表实体 uuid 是 `abc`，邮箱列 uuid 是 `def`：

```http
GET /api/v1/catalog/profile/table/records?uuid=abc&metric=table_row_count
GET /api/v1/catalog/profile/column/def
```

列响应里 `column_null` 的 `actualValue` 在 Demo 上是 `1`，`column_blank` 是 `2`（一个 NULL 加一个空串），`column_histogram` 的 `actualValue` 是取值和次数的数组。行数趋势的点是 `{"date":"2026-10-30","value":"8"}` 这种形状。
