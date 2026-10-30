"""MySQL and Doris connectors. Other datasource types stay as explicit stubs."""

from __future__ import annotations

import re
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SUPPORTED_TYPES = {"mysql", "doris"}
STUB_TYPES = ["postgresql", "clickhouse", "presto", "trino", "starrocks", "impala", "hive"]
_HOST = re.compile(r"^[A-Za-z0-9_.:\-]+$")


def type_items() -> list[dict]:
    items = [
        {"name": "mysql", "label": "MySQL", "value": "mysql", "supported": True, "defaultPort": 3306},
        {"name": "doris", "label": "Apache Doris", "value": "doris", "supported": True, "defaultPort": 9030},
    ]
    for name in STUB_TYPES:
        items.append({"name": name, "label": name, "value": name, "supported": False, "defaultPort": None})
    return items


def normalize_type(datasource_type: str) -> str:
    value = (datasource_type or "").strip().lower()
    if value not in SUPPORTED_TYPES:
        raise ValueError(f"数据源类型 {datasource_type} 未实现。当前仅支持 MySQL 与 Doris，其余类型为占位。")
    return value


def validate_param(param: dict, datasource_type: str) -> dict:
    dtype = normalize_type(datasource_type)
    if not isinstance(param, dict):
        raise ValueError("连接参数必须是对象")
    host = str(param.get("host") or "").strip()
    user = str(param.get("user") or param.get("username") or "").strip()
    if not host or not _HOST.match(host):
        raise ValueError("host 无效")
    if not user:
        raise ValueError("用户名不能为空")
    port = int(param.get("port") or (9030 if dtype == "doris" else 3306))
    if port < 1 or port > 65535:
        raise ValueError("端口无效")
    database = str(param.get("database") or param.get("db") or "").strip()
    if database and not re.match(r"^[A-Za-z0-9_]+$", database):
        raise ValueError("数据库名无效")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": str(param.get("password") or ""),
        "database": database,
        "properties": str(param.get("properties") or ""),
    }


def sqlalchemy_url(param: dict) -> str:
    user = quote_plus(param["user"])
    password = quote_plus(param.get("password") or "")
    database = param.get("database") or ""
    path = f"/{database}" if database else "/"
    return (
        f"mysql+pymysql://{user}:{password}@{param['host']}:{param['port']}{path}"
        "?charset=utf8mb4"
    )


def create_source_engine(param: dict) -> Engine:
    return create_engine(
        sqlalchemy_url(param),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 10, "read_timeout": 60, "write_timeout": 60},
        future=True,
    )


def test_connection(datasource_type: str, param: dict) -> None:
    clean = validate_param(param, datasource_type)
    engine = create_source_engine(clean)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    finally:
        engine.dispose()


def list_databases(conn) -> list[str]:
    rows = conn.execute(
        text(
            "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA "
            "WHERE SCHEMA_NAME NOT IN ('information_schema','mysql','performance_schema','sys') "
            "ORDER BY SCHEMA_NAME"
        )
    )
    return [row[0] for row in rows]


def list_tables(conn, database: str) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT TABLE_NAME, IFNULL(TABLE_COMMENT,''), IFNULL(TABLE_ROWS,0) "
            "FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA=:db AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
        ),
        {"db": database},
    )
    return [{"name": r[0], "comment": r[1], "rows": int(r[2] or 0)} for r in rows]


def list_columns(conn, database: str, table: str) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, IFNULL(COLUMN_COMMENT,''), "
            "ORDINAL_POSITION, IFNULL(COLUMN_KEY,'') "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=:db AND TABLE_NAME=:tb "
            "ORDER BY ORDINAL_POSITION"
        ),
        {"db": database, "tb": table},
    )
    return [
        {
            "name": r[0],
            "dataType": r[1],
            "columnType": r[2],
            "nullable": r[3] == "YES",
            "comment": r[4],
            "position": int(r[5]),
            "columnKey": r[6],
        }
        for r in rows
    ]


def preview(conn, database: str, table: str, limit: int = 20) -> dict:
    from app.metrics.sqlgen import quote_ident, table_ref

    limit = max(1, min(int(limit or 20), 200))
    sql = f"SELECT * FROM {table_ref(database, table)} LIMIT {limit}"
    result = conn.execute(text(sql))
    columns = list(result.keys())
    records = []
    for row in result:
        records.append({col: _cell(row[idx]) for idx, col in enumerate(columns)})
    return {"columns": columns, "records": records, "sql": sql}


def execute_select(conn, script: str, limit: int = 100) -> dict:
    sql = (script or "").strip().rstrip(";")
    if not sql or ";" in sql:
        raise ValueError("只允许单条查询")
    head = sql.lstrip().lower()
    if not (head.startswith("select") or head.startswith("with") or head.startswith("show") or head.startswith("desc")):
        raise ValueError("预览只允许 SELECT / SHOW / DESC")
    if head.startswith("select") and " limit " not in head:
        sql = f"{sql} LIMIT {max(1, min(int(limit or 100), 200))}"
    result = conn.execute(text(sql))
    columns = list(result.keys())
    records = [{col: _cell(row[idx]) for idx, col in enumerate(columns)} for row in result]
    return {"columns": columns, "records": records, "sql": sql}


def run_statements(conn, script: str | None) -> None:
    if not script or not str(script).strip():
        return
    parts = [p.strip() for p in str(script).split(";") if p.strip()]
    for part in parts:
        conn.execute(text(part))


def _cell(value):
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ", timespec="seconds") if hasattr(value, "timetz") or hasattr(value, "hour") else value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "as_tuple"):  # Decimal
        return float(value)
    return value
