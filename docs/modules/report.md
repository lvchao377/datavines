# 结果报告

## 业务背景

单次执行只回答「这一次过没过」。数据源负责人还要看今天这张表、这个库、整套源的质量分，以及分数随日期怎么变。上游用 `dv_job_quality_report` 按实体层级存每天一条分数，并用 `dv_job_execution_result_report_rel` 把报告和具体结果连起来。问题单则走 `dv_issue` 与 `dv_job_issue_rel`，状态用 `bad` / `good` 这类字符串，而不是另一套枚举。

## 核心功能点

- 每次写出质量结果后，重算当天四个层级的分数：`DATASOURCE`、`DATABASE`、`TABLE`、`COLUMN`。没有列的规则（例如表行数）不会产生 COLUMN 报告。
- 概览页展示数据源级最新分数、分数折线、通过/未通过饼图、最近问题。
- 问题状态可以改成 `good` 或其他文本，表示处理过了。改状态不会倒改已经算完的分数。
- 列上的历史检查可按库表列查询最近 50 条结果。

## 关键业务规则

- 某一层当天的分数是「该层匹配到的全部结果的 score 的算术平均」，不是加权，也不是只取最后一次。
- 数据源级包含该源当天所有结果；库级再按 `database_name` 过滤；表、列继续收窄。
- 分数来自执行器：通过/失败型公式是 0 或 100，百分比型公式可能是 97.5，差异百分比可能超过 100。报告不做截断，和上游 `getScore` 一致。因此概览上的「分」有时会高于 100，那是 `diff-percentage` 的记分方式，不是算错。
- 同一天同一层级同一实体只有一行报告，重复执行会更新 `score` 并补关联关系。
- 数据库里可空列参与唯一性比较时，SQL 的 `NULL = NULL` 不成立，所以查找已有报告是在应用里比三个名字，而不是一条带 NULL 的等值条件。
- 问题只在「有结果未通过」或「执行过程抛错」时创建，标题分别是「质量检查未通过」和「作业执行失败」。通过的作业不写 good issue。

## 数据流转过程

执行器在同一事务里已经有了 `JobExecutionResult`。它按层级找出当天该数据源的全部结果（包含刚 flush 的这一条），求平均，插入或更新 `dv_job_quality_report`，再插入关联表。概览页三个请求互不依赖：分数、趋势、饼图。饼图按结果 `state` 分组，不按执行实例状态分组，所以「跑成功但规则没过」会计入未通过。

## 前后端对应的接口和页面

| 页面 | 路由 | 接口 |
| --- | --- | --- |
| 质量概览 | `/main/detail/:id/dashboard` | `POST /job/quality-report/score`、`/score-trend`、`POST /job/execution/agg-pie`、`GET /catalog/page/entity/issue` |
| 问题处理 | 概览表格目前只展示；改状态走接口 | `POST /catalog/issue/update-status` |
| 列上的执行历史 | 调试或二次开发 | `GET /job/quality-report/listColumnExecution` |
| 报告分页 | 调试 | `POST /job/quality-report/page` |

## 使用示例

取数据源 1 今天的库级分数：

```http
POST /api/v1/job/quality-report/score
{"datasourceId":1,"entityLevel":"DATABASE","databaseName":"demo"}
```

`data.score` 可能是 `50`：空值检查 0 分和行数检查 100 分的平均。趋势：

```http
POST /api/v1/job/quality-report/score-trend
{"datasourceId":1,"entityLevel":"DATASOURCE"}
```

把问题 1 标成已处理：

```http
POST /api/v1/catalog/issue/update-status
{"id":1,"status":"good"}
```
