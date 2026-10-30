# 质量规则配置

## 业务背景

数据质量作业描述的是「对哪张表的哪一列、用哪条规则、和什么期望比、差多少算失败」。上游把规则做成指标插件，把期望值和结果公式也做成插件。本实现用注册表 `backend/app/metrics/registry.py` 固定这些插件名和中文名，用 `sqlgen.py` 生成 MySQL/Doris SQL，用 `judge.py` 做比较。配置保存在 `dv_job`，真正算数发生在执行阶段。

四类检查和上游作业类型的对应关系：

| 界面上的检查类型 | `dv_job.type` | 指标 |
| --- | --- | --- |
| 单表列检查 | 0 DATA_QUALITY | 列级指标，外加 `table_row_count` |
| 单表自定义 SQL | 0 DATA_QUALITY | `custom_aggregate_sql`、`custom_count_sql` |
| 跨表准确性 | 2 DATA_RECONCILIATION | `multi_table_accuracy` |
| 两表值比对 | 2 DATA_RECONCILIATION | `multi_table_value_comparison` |

`dv_job.type = 1` 留给数据概览，概览本身走通用任务，不要求用户先建这条作业。

## 核心功能点

- 按层级列出规则：`/metric/quality/list/column` 与 `/table`。直方图被排除，和上游 `excludeMetricSet` 一致。
- 列出期望值、结果公式、比较符、执行引擎。
- 保存作业时把规则参数、期望、公式、比较符、阈值放进 `parameter` JSON，同时把库、表、列冗余到 `schema_name` / `table_name` / `column_name`，方便列表筛选。
- `POST /metric/sql/preview` 可以在不跑作业的情况下看将要执行的 SQL。这是本实现多出来的接口，便于核对规则语义。
- 可选 Cron、重试次数、重试间隔、超时、前置 SQL、后置 SQL。

## 关键业务规则

指标名与上游类的 `getName()` 一致，例如空值是 `column_null` 而不是 `null_check`，及时性插件名是 `freshness`（目录名是 table-freshness）。`table_freshness` 作为别名指向同一指标。

实际值怎么算，见 [质量规则与判定](../metrics.md)。配置侧需要记住的几条：

- 列级「过滤型」指标（空值、非空、无值、枚举、正则、长度比较、值范围、及时性）的实际值是**命中条件的行数**，不是比率。比率要用结果公式 `percentage`，并把期望值设成「表总行数」。
- 唯一性 `column_unique` 统计「出现次数等于 1 的取值个数」。重复值 `column_duplicate` 统计「出现次数大于 1 的取值个数」。Distinct 是 `count(distinct 列)`。
- 值范围统计的是落在 `[min, max]` 内的行，方向为正。空值、无值、重复、不在枚举、正则不匹配的方向为负，只影响 `percentage` 公式的分数，不影响通过与否。通过与否只看公式结果和比较符、阈值。
- 两表值比对的期望值**强制取目标表的同名聚合**（count/sum/avg/min/max），忽略用户填的固定期望。日志会写明这一点。
- 自定义聚合 SQL 必须是单条语句。若它本身不是 SELECT，会被包成 `select (sql) as actual_value`。自定义统计 SQL 的实际值是该查询的行数，查询本身就是错误样本。
- 表行数的 `table` 可以逗号分隔多张表，执行器会各出一条结果。
- 引擎选 `spark` 可以保存，执行必然失败。请选 `local`。

期望值类型：`none`、`fix_value`、`daily_avg`、`weekly_avg`、`monthly_avg`、`last_7_day_avg`、`last_30_day_avg`、`table_total_rows`。比对类作业还可以选 `target_table_total_rows`。质量作业的期望值列表会去掉目标表总行数，与上游 `MetricController` 一致。

结果公式：`count`（实际值）、`diff`（绝对值差）、`diff-actual-expected`（实际减期望）、`percentage`、`diff-percentage`。比较符：`eq lt lte gt gte neq`。

## 数据流转过程

1. 用户在 `/main/detail/:id/editor` 选择检查类型，前端按类型请求指标列表和期望值列表，并拉取该数据源的库表列。
2. 保存时 `POST /api/v1/job`。服务把 parameter 存成 JSON 字符串，并尝试把作业关联到已同步的目录实体（`dv_catalog_entity_metric_job_rel`）。目录还没同步时关联会跳过，不影响作业。
3. 若填写了 Cron，同时插入一条启用的 `dv_job_schedule`。
4. 用户点「运行」只是入队，不算规则。规则 SQL 在执行器里根据当时的 parameter 现生成，因此改完作业再跑就会用新配置。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 规则作业 | `/main/detail/:id/editor` | `GET /job/page?datasourceId=`、`POST /job`、`DELETE /job/{id}`、`POST /job/execute/{id}` |
| 指标、期望、公式、比较符 | 新建弹窗 | `GET /metric/quality/list/{level}`、`/metric/expectedValue/list/{type}`、`/metric/resultFormula/list`、`/metric/operator/list`、`/metric/engine/list` |
| SQL 预览 | 调试 | `POST /metric/sql/preview` |

## 使用示例

邮箱空值必须为 0。Demo 数据里有 1 个 NULL，所以这条会未通过：

```json
{
  "name": "demo_email_null_check",
  "type": 0,
  "datasourceId": 1,
  "schemaName": "demo",
  "tableName": "orders",
  "columnName": "email",
  "metricType": "column_null",
  "engineType": "local",
  "parameter": {
    "metricType": "column_null",
    "metricParameter": {"database": "demo", "table": "orders", "column": "email"},
    "expectedType": "fix_value",
    "expectedParameter": {"expected_value": "0"},
    "resultFormula": "count",
    "operator": "eq",
    "threshold": "0"
  }
}
```

空值率不超过 1%（期望取本表行数，负向指标的分数约为 `100 - 实际/期望*100`）：

```json
{
  "metricType": "column_null",
  "metricParameter": {"database": "demo", "table": "orders", "column": "email"},
  "expectedType": "table_total_rows",
  "expectedParameter": {},
  "resultFormula": "percentage",
  "operator": "lte",
  "threshold": "1"
}
```

跨表准确性：源表 `orders` 按 `id` 左连 `orders_mirror`，`amount` 不一致或目标缺失的行数应等于 0。

```json
{
  "metricType": "multi_table_accuracy",
  "metricParameter": {
    "database": "demo",
    "table": "orders",
    "table2": "orders_mirror",
    "join_column": "id",
    "compare_column": "amount"
  },
  "expectedType": "fix_value",
  "expectedParameter": {"expected_value": "0"},
  "resultFormula": "count",
  "operator": "eq",
  "threshold": "0"
}
```
