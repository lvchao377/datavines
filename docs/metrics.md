# 质量规则列表及业务规则

规则实现在 `backend/app/metrics/`。名字、中文名、维度和方向对齐上游插件。`column_histogram` 能生成 SQL，但质量作业下拉不展示它。

维度：`COMPLETENESS` 完整性，`UNIQUENESS` 唯一性，`EFFECTIVENESS` 有效性，`TIMELINESS` 及时性，`ACCURACY` 准确性。方向只影响 `percentage` 的分数。

## 单表列与表级指标

过滤型指标的实际值是命中 WHERE 的行数。聚合型指标直接 SELECT 聚合函数。

| 插件名 | 中文 | 维度 | 方向 | 实际值 |
| --- | --- | --- | --- | --- |
| column_null | 空值检查 | COMPLETENESS | 负 | `column IS NULL` 的行数 |
| column_not_null | 非空检查 | COMPLETENESS | 正 | `IS NOT NULL` 的行数 |
| column_blank | 无值检查 | COMPLETENESS | 负 | NULL 或空串的行数 |
| column_unique | 唯一性检查 | UNIQUENESS | 正 | `GROUP BY 列 HAVING COUNT(1)=1` 的组数 |
| column_distinct | Distinct检查 | UNIQUENESS | 正 | `COUNT(DISTINCT 列)` |
| column_duplicate | 重复值检查 | UNIQUENESS | 负 | `HAVING COUNT(列)>1` 的组数 |
| column_in_enums | 枚举值检查 | EFFECTIVENESS | 正 | 落在枚举列表中的行数 |
| column_not_in_enums | 枚举值[不在]检查 | EFFECTIVENESS | 负 | 不在列表中或为 NULL 的行数 |
| column_match_regex | 正则表达式[匹配]检查 | COMPLETENESS | 正 | `column REGEXP 模式` 的行数 |
| column_match_not_regex | 正则表达式[不匹配]检查 | COMPLETENESS | 负 | `NOT REGEXP` 的行数 |
| column_value_between | 值范围检查 | COMPLETENESS | 正 | `列 >= min AND 列 <= max` 的行数 |
| column_length | 长度检查 | COMPLETENESS | 正 | `LENGTH(列) comparator 长度` 的行数 |
| column_min_length | 字段最小长度检查 | COMPLETENESS | 正 | `MIN(LENGTH(列))` |
| column_max_length | 字段最大长度检查 | COMPLETENESS | 正 | `MAX(LENGTH(列))` |
| column_avg_length | 字段平均长度检查 | COMPLETENESS | 正 | `AVG(LENGTH(列))` |
| column_min | 最小值检查 | COMPLETENESS | 正 | `MIN(列)` |
| column_max | 最大值检查 | COMPLETENESS | 正 | `MAX(列)` |
| column_avg | 平均值检查 | COMPLETENESS | 正 | `AVG(列)` |
| column_sum | 总值检查 | COMPLETENESS | 正 | `SUM(列)` |
| column_std_dev | 标准差检查 | COMPLETENESS | 正 | `STDDEV(列)` |
| column_variance | 方差检查 | COMPLETENESS | 正 | `VARIANCE(列)` |
| column_histogram | 数据分布检查 | COMPLETENESS | 正 | 最多 50 个取值及次数；数值列记桶数 |
| table_row_count | 表行数检查 | COMPLETENESS | 正 | `COUNT(1)`，表名可逗号分隔 |
| freshness | 及时性检查 | TIMELINESS | 正 | 时间列落在 begin 与 deadline 之间的行数。格式 `yyyy-MM-dd HH:mm:ss` 会转成 MySQL 的 `%Y-%m-%d %H:%i:%s` |
| custom_aggregate_sql | 自定义聚合SQL | ACCURACY | 正 | 用户 SQL 的标量结果 |
| custom_count_sql | 自定义统计SQL | ACCURACY | 正 | 用户 SQL 的行数 |

`table_freshness` 是 `freshness` 的别名。

枚举列表用逗号分隔，字符串会加引号，纯数字保持数字。已经带引号的列表会原样放进 `IN`。正则和过滤条件里不允许分号。

## 跨表

`multi_table_accuracy`（跨表准确性，负向）：源表按 `join_column` 左连目标表 `table2`。实际值是目标键为 NULL，或 `compare_column` 使用 `<=>` 比较不相等的行数。可选 `filter` 与 `filter2`。错误样本是这些键。

`multi_table_value_comparison`（两表值比对，正向）：`compare_metric` 取 `count`、`sum`、`avg`、`min`、`max`（默认 count）。实际值是源表聚合，期望值是目标表聚合，然后再套用户选择的结果公式。这条会覆盖期望值插件。

## 期望值

| 名称 | 中文 | 规则 |
| --- | --- | --- |
| none | 无 | 0 |
| fix_value | 固定值 | 参数 `expected_value`，缺省报错 |
| daily_avg | 日均值 | 数据日当天历史实际值的平均，保留两位；没有历史则 0 |
| weekly_avg | 周均值 | 从 `data_time` 回退 `weekday` 天到次日零点 |
| monthly_avg | 月均值 | 数据时间所在月 1 号到次日零点 |
| last_7_day_avg | 最近7天均值 | 数据日零点回退 7 天到次日零点 |
| last_30_day_avg | 最近30天均值 | 回退 30 天 |
| table_total_rows | 表总行数 | 源表 `COUNT(1)` |
| target_table_total_rows | 目标表总行数 | 目标表 `COUNT(1)`，仅比对类作业的期望列表里出现 |

历史行来自 `dv_actual_values`，键是 `数据源|库|表|列|指标`。本次结果在判定之后才写入，所以不会把自己算进期望。

上游期望 SQL 文本（`round(avg(actual_value),2)`、`date_sub`、`weekday` 等）保存在 `sqlgen.EXPECTED_SQL`，测试锁定这些片段。运行时用同样的窗口在元数据库里用 Python 聚合，避免把元数据 SQL 发到 Doris 业务库上。

## 结果公式、比较符、分数

设实际值为 A，期望值为 E，阈值 T。除法先按 4 位小数四舍五入再乘 100，与上游 `RoundingMode.HALF_UP` 一致。E 为 0 时百分比类结果为 0。

| 插件名 | 结果 | 分数 |
| --- | --- | --- |
| count | A | 通过 100，否则 0 |
| diff | \|A-E\| | 通过 100，否则 0 |
| diff-actual-expected | A-E | 通过 100，否则 0 |
| percentage | A/E×100 | 正向为该比率；负向为 100 减该比率 |
| diff-percentage | \|A-E\|/E×100 | 分数等于该百分比，不论是否通过 |

比较符：`eq =`，`lt <`，`lte <=`，`gt >`，`gte >=`，`neq !=`。用 `Decimal` 比较，`1` 与 `1.0` 相等。

`state`：1 通过，2 未通过。执行实例状态另算，见执行文档。

## 示例

Demo `orders` 共 8 行。`email` 有 1 个 NULL、1 个空串。

- `column_null` + `count` + `eq 0`：实际值 1，未通过，分数 0。
- `column_blank`：实际值 2。
- `table_row_count` + `eq 8`：通过，分数 100。
- `column_null` + 期望 `table_total_rows` + `percentage` + `lte 1`：结果 `1/8*100 = 12.5`，未通过；负向分数为 `100-12.5 = 87.5`。
- 跨表准确性对比 `orders_mirror`：id=8 在目标缺失，id=7 的 amount 是 100 对 90，实际值 2。
