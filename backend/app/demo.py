"""Create a demo MySQL schema, datasource, two jobs and a Feishu SLA on the metadata server."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine.url import make_url

from app.config import settings
from app.db import SessionLocal, engine
from app.models import DataSource, Job, Sla, SlaJob, SlaNotification, SlaSender

DEMO_ORDERS = [
    (1, "Alice", "alice@example.com", "10.50", "PAID", "2026-10-01 09:00:00"),
    (2, "Bob", None, "20.00", "PAID", "2026-10-02 09:00:00"),
    (3, "Bob", "bob@example.com", "20.00", "PAID", "2026-10-02 10:00:00"),
    (4, "", "", "0.00", "PENDING", "2026-10-03 09:00:00"),
    (5, "Carol", "not-an-email", "15.00", "SHIPPED", "2026-09-01 09:00:00"),
    (6, "Dave", "dave@example.com", None, "CANCEL", "2026-10-28 09:00:00"),
    (7, "Eve", "eve@example.com", "100.00", "PAID", "2026-10-29 09:00:00"),
    (8, "Frank", "frank@example.com", "5.00", "UNKNOWN", "2026-10-30 09:00:00"),
]

MIRROR = [
    (1, "Alice", "alice@example.com", "10.50", "PAID", "2026-10-01 09:00:00"),
    (2, "Bob", None, "20.00", "PAID", "2026-10-02 09:00:00"),
    (3, "Bob", "bob@example.com", "20.00", "PAID", "2026-10-02 10:00:00"),
    (4, "", "", "0.00", "PENDING", "2026-10-03 09:00:00"),
    (5, "Carol", "not-an-email", "15.00", "SHIPPED", "2026-09-01 09:00:00"),
    (6, "Dave", "dave@example.com", None, "CANCEL", "2026-10-28 09:00:00"),
    (7, "Eve", "eve@example.com", "90.00", "PAID", "2026-10-29 09:00:00"),
]


def _meta():
    url = make_url(settings.database_url)
    return {
        "host": url.host or "127.0.0.1",
        "port": url.port or 3306,
        "user": url.username or "root",
        "password": url.password or "",
    }


def ensure_demo_tables() -> dict:
    meta = _meta()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("CREATE DATABASE IF NOT EXISTS demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    from app.connectors import create_source_engine

    src = create_source_engine({**meta, "database": "demo"})
    try:
        with src.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS orders (
                      id INT PRIMARY KEY,
                      customer VARCHAR(64),
                      email VARCHAR(128),
                      amount DECIMAL(10,2),
                      status VARCHAR(32),
                      created_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS orders_mirror (
                      id INT PRIMARY KEY,
                      customer VARCHAR(64),
                      email VARCHAR(128),
                      amount DECIMAL(10,2),
                      status VARCHAR(32),
                      created_at DATETIME
                    )
                    """
                )
            )
            count = conn.execute(text("SELECT COUNT(1) FROM orders")).scalar()
            if not count:
                conn.execute(
                    text("INSERT INTO orders (id, customer, email, amount, status, created_at) VALUES (:id,:customer,:email,:amount,:status,:created_at)"),
                    [
                        {"id": r[0], "customer": r[1], "email": r[2], "amount": r[3], "status": r[4], "created_at": r[5]}
                        for r in DEMO_ORDERS
                    ],
                )
            mirror_count = conn.execute(text("SELECT COUNT(1) FROM orders_mirror")).scalar()
            if not mirror_count:
                conn.execute(
                    text("INSERT INTO orders_mirror (id, customer, email, amount, status, created_at) VALUES (:id,:customer,:email,:amount,:status,:created_at)"),
                    [
                        {"id": r[0], "customer": r[1], "email": r[2], "amount": r[3], "status": r[4], "created_at": r[5]}
                        for r in MIRROR
                    ],
                )
    finally:
        src.dispose()
    return meta


def _job_parameter(metric, column, expected_type, expected_value, formula, operator, threshold, extra=None):
    metric_parameter = {"database": "demo", "table": "orders", "column": column}
    if extra:
        metric_parameter.update(extra)
    return {
        "metricType": metric,
        "metricParameter": metric_parameter,
        "expectedType": expected_type,
        "expectedParameter": {"expected_value": expected_value} if expected_value is not None else {},
        "resultFormula": formula,
        "operator": operator,
        "threshold": threshold,
    }


def apply_schema_change() -> dict:
    """Add demo.orders.note when missing, then refresh the catalog so a COLUMN_ADDED change is visible."""
    from app.catalog import refresh_datasource
    from app.connectors import create_source_engine

    meta = _meta()
    src = create_source_engine({**meta, "database": "demo"})
    try:
        with src.begin() as conn:
            exists = conn.execute(text("SHOW COLUMNS FROM orders LIKE 'note'")).fetchall()
            if not exists:
                conn.execute(text("ALTER TABLE orders ADD COLUMN note VARCHAR(64) NULL"))
    finally:
        src.dispose()
    with SessionLocal() as session:
        ds = session.query(DataSource).filter(DataSource.name == "demo-mysql").one_or_none()
        if ds is None:
            raise ValueError("请先初始化 Demo 数据源")
        return refresh_datasource(session, ds.id, "demo")


def bootstrap_demo(workspace_id: int | None = None, user_id: int | None = None) -> dict:
    from app.catalog import bind_job, refresh_datasource

    meta = ensure_demo_tables()
    param = {**meta, "database": "demo"}
    wid = int(workspace_id or settings.default_workspace_id)
    uid = int(user_id or settings.default_user_id)
    with SessionLocal() as session:
        ds = session.query(DataSource).filter(DataSource.name == "demo-mysql").one_or_none()
        if ds is not None and int(ds.workspace_id) != wid:
            raise ValueError("Demo 数据源属于其他工作空间")
        if ds is None:
            ds = DataSource(
                uuid=uuid.uuid4().hex,
                name="demo-mysql",
                category="database",
                type="mysql",
                param=json.dumps(param),
                workspace_id=wid,
                create_by=uid,
                update_by=uid,
            )
            session.add(ds)
            session.flush()
        else:
            ds.param = json.dumps(param)
            ds.type = "mysql"
        refresh_datasource(session, ds.id, "demo")
        specs = [
            (
                "demo_email_null_check",
                "column_null",
                "email",
                _job_parameter("column_null", "email", "fix_value", "0", "count", "eq", "0"),
            ),
            (
                "demo_orders_row_count",
                "table_row_count",
                None,
                _job_parameter("table_row_count", None, "fix_value", "8", "count", "eq", "8", extra={"column": None}),
            ),
        ]
        job_ids = {}
        for name, metric, column, parameter in specs:
            parameter["metricParameter"].pop("column", None) if column is None else None
            if column is None:
                parameter["metricParameter"].pop("column", None)
            job = (
                session.query(Job)
                .filter(Job.name == name, Job.datasource_id == ds.id)
                .one_or_none()
            )
            if job is None:
                job = Job(
                    name=name,
                    type=0,
                    datasource_id=ds.id,
                    schema_name="demo",
                    table_name="orders",
                    column_name=column,
                    metric_type=metric,
                    engine_type="local",
                    execute_platform_type="local",
                    parameter=json.dumps(parameter, ensure_ascii=False),
                    retry_times=0,
                    retry_interval=1,
                    timeout=120,
                    timeout_strategy=0,
                    create_by=uid,
                    update_by=uid,
                )
                session.add(job)
                session.flush()
            job_ids[name] = job.id
            bind_job(session, job)
        sender = session.query(SlaSender).filter(SlaSender.name == "demo-feishu-mock").one_or_none()
        webhook = f"http://127.0.0.1:{settings.port}/api/v1/sla/mock/receive"
        if sender is None:
            sender = SlaSender(
                type="feishu",
                name="demo-feishu-mock",
                workspace_id=wid,
                config=json.dumps({"webhook": webhook}),
                create_by=uid,
                update_by=uid,
            )
            session.add(sender)
            session.flush()
        sla = session.query(Sla).filter(Sla.name == "demo-null-sla").one_or_none()
        if sla is None:
            sla = Sla(
                workspace_id=wid,
                name="demo-null-sla",
                description="邮箱空值检查失败时通知飞书（默认打到内置 mock）",
                create_by=uid,
                update_by=uid,
            )
            session.add(sla)
            session.flush()
        link = (
            session.query(SlaJob)
            .filter(SlaJob.sla_id == sla.id, SlaJob.job_id == job_ids["demo_email_null_check"])
            .one_or_none()
        )
        if link is None:
            session.add(
                SlaJob(
                    workspace_id=wid,
                    sla_id=sla.id,
                    job_id=job_ids["demo_email_null_check"],
                    create_by=uid,
                    update_by=uid,
                )
            )
        note = session.query(SlaNotification).filter(SlaNotification.sla_id == sla.id).one_or_none()
        if note is None:
            session.add(
                SlaNotification(
                    type="feishu",
                    workspace_id=wid,
                    sla_id=sla.id,
                    sender_id=sender.id,
                    config=json.dumps({"atAll": False}),
                    create_by=uid,
                    update_by=uid,
                )
            )
        session.commit()
        return {"datasourceId": ds.id, "jobs": job_ids, "slaId": sla.id, "webhook": webhook, "param": {**param, "password": "******"}}
