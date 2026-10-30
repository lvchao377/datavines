# 检查执行

## 业务背景

配置只是声明。一次检查要把声明变成：在被检库上跑出的实际值、从历史或固定值得到的期望值、套上公式之后的比较结果、失败行样本、日志，以及是否要告警。上游把这一段叫做 Command 到 JobExecution。本实现保持这个顺序：接口只负责入队，工人线程才去连业务库。这样手动运行和 Cron 运行不会分叉成两套代码。

执行实例状态沿用上游常用编码：0 已提交，1 运行中，6 失败，7 成功，9 已终止。这里的「成功」表示 SQL 跑完了，不表示质量通过。质量通过与否在 `dv_job_execution_result.state`：1 通过，2 未通过。

## 核心功能点

- 提交执行、查询状态、拉日志、拉全部结果、分页看错误样本、终止。
- Local 引擎执行指标 SQL、可选的目标表 SQL、前置与后置脚本。
- 重试只针对抛错（连不上库、SQL 非法），不对「质量未通过」重试。间隔为作业上的 `retry_interval` 秒。
- 超时用定时器关掉连接，实例记为失败。终止接口写停止命令并立刻 `dispose` 当前连接。
- Spark 在进入 SQL 之前失败，日志写明只保留接口。
- 失败样本写入元数据库扩展表 `dv_error_data`。若作业配置了错误数据存储，再写到那台 MySQL 的 `datavines_error_data`。若打开「写回被检库」，同样写一张 `datavines_error_data`。
- 直方图这类 LIST 结果把 JSON 放在扩展表 `dv_metric_payload`，数值列里记桶的个数，避免改上游的 `decimal(20,4)` 列。

## 关键业务规则

一次执行的判定顺序固定为：

1. 生成实际值 SQL 并执行。实际值为 NULL 时按 0 参与后续计算。
2. 若是两表值比对，期望值等于目标聚合，期望类型记为 `target_metric`。
3. 否则按期望类型计算。`none` 得到 0。`fix_value` 取参数 `expected_value`。日/周/月/近 7 天/近 30 天对 `dv_actual_values` 里同一 `unique_code` 的历史做平均，窗口与上游 MetricScript 一致，空窗口得 0，平均值保留两位。周均值的起点是 `data_time` 减去 `weekday` 天（保留时分秒），终点是数据日的次日零点。月均值按该数据时间所在月的 1 号到次日零点，便于补数重复计算；上游 SQL 的月起点用的是服务器 `curdate()`，两者在「作业就在数据日当天跑」时相同。
4. `table_total_rows` / `target_table_total_rows` 再发一条 `count(1)`。
5. 公式得到结果，再和阈值比较。`count`、`diff`、`diff-actual-expected` 的分数是通过 100、否则 0。`percentage` 在正向指标上等于实际/期望×100，在负向指标上等于 100 减这个比率。`diff-percentage` 的分数就是差异百分比本身，可以大于 100。
6. 把本次数值写入 `dv_actual_values`，供下次日均使用。因此期望值用的是**本次之前**的历史。
7. 未通过且指标允许导出错误行时，把失效 SQL 加上 `limit 100` 拉回样本。
8. 任一结果未通过，或整次执行抛错，写 `dv_issue`（status=`bad`）并按 SLA 发飞书。

`unique_code` 由数据源、库、表、列、指标名拼成，最长 250 字符。多表行数会在 key 后再加表名，保证结果表的唯一约束不冲突。

标识符用反引号，拒绝分号和非法字符，避免把过滤条件写成第二条语句。过滤条件本身仍是原始 SQL 片段，和上游一样交给使用者负责。

## 数据流转过程

`POST /job/execute/{id}` → 插入 `dv_job_execution` 与 `dv_command` → 工人抢到命令并删除 → 状态改为 1，日志文件落到 `/tmp/datavines/logs/job-{id}.log`，路径记在 `log_path` → Local 引擎在业务库事务里跑前置 SQL、实际值 SQL、错误样本、后置 SQL → 计算期望与判定 → 写 `dv_job_execution_result`、`dv_actual_values`、必要时写错误行和 Issue → 刷新当日质量报告 → 状态改为 7 或 6 或 9。

前端执行日志页每 2 秒拉一次日志、结果和错误行，直到用户离开页面。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 执行记录 | `/main/detail/:id/jobs` | `POST /job/execution/page` |
| 执行日志 | `/main/detail/:id/jobExecutionLogs` | `GET /job/execution/log/{id}`、`/list/result/{id}`、`/errorDataPage`、`/status/{id}`、`DELETE /job/execution/kill/{id}` |
| 饼图、柱图 | 质量概览 | `POST /job/execution/agg-pie`、`/trend-bar` |

快捷提交（创建作业并立刻入队）还有 `POST /job/execution/submit/data-quality` 和 `/submit/data-reconciliation`，请求体与创建作业相同。

## 使用示例

```http
POST /api/v1/job/execute/1
```

返回的 `data` 是执行实例 id。接着：

```http
GET /api/v1/job/execution/status/10
GET /api/v1/job/execution/log/10
GET /api/v1/job/execution/list/result/10
GET /api/v1/job/execution/errorDataPage?executionId=10&pageNumber=1&pageSize=20
```

Demo 的邮箱空值作业跑完后，结果大致是：`actualValue=1`，`expectedValue=0`，`state=2`，`score=0`，错误样本里能看到 `email` 为 null 的那一行 Bob。表行数作业则是 `actualValue=8`，`state=1`，`score=100`。执行实例的 `status` 两者都是 7。

终止：

```http
DELETE /api/v1/job/execution/kill/10
```
