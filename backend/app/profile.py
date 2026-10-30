"""Data profile: pick metrics by column type, store daily values, keep row-count trend."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.catalog import get_entity, save_profile
from app.connectors import create_source_engine, validate_param
from app.metrics.sqlgen import build_sql, table_ref
from app.models import DataSource
from app.util import parse_json

NUMERIC = {"int", "bigint", "tinyint", "smallint", "mediumint", "decimal", "numeric", "float", "double", "real"}
TEMPORAL = {"date", "datetime", "timestamp", "time", "year"}

PROFILE_METRICS = {
    "numeric": ["column_null", "column_distinct", "column_min", "column_max", "column_avg", "column_sum", "column_std_dev", "column_histogram"],
    "string": ["column_null", "column_blank", "column_distinct", "column_min_length", "column_max_length", "column_avg_length", "column_histogram"],
    "datetime": ["column_null", "column_distinct", "column_min", "column_max"],
}


def family(data_type: str) -> str:
    value = (data_type or "").lower()
    if value in NUMERIC:
        return "numeric"
    if value in TEMPORAL:
        return "datetime"
    return "string"


def profile_table(session: Session, datasource_id: int, database: str, table: str, columns: list[str] | None = None) -> dict:
    ds = session.get(DataSource, datasource_id)
    if ds is None:
        raise ValueError("数据源不存在")
    param = validate_param(parse_json(ds.param, {}), ds.type)
    table_entity = get_entity(session, datasource_id, f"{database}.{table}")
    if table_entity is None:
        raise ValueError("请先同步该表的元数据")
    engine = create_source_engine(param)
    data_date = datetime.now().strftime("%Y-%m-%d")
    summary = {"table": f"{database}.{table}", "columns": [], "rowCount": None}
    try:
        with engine.connect() as conn:
            ref = table_ref(database, table)
            row_count = conn.execute(text(f"select count(1) from {ref}")).scalar()
            summary["rowCount"] = int(row_count or 0)
            save_profile(session, table_entity.uuid, "table_row_count", str(summary["rowCount"]), "number", data_date)
            from app.models import CatalogEntityInstance

            col_entities = (
                session.query(CatalogEntityInstance)
                .filter(
                    CatalogEntityInstance.datasource_id == datasource_id,
                    CatalogEntityInstance.type == "column",
                    CatalogEntityInstance.status == "active",
                    CatalogEntityInstance.fully_qualified_name.like(f"{database}.{table}.%"),
                )
                .all()
            )
            for col in col_entities:
                if columns and col.display_name not in columns:
                    continue
                props = parse_json(col.properties, {})
                kind = family(props.get("dataType") or "")
                metrics = PROFILE_METRICS[kind]
                column_result = {"column": col.display_name, "type": props.get("dataType"), "family": kind, "metrics": {}}
                for metric_name in metrics:
                    plan = build_sql(metric_name, {"database": database, "table": table, "column": col.display_name})
                    if plan.list_metric:
                        rows = conn.execute(text(plan.actual_sql)).fetchall()
                        items = []
                        for row in rows:
                            raw = "" if row[0] is None else str(row[0])
                            key, _, count = raw.partition("\x01")
                            items.append({"key": key, "count": _num(count)})
                        save_profile(session, col.uuid, metric_name, json.dumps(items, ensure_ascii=False), "list", data_date)
                        column_result["metrics"][metric_name] = items
                    else:
                        value = conn.execute(text(plan.actual_sql)).scalar()
                        text_value = "null" if value is None else str(value)
                        save_profile(session, col.uuid, metric_name, text_value, "number", data_date)
                        column_result["metrics"][metric_name] = None if value is None else _num(value)
                summary["columns"].append(column_result)
        session.commit()
    finally:
        engine.dispose()
    return summary


def _num(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return value
