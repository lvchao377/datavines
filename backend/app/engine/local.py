"""Local JDBC engine: run metric SQL through SQLAlchemy on MySQL or Doris."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text

from app.connectors import create_source_engine, run_statements, validate_param
from app.metrics.sqlgen import SqlPlan


class Cancelled(Exception):
    pass


def _scalar(conn, sql: str):
    row = conn.execute(text(sql)).first()
    if row is None:
        return None
    return row[0]


def _as_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def run_plan(param: dict, datasource_type: str, plan: SqlPlan, *, pre_sql: str | None, post_sql: str | None, collect_errors: bool, cancel_probe, engine_holder: dict) -> dict:
    clean = validate_param(param, datasource_type)
    engine = create_source_engine(clean)
    engine_holder["engine"] = engine
    try:
        with engine.begin() as conn:
            if cancel_probe():
                raise Cancelled("执行已被终止")
            run_statements(conn, pre_sql)
            if cancel_probe():
                raise Cancelled("执行已被终止")
            payload = None
            if plan.list_metric:
                rows = conn.execute(text(plan.actual_sql)).fetchall()
                items = []
                for row in rows:
                    raw = "" if row[0] is None else str(row[0])
                    if "\x01" in raw:
                        key, _, count = raw.partition("\x01")
                    elif "\001" in raw:
                        key, _, count = raw.partition("\001")
                    else:
                        key, count = raw, "1"
                    try:
                        count_val = float(count)
                    except ValueError:
                        count_val = count
                    items.append({"key": key, "count": count_val})
                actual = Decimal(len(items))
                payload = items
            else:
                actual = _as_decimal(_scalar(conn, plan.actual_sql))
            expected_from_target = None
            if plan.expected_sql:
                expected_from_target = _as_decimal(_scalar(conn, plan.expected_sql))
            table_rows = None
            target_rows = None
            errors = []
            if collect_errors and plan.invalidate_sql:
                if cancel_probe():
                    raise Cancelled("执行已被终止")
                limited = plan.invalidate_sql.rstrip()
                if " limit " not in limited.lower():
                    limited = f"{limited} limit 100"
                result = conn.execute(text(limited))
                columns = list(result.keys())
                for row in result:
                    errors.append({col: _jsonable(row[idx]) for idx, col in enumerate(columns)})
            if cancel_probe():
                raise Cancelled("执行已被终止")
            run_statements(conn, post_sql)
        return {
            "actual": actual,
            "expected_from_target": expected_from_target,
            "table_rows": table_rows,
            "target_rows": target_rows,
            "errors": errors,
            "payload": payload,
        }
    finally:
        engine_holder["engine"] = None
        engine.dispose()


def scalar_on_source(param: dict, datasource_type: str, sql: str, engine_holder: dict, cancel_probe):
    clean = validate_param(param, datasource_type)
    engine = create_source_engine(clean)
    engine_holder["engine"] = engine
    try:
        with engine.connect() as conn:
            if cancel_probe():
                raise Cancelled("执行已被终止")
            return _as_decimal(_scalar(conn, sql))
    finally:
        engine_holder["engine"] = None
        engine.dispose()


def write_external_errors(storage_param: dict, storage_type: str, execution_id: int, rows: list[dict]) -> None:
    if (storage_type or "").lower() not in ("mysql", "doris") or not rows:
        return
    clean = validate_param(storage_param, "mysql" if storage_type.lower() == "mysql" else "doris")
    engine = create_source_engine(clean)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS datavines_error_data ("
                    "id BIGINT PRIMARY KEY AUTO_INCREMENT,"
                    "job_execution_id BIGINT NOT NULL,"
                    "row_data LONGTEXT NOT NULL,"
                    "create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            for row in rows:
                conn.execute(
                    text("INSERT INTO datavines_error_data (job_execution_id, row_data) VALUES (:eid, :row)"),
                    {"eid": execution_id, "row": json.dumps(row, ensure_ascii=False, default=str)},
                )
    finally:
        engine.dispose()


def _jsonable(value):
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(sep=" ")
        except TypeError:
            return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value
