"""Catalog sync, profile, lineage and the Doris connector path against the local MySQL protocol server."""

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine


def _mysql_up() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _mysql_up(), reason="metadata MySQL is not reachable")
def test_doris_connector_can_use_mysql_protocol_server():
    from sqlalchemy.engine.url import make_url

    from app.config import settings
    from app.connectors import list_databases, test_connection
    from app.connectors import create_source_engine, validate_param

    url = make_url(settings.database_url)
    param = validate_param(
        {
            "host": url.host or "127.0.0.1",
            "port": url.port or 3306,
            "user": url.username,
            "password": url.password or "",
            "database": "demo",
        },
        "doris",
    )
    test_connection("doris", param)
    engine_ds = create_source_engine(param)
    try:
        with engine_ds.connect() as conn:
            names = list_databases(conn)
        assert "demo" in names
    finally:
        engine_ds.dispose()


@pytest.mark.skipif(not _mysql_up(), reason="metadata MySQL is not reachable")
def test_catalog_schema_change_profile_and_lineage():
    from app.bootstrap import init_database
    from app.catalog import get_entity, parse_lineage_sql, refresh_datasource
    from app.connectors import create_source_engine, validate_param
    from app.demo import bootstrap_demo
    from app.models import CatalogEntityMetricJobRel, CatalogEntityProfile, CatalogSchemaChange, DataSource, Job
    from app.profile import profile_table
    from sqlalchemy.engine.url import make_url
    from app.config import settings

    init_database()
    info = bootstrap_demo()
    url = make_url(settings.database_url)
    param = validate_param(
        {
            "host": url.host or "127.0.0.1",
            "port": url.port or 3306,
            "user": url.username,
            "password": url.password or "",
            "database": "demo",
        },
        "mysql",
    )
    src = create_source_engine(param)
    try:
        with src.begin() as conn:
            conn.execute(text("ALTER TABLE orders DROP COLUMN IF EXISTS qa_probe"))
            conn.execute(text("ALTER TABLE orders ADD COLUMN qa_probe VARCHAR(16) NULL"))
    finally:
        src.dispose()

    with SessionLocal() as session:
        refresh_datasource(session, info["datasourceId"], "demo")
        added = (
            session.query(CatalogSchemaChange)
            .filter(CatalogSchemaChange.column_name == "qa_probe", CatalogSchemaChange.change_type == "COLUMN_ADDED")
            .count()
        )
        assert added >= 1
        column = get_entity(session, info["datasourceId"], "demo.orders.email")
        table = get_entity(session, info["datasourceId"], "demo.orders")
        assert column is not None and table is not None
        job = session.query(Job).filter(Job.id == info["jobs"]["demo_email_null_check"]).one()
        rel = (
            session.query(CatalogEntityMetricJobRel)
            .filter(CatalogEntityMetricJobRel.metric_job_id == job.id, CatalogEntityMetricJobRel.entity_uuid == column.uuid)
            .one_or_none()
        )
        assert rel is not None
        summary = profile_table(session, info["datasourceId"], "demo", "orders", ["email"])
        assert summary["rowCount"] == 8
        email = summary["columns"][0]["metrics"]
        assert email["column_null"] == 1
        assert email["column_blank"] == 2
        assert isinstance(email["column_histogram"], list) and email["column_histogram"]
        stored = (
            session.query(CatalogEntityProfile)
            .filter(CatalogEntityProfile.entity_uuid == table.uuid, CatalogEntityProfile.metric_name == "table_row_count")
            .all()
        )
        assert stored
        edges = parse_lineage_sql(session, info["datasourceId"], "insert into orders_mirror select * from orders")
        session.commit()
        assert edges >= 1

    src = create_source_engine(param)
    try:
        with src.begin() as conn:
            conn.execute(text("ALTER TABLE orders MODIFY COLUMN qa_probe VARCHAR(64) NULL"))
    finally:
        src.dispose()
    with SessionLocal() as session:
        refresh_datasource(session, info["datasourceId"], "demo")
        changed = (
            session.query(CatalogSchemaChange)
            .filter(CatalogSchemaChange.column_name == "qa_probe", CatalogSchemaChange.change_type == "COLUMN_TYPE_CHANGED")
            .count()
        )
        assert changed >= 1
