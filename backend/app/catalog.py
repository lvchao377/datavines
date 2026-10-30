"""Catalog sync, schema-change detection, tags and a simple lineage graph."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.connectors import create_source_engine, list_columns, list_databases, list_tables, validate_param
from app.models import (
    CatalogEntityInstance,
    CatalogEntityMetricJobRel,
    CatalogEntityProfile,
    CatalogEntityRel,
    CatalogEntityTagRel,
    CatalogSchemaChange,
    CatalogTag,
    CatalogTagCategory,
    DataSource,
    Job,
)
from app.util import parse_json

SYSTEM_DBS = {"information_schema", "mysql", "performance_schema", "sys"}


def _uid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _loads(text: str | None) -> dict:
    data = parse_json(text, {})
    return data if isinstance(data, dict) else {}


def get_entity(session: Session, datasource_id: int, fqn: str) -> CatalogEntityInstance | None:
    return (
        session.query(CatalogEntityInstance)
        .filter(
            CatalogEntityInstance.datasource_id == datasource_id,
            CatalogEntityInstance.fully_qualified_name == fqn,
            CatalogEntityInstance.status == "active",
        )
        .one_or_none()
    )


def _upsert(session: Session, datasource_id: int, entity_type: str, fqn: str, display: str, properties: dict, description: str | None = None) -> tuple[CatalogEntityInstance, bool]:
    row = get_entity(session, datasource_id, fqn)
    created = False
    blob = json.dumps(properties, ensure_ascii=False)
    if row is None:
        row = CatalogEntityInstance(
            uuid=_uid(),
            type=entity_type,
            datasource_id=datasource_id,
            fully_qualified_name=fqn,
            display_name=display,
            description=description,
            properties=blob,
            version="1.0",
            status="active",
            update_by=settings.default_user_id,
        )
        session.add(row)
        session.flush()
        created = True
    else:
        row.properties = blob
        row.display_name = display
        row.description = description
        row.update_by = settings.default_user_id
        row.update_time = _now()
    return row, created


def _ensure_child(session: Session, parent_uuid: str, child_uuid: str) -> None:
    exists = (
        session.query(CatalogEntityRel)
        .filter(
            CatalogEntityRel.entity1_uuid == parent_uuid,
            CatalogEntityRel.entity2_uuid == child_uuid,
            CatalogEntityRel.type == "child",
        )
        .one_or_none()
    )
    if exists is None:
        session.add(
            CatalogEntityRel(
                entity1_uuid=parent_uuid,
                entity2_uuid=child_uuid,
                type="child",
                source_type="metadata",
                update_by=settings.default_user_id,
            )
        )


def _mark_deleted(session: Session, row: CatalogEntityInstance) -> None:
    row.status = f"deleted-{uuid.uuid4().hex[:12]}"
    row.update_time = _now()
    row.update_by = settings.default_user_id


def _change(session, parent_uuid, entity_uuid, change_type, database, table, column, before, after) -> None:
    session.add(
        CatalogSchemaChange(
            parent_uuid=parent_uuid or entity_uuid,
            entity_uuid=entity_uuid,
            change_type=change_type,
            database_name=database,
            table_name=table,
            column_name=column,
            change_before=before,
            change_after=after,
            update_by=settings.default_user_id,
        )
    )


def refresh_datasource_safe(session: Session, datasource_id: int, database: str | None = None) -> dict:
    """Sync metadata and record column type changes using snapshots taken before update."""
    ds = session.get(DataSource, datasource_id)
    if ds is None:
        raise ValueError("数据源不存在")
    param = validate_param(_loads(ds.param), ds.type)
    engine = create_source_engine(param)
    added = deleted = changed = 0
    try:
        with engine.connect() as conn:
            databases = [database] if database else [d for d in list_databases(conn) if d not in SYSTEM_DBS]
            active = (
                session.query(CatalogEntityInstance)
                .filter(CatalogEntityInstance.datasource_id == datasource_id, CatalogEntityInstance.status == "active")
                .all()
            )
            by_fqn = {row.fully_qualified_name: row for row in active}
            snapshots = {row.fully_qualified_name: _loads(row.properties) for row in active}
            seen = set()
            for db_name in databases:
                seen.add(db_name)
                db_entity = _touch(session, by_fqn, datasource_id, "database", db_name, db_name, {"database": db_name}, None)
                if db_name not in snapshots:
                    added += 1
                    _change(session, db_entity.uuid, db_entity.uuid, "DATABASE_ADDED", db_name, None, None, None, db_name)
                tables = list_tables(conn, db_name)
                seen_tables = set()
                for table in tables:
                    tfqn = f"{db_name}.{table['name']}"
                    seen.add(tfqn)
                    seen_tables.add(tfqn)
                    props = {"database": db_name, "table": table["name"], "rows": table["rows"], "comment": table["comment"]}
                    table_entity = _touch(session, by_fqn, datasource_id, "table", tfqn, table["name"], props, table["comment"])
                    _ensure_child(session, db_entity.uuid, table_entity.uuid)
                    if tfqn not in snapshots:
                        added += 1
                        _change(session, db_entity.uuid, table_entity.uuid, "TABLE_ADDED", db_name, table["name"], None, None, table["name"])
                    cols = list_columns(conn, db_name, table["name"])
                    seen_cols = set()
                    for col in cols:
                        cfqn = f"{tfqn}.{col['name']}"
                        seen.add(cfqn)
                        seen_cols.add(cfqn)
                        cprops = {
                            "database": db_name,
                            "table": table["name"],
                            "column": col["name"],
                            "dataType": col["dataType"],
                            "columnType": col["columnType"],
                            "nullable": col["nullable"],
                            "comment": col["comment"],
                            "position": col["position"],
                            "columnKey": col["columnKey"],
                        }
                        col_entity = _touch(session, by_fqn, datasource_id, "column", cfqn, col["name"], cprops, col["comment"])
                        _ensure_child(session, table_entity.uuid, col_entity.uuid)
                        old = snapshots.get(cfqn)
                        if old is None:
                            added += 1
                            _change(session, table_entity.uuid, col_entity.uuid, "COLUMN_ADDED", db_name, table["name"], col["name"], None, col["columnType"])
                        elif old.get("columnType") != col["columnType"]:
                            changed += 1
                            _change(
                                session,
                                table_entity.uuid,
                                col_entity.uuid,
                                "COLUMN_TYPE_CHANGED",
                                db_name,
                                table["name"],
                                col["name"],
                                old.get("columnType"),
                                col["columnType"],
                            )
                    for cfqn, old_row in list(by_fqn.items()):
                        if old_row.type == "column" and old_row.fully_qualified_name.startswith(tfqn + ".") and cfqn not in seen_cols and old_row.status == "active":
                            _mark_deleted(session, old_row)
                            deleted += 1
                            _change(session, table_entity.uuid, old_row.uuid, "COLUMN_DELETED", db_name, table["name"], old_row.display_name, snapshots.get(cfqn, {}).get("columnType"), None)
                for fqn, old_row in list(by_fqn.items()):
                    if old_row.type == "table" and old_row.fully_qualified_name.startswith(db_name + ".") and old_row.fully_qualified_name.count(".") == 1 and fqn not in seen_tables and old_row.status == "active":
                        _mark_deleted(session, old_row)
                        deleted += 1
                        _change(session, db_entity.uuid, old_row.uuid, "TABLE_DELETED", db_name, old_row.display_name, None, old_row.display_name, None)
            if database is None:
                for fqn, old_row in list(by_fqn.items()):
                    if old_row.type == "database" and fqn not in seen and old_row.status == "active":
                        _mark_deleted(session, old_row)
                        deleted += 1
                        _change(session, old_row.uuid, old_row.uuid, "DATABASE_DELETED", fqn, None, None, fqn, None)
        session.commit()
    finally:
        engine.dispose()
    return {"added": added, "deleted": deleted, "changed": changed}


def _touch(session, by_fqn, datasource_id, entity_type, fqn, display, properties, description):
    row = by_fqn.get(fqn)
    blob = json.dumps(properties, ensure_ascii=False)
    if row is None or row.status != "active":
        row = CatalogEntityInstance(
            uuid=_uid(),
            type=entity_type,
            datasource_id=datasource_id,
            fully_qualified_name=fqn,
            display_name=display,
            description=description,
            properties=blob,
            version="1.0",
            status="active",
            update_by=settings.default_user_id,
        )
        session.add(row)
        session.flush()
        by_fqn[fqn] = row
    else:
        row.properties = blob
        row.display_name = display
        row.description = description
        row.update_time = _now()
        row.update_by = settings.default_user_id
    return row


def bind_job(session: Session, job: Job) -> None:
    fqn = None
    if job.schema_name and job.table_name and job.column_name:
        fqn = f"{job.schema_name}.{job.table_name}.{job.column_name}"
    elif job.schema_name and job.table_name:
        fqn = f"{job.schema_name}.{job.table_name}"
    elif job.schema_name:
        fqn = job.schema_name
    if not fqn:
        return
    entity = get_entity(session, job.datasource_id, fqn)
    if entity is None:
        return
    exists = (
        session.query(CatalogEntityMetricJobRel)
        .filter(
            CatalogEntityMetricJobRel.entity_uuid == entity.uuid,
            CatalogEntityMetricJobRel.metric_job_id == job.id,
            CatalogEntityMetricJobRel.metric_job_type == (job.metric_type or "job"),
        )
        .one_or_none()
    )
    if exists is None:
        session.add(
            CatalogEntityMetricJobRel(
                entity_uuid=entity.uuid,
                metric_job_id=job.id,
                metric_job_type=job.metric_type or "job",
                create_by=settings.default_user_id,
                update_by=settings.default_user_id,
            )
        )


def children(session: Session, parent_uuid: str, entity_type: str | None = None) -> list[CatalogEntityInstance]:
    rels = session.query(CatalogEntityRel).filter(CatalogEntityRel.entity1_uuid == parent_uuid, CatalogEntityRel.type == "child").all()
    ids = [rel.entity2_uuid for rel in rels]
    if not ids:
        return []
    query = session.query(CatalogEntityInstance).filter(CatalogEntityInstance.uuid.in_(ids), CatalogEntityInstance.status == "active")
    if entity_type:
        query = query.filter(CatalogEntityInstance.type == entity_type)
    return query.order_by(CatalogEntityInstance.display_name.asc()).all()


def lineage(session: Session, entity_uuid: str) -> dict:
    node = session.query(CatalogEntityInstance).filter(CatalogEntityInstance.uuid == entity_uuid).one_or_none()
    if node is None:
        raise ValueError("实体不存在")
    rels = (
        session.query(CatalogEntityRel)
        .filter(
            ((CatalogEntityRel.entity1_uuid == entity_uuid) | (CatalogEntityRel.entity2_uuid == entity_uuid)),
            CatalogEntityRel.type.in_(["upstream", "downstream"]),
        )
        .all()
    )
    uuids = {entity_uuid}
    edges = []
    for rel in rels:
        uuids.add(rel.entity1_uuid)
        uuids.add(rel.entity2_uuid)
        edges.append({"from": rel.entity1_uuid, "to": rel.entity2_uuid, "type": rel.type, "sourceType": rel.source_type})
    nodes = session.query(CatalogEntityInstance).filter(CatalogEntityInstance.uuid.in_(uuids)).all()
    return {
        "nodes": [
            {"uuid": n.uuid, "fqn": n.fully_qualified_name, "displayName": n.display_name, "type": n.type}
            for n in nodes
        ],
        "edges": edges,
    }


def add_lineage(session: Session, from_uuid: str, to_uuid: str, source_type: str = "manual", script: str | None = None) -> None:
    exists = (
        session.query(CatalogEntityRel)
        .filter(CatalogEntityRel.entity1_uuid == from_uuid, CatalogEntityRel.entity2_uuid == to_uuid, CatalogEntityRel.type == "downstream")
        .one_or_none()
    )
    if exists is None:
        session.add(
            CatalogEntityRel(
                entity1_uuid=from_uuid,
                entity2_uuid=to_uuid,
                type="downstream",
                source_type=source_type,
                related_script=script,
                update_by=settings.default_user_id,
            )
        )


_TABLE_RE = re.compile(r"(?:from|join)\s+`?([A-Za-z_][A-Za-z0-9_]*)`?(?:\.`?([A-Za-z_][A-Za-z0-9_]*)`?)?", re.I)


def parse_lineage_sql(session: Session, datasource_id: int, sql: str) -> int:
    """Best-effort lineage: INSERT target is downstream of FROM/JOIN sources; otherwise chain tables left to right."""
    tables = []
    for match in _TABLE_RE.finditer(sql or ""):
        if match.group(2):
            tables.append(f"{match.group(1)}.{match.group(2)}")
        else:
            tables.append(match.group(1))
    # unique preserve order
    ordered = []
    for name in tables:
        if name not in ordered:
            ordered.append(name)
    catalog_tables = (
        session.query(CatalogEntityInstance)
        .filter(
            CatalogEntityInstance.datasource_id == datasource_id,
            CatalogEntityInstance.status == "active",
            CatalogEntityInstance.type == "table",
        )
        .all()
    )

    def resolve(name: str):
        exact = [row for row in catalog_tables if row.fully_qualified_name == name]
        if len(exact) == 1:
            return exact[0]
        loose = [
            row for row in catalog_tables
            if row.display_name == name or row.fully_qualified_name.endswith("." + name)
        ]
        return loose[0] if len(loose) == 1 else None

    entities = []
    for name in ordered:
        row = resolve(name)
        if row and row not in entities:
            entities.append(row)
    created = 0
    insert = re.search(r"insert\s+into\s+`?([A-Za-z_][A-Za-z0-9_]*)`?(?:\.`?([A-Za-z_][A-Za-z0-9_]*)`?)?", sql or "", re.I)
    if insert:
        target_name = f"{insert.group(1)}.{insert.group(2)}" if insert.group(2) else insert.group(1)
        target = resolve(target_name)
        sources = [entity for entity in entities if target is None or entity.uuid != target.uuid]
        if target and sources:
            for src in sources:
                add_lineage(session, src.uuid, target.uuid, "sql", sql)
                created += 1
            return created
    for left, right in zip(entities, entities[1:]):
        add_lineage(session, left.uuid, right.uuid, "sql", sql)
        created += 1
    return created


def save_profile(session: Session, entity_uuid: str, metric_name: str, actual_value: str, value_type: str, data_date: str) -> None:
    row = (
        session.query(CatalogEntityProfile)
        .filter(
            CatalogEntityProfile.entity_uuid == entity_uuid,
            CatalogEntityProfile.metric_name == metric_name,
            CatalogEntityProfile.data_date == data_date,
        )
        .one_or_none()
    )
    if row is None:
        session.add(
            CatalogEntityProfile(
                entity_uuid=entity_uuid,
                metric_name=metric_name,
                actual_value=actual_value,
                actual_value_type=value_type,
                data_date=data_date,
            )
        )
    else:
        row.actual_value = actual_value
        row.actual_value_type = value_type
        row.update_time = _now()


def refresh_datasource(session: Session, datasource_id: int, database: str | None = None) -> dict:
    """Public entry. The snapshot-based implementation records schema changes correctly."""
    return refresh_datasource_safe(session, datasource_id, database)


def entity_tags(session: Session, entity_uuid: str) -> list[dict]:
    rels = session.query(CatalogEntityTagRel).filter(CatalogEntityTagRel.entity_uuid == entity_uuid).all()
    out = []
    for rel in rels:
        tag = session.query(CatalogTag).filter(CatalogTag.uuid == rel.tag_uuid).one_or_none()
        if tag:
            category = session.query(CatalogTagCategory).filter(CatalogTagCategory.uuid == tag.category_uuid).one_or_none()
            out.append({"uuid": tag.uuid, "name": tag.name, "categoryUuid": tag.category_uuid, "categoryName": category.name if category else ""})
    return out
