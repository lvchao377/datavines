import pytest

from app.metrics.registry import list_metrics
from app.metrics.sqlgen import EXPECTED_SQL, build_sql, expected_sql_template


BASE = {"database": "demo", "table": "orders", "column": "email"}


def test_registry_covers_upstream_names():
    names = {item.name for item in list_metrics()}
    expected = {
        "column_null",
        "column_not_null",
        "column_blank",
        "column_unique",
        "column_distinct",
        "column_duplicate",
        "column_in_enums",
        "column_not_in_enums",
        "column_match_regex",
        "column_match_not_regex",
        "column_value_between",
        "column_length",
        "column_min_length",
        "column_max_length",
        "column_avg_length",
        "column_min",
        "column_max",
        "column_avg",
        "column_sum",
        "column_std_dev",
        "column_variance",
        "column_histogram",
        "table_row_count",
        "freshness",
        "custom_aggregate_sql",
        "custom_count_sql",
        "multi_table_accuracy",
        "multi_table_value_comparison",
    }
    assert expected <= names
    assert len(names) == 28


def test_null_unique_and_aggregate_sql():
    null_sql = build_sql("column_null", BASE)
    assert "(`email` is null)" in null_sql.actual_sql
    assert null_sql.invalidate_sql.startswith("select * from `demo`.`orders`")
    assert "count(1) as actual_value" in null_sql.actual_sql
    unique_sql = build_sql("column_unique", {**BASE, "filter": "id > 0"})
    assert "group by `email`" in unique_sql.actual_sql
    assert "having count(1) = 1" in unique_sql.actual_sql
    assert "(id > 0)" in unique_sql.actual_sql
    dup = build_sql("column_duplicate", BASE)
    assert "having count(`email`) > 1" in dup.actual_sql
    assert "count(distinct(`email`))" in build_sql("column_distinct", BASE).actual_sql
    assert "avg(`amount`)" in build_sql("column_avg", {"database": "demo", "table": "orders", "column": "amount"}).actual_sql
    assert "stddev(`amount`)" in build_sql("column_std_dev", {"database": "demo", "table": "orders", "column": "amount"}).actual_sql
    assert build_sql("table_row_count", {"database": "demo", "table": "orders"}).actual_sql.endswith("from `demo`.`orders`") or "from `demo`.`orders`" in build_sql("table_row_count", {"database": "demo", "table": "orders"}).actual_sql


def test_enums_regex_length_between_freshness():
    enums = build_sql("column_in_enums", {**BASE, "column": "status", "enum_list": "PAID,SHIPPED"})
    assert "`status` in ( 'PAID', 'SHIPPED' )" in enums.actual_sql
    missing = build_sql("column_not_in_enums", {**BASE, "column": "status", "enum_list": "PAID"})
    assert "not in" in missing.actual_sql and "is null" in missing.actual_sql
    regex = build_sql("column_match_regex", {**BASE, "regexp": "^a+$"})
    assert "regexp '^a+$'" in regex.actual_sql
    length = build_sql("column_length", {**BASE, "comparator": "gt", "length": 5})
    assert "length(`email`) > 5" in length.actual_sql
    between = build_sql("column_value_between", {"database": "demo", "table": "orders", "column": "amount", "min": 0, "max": 100})
    assert "`amount` >= 0" in between.actual_sql and "`amount` <= 100" in between.actual_sql
    fresh = build_sql(
        "freshness",
        {**BASE, "column": "created_at", "begin_time": "2026-01-01", "deadline_time": "2026-10-30", "datetime_format": "yyyy-MM-dd"},
    )
    assert "DATE_FORMAT(`created_at`, '%Y-%m-%d')" in fresh.actual_sql
    hist = build_sql("column_histogram", {**BASE, "column": "status"})
    assert hist.list_metric is True
    assert "limit 50" in hist.actual_sql


def test_custom_and_multi_table():
    agg = build_sql("custom_aggregate_sql", {"actual_aggregate_sql": "select sum(amount) from demo.orders"})
    assert "sum(amount)" in agg.actual_sql
    counted = build_sql("custom_count_sql", {"actual_execute_sql": "select * from demo.orders where amount < 0"})
    assert "amount < 0" in counted.invalidate_sql
    assert "count(1) as actual_value" in counted.actual_sql
    accuracy = build_sql(
        "multi_table_accuracy",
        {"database": "demo", "table": "orders", "table2": "orders_mirror", "join_column": "id", "compare_column": "amount"},
    )
    assert "left join `demo`.`orders_mirror`" in accuracy.actual_sql
    assert "<=>" in accuracy.actual_sql
    compare = build_sql(
        "multi_table_value_comparison",
        {"database": "demo", "table": "orders", "table2": "orders_mirror", "column": "amount", "compare_metric": "sum"},
    )
    assert "sum(`amount`)" in compare.actual_sql
    assert "orders_mirror" in compare.expected_sql


def test_expected_sql_templates_match_upstream_fragments():
    daily = expected_sql_template("daily_avg", "k")
    assert "round(avg(actual_value),2)" in daily
    assert "interval 1 DAY" in daily
    assert "expected_value_k" in daily
    assert "interval 7 DAY" in EXPECTED_SQL["last_7_day_avg"]
    assert "interval 30 DAY" in EXPECTED_SQL["last_30_day_avg"]
    assert "weekday" in EXPECTED_SQL["weekly_avg"]
    assert "%Y-%m-01" in EXPECTED_SQL["monthly_avg"]


def test_identifier_guard():
    with pytest.raises(ValueError):
        build_sql("column_null", {"database": "demo", "table": "orders;drop", "column": "email"})
    with pytest.raises(ValueError):
        build_sql("column_null", {"database": "demo", "table": "orders", "column": "email", "filter": "1=1; delete from t"})
