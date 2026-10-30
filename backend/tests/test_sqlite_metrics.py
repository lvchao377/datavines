from decimal import Decimal

from sqlalchemy import create_engine, text

from app.metrics.judge import judge
from app.metrics.sqlgen import build_sql


def test_sqlite_runs_core_metric_sql_and_judgment():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("create table orders (id integer, email varchar, amount numeric, status varchar)"))
        conn.execute(
            text("insert into orders values (1, 'a@x.com', 10, 'PAID'), (2, NULL, 20, 'PAID'), (3, '', 0, 'BAD')")
        )
        null_plan = build_sql("column_null", {"table": "orders", "column": "email"})
        nulls = conn.execute(text(null_plan.actual_sql)).scalar()
        assert nulls == 1
        judgment = judge(nulls, 0, "count", "eq", 0, "NEGATIVE")
        assert judgment.success is False and judgment.state == 2
        rows = conn.execute(text(build_sql("table_row_count", {"table": "orders"}).actual_sql)).scalar()
        assert judge(rows, 3, "count", "eq", 3, "POSITIVE").success is True
        distinct = conn.execute(text(build_sql("column_distinct", {"table": "orders", "column": "status"}).actual_sql)).scalar()
        assert distinct == 2
        unique = conn.execute(text(build_sql("column_unique", {"table": "orders", "column": "status"}).actual_sql)).scalar()
        # BAD appears once, PAID appears twice -> one unique value
        assert unique == 1
        duplicate = conn.execute(text(build_sql("column_duplicate", {"table": "orders", "column": "status"}).actual_sql)).scalar()
        assert duplicate == 1
        total = conn.execute(text(build_sql("column_sum", {"table": "orders", "column": "amount"}).actual_sql)).scalar()
        assert Decimal(str(total)) == Decimal("30")
        blank = conn.execute(text(build_sql("column_blank", {"table": "orders", "column": "email"}).actual_sql)).scalar()
        assert blank == 2
