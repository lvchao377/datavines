"""HTTP routes aligned with DataVines /api/v1 controllers.

Responses use {code, msg, data}. Upstream sometimes returned the payload
directly; this clone always wraps it so the React client can unwrap `data`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_token, hash_password, member_workspace_ids, verify_password
from app.catalog import (
    add_lineage,
    bind_job,
    children,
    entity_tags,
    get_entity,
    lineage,
    parse_lineage_sql,
    refresh_datasource,
)
from app.config import settings
from app.connectors import execute_select, list_columns, list_databases, list_tables, preview, test_connection, type_items, validate_param
from app.constants import EXEC_STATUS_LABEL
from app.db import get_db
from app.demo import apply_schema_change, bootstrap_demo
from app.metrics.judge import EXPECTED_TYPES, FORMULAS, OPERATORS
from app.metrics.registry import get_metric, list_metrics
from app.metrics.sqlgen import build_sql
from app.models import (
    AccessToken,
    AlertSendLog,
    CatalogEntityInstance,
    CatalogEntityRel,
    CatalogEntityProfile,
    CatalogSchemaChange,
    CatalogTag,
    CatalogTagCategory,
    CatalogEntityTagRel,
    CommonTask,
    CommonTaskSchedule,
    Config,
    DataSource,
    Env,
    ErrorDataRow,
    ErrorDataStorage,
    Issue,
    Job,
    JobExecution,
    JobExecutionResult,
    JobIssueRel,
    JobQualityReport,
    JobSchedule,
    MetricPayload,
    Sla,
    SlaJob,
    SlaNotification,
    SlaSender,
    Tenant,
    User,
    UserWorkspace,
    Workspace,
)
from app.scheduler import cron_due, enqueue_common, enqueue_job, enqueue_stop, normalize_cron, upcoming
from app.util import as_int, dump_row, fail, json_text, ok, page_payload, parse_json

router = APIRouter()


def _pick(data: dict, *keys, default=None):
    for key in keys:
        if isinstance(data, dict) and key in data and data[key] is not None:
            return data[key]
    return default


def _page_args(data_or_query, page_number=None, page_size=None):
    if isinstance(data_or_query, dict):
        page = as_int(_pick(data_or_query, "pageNumber", "page", "current", default=page_number or 1), 1)
        size = as_int(_pick(data_or_query, "pageSize", "size", default=page_size or 10), 10)
    else:
        page = as_int(page_number, 1)
        size = as_int(page_size, 10)
    return max(page, 1), min(max(size, 1), 200)


def _slice(query, page, size):
    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return total, rows


def _actor(request: Request, db: Session) -> User | None:
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        return None
    return db.get(User, int(uid))


def _user_view(db: Session, user: User) -> dict:
    links = db.query(UserWorkspace).filter(UserWorkspace.user_id == user.id).all()
    spaces = []
    for link in links:
        workspace = db.get(Workspace, link.workspace_id)
        if workspace is not None:
            spaces.append({"id": workspace.id, "name": workspace.name})
    return {
        "id": user.id,
        "userId": user.id,
        "username": user.username,
        "email": user.email,
        "admin": bool(user.admin),
        "workspaceId": spaces[0]["id"] if spaces else None,
        "workspaces": spaces,
    }


def _owns_workspace(db: Session, user: User, workspace_id: int) -> bool:
    return int(workspace_id) in member_workspace_ids(db, user.id)


# ---------- health / identity ----------

@router.get("/health")
def health():
    return ok({"status": "up", "engine": {"local": True, "spark": False}, "alerts": ["feishu"]})


@router.post("/login")
def login(body: dict, db: Session = Depends(get_db)):
    username = str(_pick(body, "username", default="") or "").strip()
    password = str(_pick(body, "password", default="") or "")
    user = db.query(User).filter(User.username == username).one_or_none()
    if user is None or not verify_password(password, user.password):
        return fail("用户名或密码错误", 400)
    token = create_token(user)
    data = _user_view(db, user)
    data["token"] = token
    return {"code": 200, "msg": "Success", "token": token, "data": data}


@router.post("/register")
def register(body: dict, db: Session = Depends(get_db)):
    username = str(_pick(body, "username", default="") or "").strip()
    password = str(_pick(body, "password", default="") or "")
    email = str(_pick(body, "email", default="") or "").strip()
    if not username or not password or not email:
        return fail("用户名、邮箱和密码不能为空")
    if len(password) < 6:
        return fail("密码至少 6 位")
    if db.query(User).filter(User.username == username).first():
        return fail("用户名已注册")
    user = User(username=username, password=hash_password(password), email=email, phone=_pick(body, "phone"), admin=0)
    db.add(user)
    db.flush()
    workspace_name = f"{username}'s default"
    if db.query(Workspace).filter(Workspace.name == workspace_name).first():
        workspace_name = f"{username}'s default {user.id}"
    workspace = Workspace(name=workspace_name, create_by=user.id, update_by=user.id)
    db.add(workspace)
    db.flush()
    db.add(
        UserWorkspace(
            user_id=user.id,
            workspace_id=workspace.id,
            role_id=1,
            create_by=user.id,
            update_by=user.id,
        )
    )
    db.commit()
    db.refresh(user)
    return ok(_user_view(db, user))


@router.get("/user/info")
def user_info(request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    return ok(_user_view(db, user))


@router.get("/user/list")
def user_list(request: Request, workspaceId: int | None = None, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    allowed = member_workspace_ids(db, user.id)
    if workspaceId is not None and int(workspaceId) not in allowed:
        return fail("无权查看该工作空间的用户", 403)
    if user.admin and workspaceId is None:
        rows = db.query(User).order_by(User.id).all()
    else:
        target = int(workspaceId) if workspaceId is not None else (min(allowed) if allowed else None)
        if target is None:
            return ok([])
        member_ids = [
            row.user_id
            for row in db.query(UserWorkspace).filter(UserWorkspace.workspace_id == target).all()
        ]
        rows = db.query(User).filter(User.id.in_(member_ids or [-1])).order_by(User.id).all()
    return ok([_user_view(db, row) for row in rows])


@router.get("/workspace/list")
def workspace_list(request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    return ok(_user_view(db, user)["workspaces"])


# ---------- metrics ----------

def _item(label, value, **extra):
    data = {"label": label, "value": value, "name": label, "key": value}
    data.update(extra)
    return data


@router.get("/metric/list")
def metric_list():
    return ok([_item(m.zh_name, m.name, dimension=m.dimension, level=m.level) for m in list_metrics()])


@router.get("/metric/list/{type}")
def metric_list_by_type(type: str):
    items = []
    for metric in list_metrics():
        if type == "DATA_QUALITY" and metric.single_table and not metric.exclude_from_quality_list:
            items.append(_item(metric.zh_name, metric.name, level=metric.level))
        elif type == "DATA_RECONCILIATION" and not metric.single_table:
            items.append(_item(metric.zh_name, metric.name, level=metric.level))
    return ok(items)


@router.get("/metric/reconciliation/list")
def reconciliation_list():
    return ok([_item(m.zh_name, m.name) for m in list_metrics() if not m.single_table])


@router.get("/metric/quality/list/{level}")
def quality_list(level: str):
    return ok([
        _item(m.zh_name, m.name)
        for m in list_metrics()
        if m.single_table and m.level == level and not m.exclude_from_quality_list
    ])


@router.get("/metric/configs/{name}")
def metric_configs(name: str):
    try:
        metric = get_metric(name)
    except KeyError as exc:
        return fail(str(exc))
    return ok([{"label": item["label"], "key": item["key"], "supportMultiple": item["supportMultiple"]} for item in metric.configs])


@router.get("/metric/expectedValue/list/{type}")
def expected_list(type: str):
    items = []
    for item in EXPECTED_TYPES:
        if type == "DATA_QUALITY" and item["value"] == "target_table_total_rows":
            continue
        items.append(_item(item["label"], item["value"]))
    return ok(items)


@router.get("/metric/engine/list")
def engine_list():
    return ok([
        _item("local", "local", implemented=True),
        _item("spark", "spark", implemented=False, note="接口占位，执行会失败"),
    ])


@router.get("/metric/resultFormula/list")
def formula_list():
    return ok([_item(item["label"], item["value"], symbol=item["symbol"], formulaType=item["type"]) for item in FORMULAS])


@router.get("/metric/operator/list")
def operator_list():
    return ok([_item(item["label"], item["value"], symbol=item["symbol"]) for item in OPERATORS])


@router.post("/metric/sql/preview")
def sql_preview(body: dict):
    try:
        metric = _pick(body, "metricType", "metric", "name")
        params = _pick(body, "metricParameter", "parameter", default=body)
        plan = build_sql(metric, params)
    except (KeyError, ValueError) as exc:
        return fail(str(exc))
    return ok(plan.as_dict())


# ---------- datasource ----------

@router.get("/datasource/type/list")
def ds_types():
    return ok(type_items())


@router.get("/datasource/config/{dtype}")
def ds_config(dtype: str):
    port = 9030 if dtype.lower() == "doris" else 3306
    return ok([
        {"key": "host", "label": "主机", "required": True},
        {"key": "port", "label": "端口", "required": True, "default": port},
        {"key": "database", "label": "数据库", "required": False},
        {"key": "user", "label": "用户名", "required": True},
        {"key": "password", "label": "密码", "required": False},
    ])


@router.post("/datasource/test")
def ds_test(body: dict):
    try:
        test_connection(_pick(body, "type", default="mysql"), _pick(body, "param", "parameter", default=body))
    except Exception as exc:
        return fail(f"连接失败: {exc}")
    return ok(True, "Connection test succeeded")


def _deny_datasource(request: Request, db: Session, row: DataSource | None):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    if row is None:
        return fail("数据源不存在", 404)
    if not _owns_workspace(db, user, row.workspace_id):
        return fail("无权访问该数据源", 403)
    return None


@router.get("/datasource/page")
def ds_page(
    request: Request,
    searchVal: str | None = None,
    pageNumber: int = 1,
    pageSize: int = 10,
    workspaceId: int | None = None,
    db: Session = Depends(get_db),
):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    allowed = member_workspace_ids(db, user.id)
    query = db.query(DataSource)
    if workspaceId is not None:
        if int(workspaceId) not in allowed:
            return fail("无权访问该工作空间的数据源", 403)
        query = query.filter(DataSource.workspace_id == int(workspaceId))
    else:
        query = query.filter(DataSource.workspace_id.in_(allowed or [-1]))
    if searchVal:
        query = query.filter(DataSource.name.like(f"%{searchVal}%"))
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(DataSource.id.desc()), page, size)
    return ok(page_payload([dump_row(row, mask_password=True) for row in rows], total, page, size))


@router.get("/datasource/list/{workspace_id}/{dtype}")
def ds_list(workspace_id: int, dtype: str, request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    if not _owns_workspace(db, user, workspace_id):
        return fail("无权访问该工作空间的数据源", 403)
    rows = db.query(DataSource).filter(DataSource.workspace_id == workspace_id, DataSource.type == dtype).all()
    return ok([dump_row(row, mask_password=True) for row in rows])


@router.post("/datasource")
def ds_create(body: dict, request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    try:
        dtype = str(_pick(body, "type", default="mysql")).lower()
        param = validate_param(_pick(body, "param", default={}), dtype)
    except ValueError as exc:
        return fail(str(exc))
    name = _pick(body, "name")
    if not name:
        return fail("名称不能为空")
    allowed = member_workspace_ids(db, user.id)
    workspace_id = _pick(body, "workspaceId", "workspace_id")
    workspace_id = int(workspace_id) if workspace_id else (min(allowed) if allowed else None)
    if workspace_id is None or workspace_id not in allowed:
        return fail("无权在该工作空间创建数据源", 403)
    if db.query(DataSource).filter(DataSource.name == name).first():
        return fail("数据源名称已存在")
    row = DataSource(
        uuid=uuid.uuid4().hex,
        name=name,
        category=_pick(body, "category", default="database"),
        type=dtype,
        param=json.dumps(param),
        workspace_id=workspace_id,
        create_by=user.id,
        update_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(dump_row(row, mask_password=True))


@router.put("/datasource")
def ds_update(body: dict, request: Request, db: Session = Depends(get_db)):
    row = db.get(DataSource, _pick(body, "id"))
    denied = _deny_datasource(request, db, row)
    if denied:
        return denied
    if _pick(body, "name"):
        row.name = _pick(body, "name")
    if _pick(body, "type"):
        row.type = str(_pick(body, "type")).lower()
    if _pick(body, "param") is not None:
        try:
            param = validate_param(_pick(body, "param"), row.type)
        except ValueError as exc:
            return fail(str(exc))
        row.param = json.dumps(param)
    row.update_by = _actor(request, db).id
    db.commit()
    return ok(dump_row(row, mask_password=True))


@router.delete("/datasource/{datasource_id}")
def ds_delete(datasource_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(DataSource, datasource_id)
    denied = _deny_datasource(request, db, row)
    if denied:
        return denied
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/datasource/{datasource_id}")
def ds_get(datasource_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(DataSource, datasource_id)
    denied = _deny_datasource(request, db, row)
    if denied:
        return denied
    return ok(dump_row(row))


def _open_or_fail(request: Request, db: Session, datasource_id: int):
    row = db.get(DataSource, datasource_id)
    denied = _deny_datasource(request, db, row)
    if denied is not None:
        return None, denied
    from app.connectors import create_source_engine

    param = validate_param(parse_json(row.param, {}), row.type)
    return (row, create_source_engine(param), param), None


@router.get("/datasource/{datasource_id}/databases")
def ds_databases(datasource_id: int, request: Request, db: Session = Depends(get_db)):
    opened, denied = _open_or_fail(request, db, datasource_id)
    if denied:
        return denied
    _, eng, _ = opened
    try:
        with eng.connect() as conn:
            data = list_databases(conn)
        eng.dispose()
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


@router.get("/datasource/{datasource_id}/{database}/tables")
def ds_tables(datasource_id: int, database: str, request: Request, db: Session = Depends(get_db)):
    opened, denied = _open_or_fail(request, db, datasource_id)
    if denied:
        return denied
    _, eng, _ = opened
    try:
        with eng.connect() as conn:
            data = list_tables(conn, database)
        eng.dispose()
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


@router.get("/datasource/{datasource_id}/{database}/{table}/columns")
def ds_columns(datasource_id: int, database: str, table: str, request: Request, db: Session = Depends(get_db)):
    opened, denied = _open_or_fail(request, db, datasource_id)
    if denied:
        return denied
    _, eng, _ = opened
    try:
        with eng.connect() as conn:
            data = list_columns(conn, database, table)
        eng.dispose()
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


@router.get("/datasource/{datasource_id}/{database}/{table}/preview")
def ds_preview(datasource_id: int, database: str, table: str, request: Request, limit: int = 20, db: Session = Depends(get_db)):
    opened, denied = _open_or_fail(request, db, datasource_id)
    if denied:
        return denied
    _, eng, _ = opened
    try:
        with eng.connect() as conn:
            data = preview(conn, database, table, limit)
        eng.dispose()
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


@router.post("/datasource/execute")
def ds_execute(body: dict, request: Request, db: Session = Depends(get_db)):
    raw_id = _pick(body, "datasourceId", "datasource_id")
    if raw_id is None:
        return fail("缺少数据源")
    opened, denied = _open_or_fail(request, db, int(raw_id))
    if denied:
        return denied
    _, eng, _ = opened
    try:
        with eng.connect() as conn:
            data = execute_select(conn, _pick(body, "script", "sql", default=""), _pick(body, "limit", default=100))
        eng.dispose()
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


# ---------- jobs ----------

def _save_job(body: dict, row: Job | None, db: Session) -> Job:
    parameter = _pick(body, "parameter", default={})
    if isinstance(parameter, str):
        parameter = parse_json(parameter, {})
    metric_parameter = parameter.get("metricParameter") or {}
    schema_name = _pick(body, "schemaName", "schema_name", default=metric_parameter.get("database"))
    table_name = _pick(body, "tableName", "table_name", default=metric_parameter.get("table"))
    column_name = _pick(body, "columnName", "column_name", default=metric_parameter.get("column"))
    metric_type = _pick(body, "metricType", "metric_type", default=parameter.get("metricType"))
    if row is None:
        row = Job(
            name=_pick(body, "name"),
            datasource_id=_pick(body, "datasourceId", "datasource_id"),
            create_by=settings.default_user_id,
            update_by=settings.default_user_id,
        )
        db.add(row)
    row.name = _pick(body, "name", default=row.name)
    row.type = _pick(body, "type", default=row.type or 0)
    row.datasource_id = _pick(body, "datasourceId", "datasource_id", default=row.datasource_id)
    row.datasource_id_2 = _pick(body, "datasourceId2", "datasource_id_2", default=row.datasource_id_2)
    row.schema_name = schema_name
    row.table_name = table_name
    row.column_name = column_name
    row.metric_type = metric_type
    row.engine_type = _pick(body, "engineType", "engine_type", default=row.engine_type or "local")
    row.execute_platform_type = _pick(body, "executePlatformType", default=row.execute_platform_type or "local")
    row.engine_parameter = json_text(_pick(body, "engineParameter", default=row.engine_parameter))
    row.parameter = json.dumps(parameter, ensure_ascii=False)
    row.retry_times = _pick(body, "retryTimes", "retry_times", default=row.retry_times or 0)
    row.retry_interval = _pick(body, "retryInterval", "retry_interval", default=row.retry_interval or 1)
    row.timeout = _pick(body, "timeout", default=row.timeout or 600)
    row.timeout_strategy = _pick(body, "timeoutStrategy", "timeout_strategy", default=row.timeout_strategy or 0)
    row.pre_sql = _pick(body, "preSql", "pre_sql", default=row.pre_sql)
    row.post_sql = _pick(body, "postSql", "post_sql", default=row.post_sql)
    row.error_data_storage_id = _pick(body, "errorDataStorageId", "error_data_storage_id", default=row.error_data_storage_id)
    flag = _pick(body, "isErrorDataOutputToDatasource", "is_error_data_output_to_datasource", default=row.is_error_data_output_to_datasource)
    row.is_error_data_output_to_datasource = bool(flag) if flag is not None else False
    row.error_data_output_to_datasource_database = _pick(
        body, "errorDataOutputToDatasourceDatabase", default=row.error_data_output_to_datasource_database
    )
    row.update_by = settings.default_user_id
    return row


@router.post("/job")
def job_create(body: dict, db: Session = Depends(get_db)):
    if not _pick(body, "name") or not _pick(body, "datasourceId", "datasource_id"):
        return fail("作业名称和数据源不能为空")
    row = _save_job(body, None, db)
    db.flush()
    bind_job(db, row)
    cron = _pick(body, "cronExpression", "cron")
    if cron:
        db.add(
            JobSchedule(
                type="cycle",
                job_id=row.id,
                cron_expression=cron,
                status=1 if _pick(body, "scheduleStatus", default=True) else 0,
                create_by=settings.default_user_id,
                update_by=settings.default_user_id,
            )
        )
    db.commit()
    db.refresh(row)
    return ok(dump_row(row))


@router.put("/job")
def job_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(Job, _pick(body, "id"))
    if row is None:
        return fail("作业不存在", 404)
    _save_job(body, row, db)
    bind_job(db, row)
    db.commit()
    return ok(dump_row(row))


@router.delete("/job/{job_id}")
def job_delete(job_id: int, db: Session = Depends(get_db)):
    row = db.get(Job, job_id)
    if row is None:
        return fail("作业不存在", 404)
    db.query(JobSchedule).filter(JobSchedule.job_id == job_id).delete()
    db.query(SlaJob).filter(SlaJob.job_id == job_id).delete()
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/job/page")
def job_page(
    searchVal: str | None = None,
    schemaSearch: str | None = None,
    tableSearch: str | None = None,
    columnSearch: str | None = None,
    datasourceId: int | None = None,
    pageNumber: int = 1,
    pageSize: int = 10,
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if datasourceId:
        query = query.filter(Job.datasource_id == datasourceId)
    if searchVal:
        query = query.filter(Job.name.like(f"%{searchVal}%"))
    if schemaSearch:
        query = query.filter(Job.schema_name.like(f"%{schemaSearch}%"))
    if tableSearch:
        query = query.filter(Job.table_name.like(f"%{tableSearch}%"))
    if columnSearch:
        query = query.filter(Job.column_name.like(f"%{columnSearch}%"))
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(Job.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.get("/job/list/{datasource_id}")
def job_list(datasource_id: int, db: Session = Depends(get_db)):
    rows = db.query(Job).filter(Job.datasource_id == datasource_id).all()
    return ok([dump_row(row) for row in rows])


@router.get("/job/{job_id}")
def job_get(job_id: int, db: Session = Depends(get_db)):
    row = db.get(Job, job_id)
    if row is None:
        return fail("作业不存在", 404)
    return ok(dump_row(row))


@router.get("/job/config/{job_id}")
@router.get("/job/execute/config/{job_id}")
def job_config(job_id: int, db: Session = Depends(get_db)):
    row = db.get(Job, job_id)
    if row is None:
        return fail("作业不存在", 404)
    return ok(dump_row(row))


@router.post("/job/execute/{job_id}")
def job_execute(job_id: int, db: Session = Depends(get_db)):
    try:
        execution_id = enqueue_job(db, job_id)
    except ValueError as exc:
        return fail(str(exc))
    return ok(execution_id)


@router.post("/job/schedule/createOrUpdate")
def schedule_save(body: dict, db: Session = Depends(get_db)):
    job_id = _pick(body, "jobId", "job_id")
    row = db.query(JobSchedule).filter(JobSchedule.job_id == job_id).one_or_none()
    if row is None:
        row = JobSchedule(job_id=job_id, type=_pick(body, "type", default="cycle"), create_by=settings.default_user_id, update_by=settings.default_user_id)
        db.add(row)
    row.type = _pick(body, "type", default=row.type or "cycle")
    row.param = json_text(_pick(body, "param", default=row.param))
    row.cron_expression = _pick(body, "cronExpression", "cron_expression", default=row.cron_expression)
    status = _pick(body, "status", default=1)
    row.status = 1 if status in (1, True, "1", "true", "online") else 0
    if row.cron_expression:
        try:
            normalize_cron(row.cron_expression)
        except ValueError as exc:
            return fail(str(exc))
    row.update_by = settings.default_user_id
    db.commit()
    return ok(dump_row(row))


@router.get("/job/schedule/{job_id}")
def schedule_get(job_id: int, db: Session = Depends(get_db)):
    row = db.query(JobSchedule).filter(JobSchedule.job_id == job_id).one_or_none()
    return ok(dump_row(row) if row else None)


@router.post("/job/schedule/cron")
def schedule_cron_check(body: dict):
    expr = _pick(body, "cronExpression", "crontab", default="")
    try:
        normalize_cron(expr)
        due = cron_due(expr, datetime.now())
    except ValueError as exc:
        return fail(str(exc))
    return ok({"valid": True, "dueNow": due})


@router.post("/job/schedule/cron/future/list")
def schedule_future(body: dict):
    expr = _pick(body, "cronExpression", "crontab", default="")
    try:
        times = upcoming(expr, as_int(_pick(body, "count", default=5), 5))
    except ValueError as exc:
        return fail(str(exc))
    return ok(times)


# ---------- execution ----------

@router.post("/job/execution/page")
def execution_page(body: dict | None = None, db: Session = Depends(get_db)):
    body = body or {}
    query = db.query(JobExecution)
    if _pick(body, "jobId", "job_id"):
        query = query.filter(JobExecution.job_id == _pick(body, "jobId", "job_id"))
    if _pick(body, "datasourceId", "datasource_id"):
        query = query.filter(JobExecution.datasource_id == _pick(body, "datasourceId", "datasource_id"))
    if _pick(body, "status") is not None and _pick(body, "status") != "":
        query = query.filter(JobExecution.status == _pick(body, "status"))
    page, size = _page_args(body)
    total, rows = _slice(query.order_by(JobExecution.id.desc()), page, size)
    records = [dump_row(row, extra={"statusLabel": EXEC_STATUS_LABEL.get(row.status, str(row.status))}) for row in rows]
    return ok(page_payload(records, total, page, size))


@router.get("/job/execution/list/{job_id}")
def execution_list(job_id: int, db: Session = Depends(get_db)):
    rows = db.query(JobExecution).filter(JobExecution.job_id == job_id).order_by(JobExecution.id.desc()).all()
    return ok([dump_row(row, extra={"statusLabel": EXEC_STATUS_LABEL.get(row.status, "")}) for row in rows])


@router.get("/job/execution/status/{execution_id}")
def execution_status(execution_id: int, db: Session = Depends(get_db)):
    row = db.get(JobExecution, execution_id)
    if row is None:
        return fail("执行实例不存在", 404)
    return ok({"id": row.id, "status": row.status, "statusLabel": EXEC_STATUS_LABEL.get(row.status, "")})


def _result_dump(db: Session, row: JobExecutionResult) -> dict:
    payload = db.query(MetricPayload).filter(MetricPayload.job_execution_result_id == row.id).one_or_none()
    extra = {"payload": parse_json(payload.payload, None) if payload else None}
    return dump_row(row, extra=extra)


@router.get("/job/execution/result/{execution_id}")
def execution_result(execution_id: int, db: Session = Depends(get_db)):
    row = db.query(JobExecutionResult).filter(JobExecutionResult.job_execution_id == execution_id).order_by(JobExecutionResult.id.asc()).first()
    return ok(_result_dump(db, row) if row else None)


@router.get("/job/execution/list/result/{execution_id}")
def execution_results(execution_id: int, db: Session = Depends(get_db)):
    rows = db.query(JobExecutionResult).filter(JobExecutionResult.job_execution_id == execution_id).all()
    return ok([_result_dump(db, row) for row in rows])


@router.get("/job/execution/log/{execution_id}")
def execution_log(execution_id: int, db: Session = Depends(get_db)):
    row = db.get(JobExecution, execution_id)
    if row is None:
        return fail("执行实例不存在", 404)
    text = ""
    if row.log_path:
        try:
            with open(row.log_path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            text = ""
    return ok({"log": text, "path": row.log_path, "status": row.status})


@router.get("/job/execution/errorDataPage")
def error_page(executionId: int, pageNumber: int = 1, pageSize: int = 20, db: Session = Depends(get_db)):
    query = db.query(ErrorDataRow).filter(ErrorDataRow.job_execution_id == executionId).order_by(ErrorDataRow.id.asc())
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query, page, size)
    records = []
    for row in rows:
        item = dump_row(row)
        item["rowData"] = parse_json(row.row_data, row.row_data)
        records.append(item)
    return ok(page_payload(records, total, page, size))


@router.delete("/job/execution/kill/{execution_id}")
def execution_kill(execution_id: int, db: Session = Depends(get_db)):
    row = db.get(JobExecution, execution_id)
    if row is None:
        return fail("执行实例不存在", 404)
    enqueue_stop(db, execution_id)
    return ok(True)


@router.post("/job/execution/agg-pie")
def agg_pie(body: dict, db: Session = Depends(get_db)):
    query = db.query(JobExecutionResult.state, func.count(JobExecutionResult.id)).join(
        JobExecution, JobExecution.id == JobExecutionResult.job_execution_id
    )
    if _pick(body, "datasourceId"):
        query = query.filter(JobExecution.datasource_id == _pick(body, "datasourceId"))
    rows = query.group_by(JobExecutionResult.state).all()
    return ok([{"state": state, "name": "通过" if state == 1 else "未通过", "value": count} for state, count in rows])


@router.post("/job/execution/trend-bar")
def trend_bar(body: dict, db: Session = Depends(get_db)):
    datasource_id = _pick(body, "datasourceId")
    days = as_int(_pick(body, "days", default=7), 7)
    start = datetime.now().date() - timedelta(days=days - 1)
    rows = (
        db.query(func.date(JobExecution.schedule_time), JobExecutionResult.state, func.count(JobExecutionResult.id))
        .join(JobExecutionResult, JobExecutionResult.job_execution_id == JobExecution.id)
        .filter(JobExecution.schedule_time >= datetime.combine(start, datetime.min.time()))
    )
    if datasource_id:
        rows = rows.filter(JobExecution.datasource_id == datasource_id)
    bucket: dict[str, dict] = {}
    for day, state, count in rows.group_by(func.date(JobExecution.schedule_time), JobExecutionResult.state).all():
        key = str(day)
        bucket.setdefault(key, {"date": key, "success": 0, "fail": 0})
        if state == 1:
            bucket[key]["success"] = count
        else:
            bucket[key]["fail"] = count
    return ok([bucket[key] for key in sorted(bucket)])


def _submit_inline(body: dict, db: Session, job_type: int):
    body = dict(body)
    body["type"] = job_type
    row = _save_job(body, None, db)
    db.flush()
    bind_job(db, row)
    execution_id = enqueue_job(db, row.id)
    return ok({"jobId": row.id, "executionId": execution_id})


@router.post("/job/execution/submit/data-quality")
def submit_quality(body: dict, db: Session = Depends(get_db)):
    return _submit_inline(body, db, 0)


@router.post("/job/execution/submit/data-reconciliation")
def submit_reconciliation(body: dict, db: Session = Depends(get_db)):
    return _submit_inline(body, db, 2)


# ---------- quality report ----------

@router.post("/job/quality-report/page")
def report_page(body: dict, db: Session = Depends(get_db)):
    query = db.query(JobQualityReport)
    if _pick(body, "datasourceId"):
        query = query.filter(JobQualityReport.datasource_id == _pick(body, "datasourceId"))
    if _pick(body, "entityLevel"):
        query = query.filter(JobQualityReport.entity_level == _pick(body, "entityLevel"))
    if _pick(body, "databaseName"):
        query = query.filter(JobQualityReport.database_name == _pick(body, "databaseName"))
    if _pick(body, "tableName"):
        query = query.filter(JobQualityReport.table_name == _pick(body, "tableName"))
    page, size = _page_args(body)
    total, rows = _slice(query.order_by(JobQualityReport.report_date.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.post("/job/quality-report/score")
def report_score(body: dict, db: Session = Depends(get_db)):
    level = _pick(body, "entityLevel", default="DATASOURCE")
    query = db.query(JobQualityReport).filter(JobQualityReport.datasource_id == _pick(body, "datasourceId"), JobQualityReport.entity_level == level)
    if _pick(body, "reportDate"):
        query = query.filter(JobQualityReport.report_date == _pick(body, "reportDate"))
    if _pick(body, "databaseName"):
        query = query.filter(JobQualityReport.database_name == _pick(body, "databaseName"))
    if _pick(body, "tableName"):
        query = query.filter(JobQualityReport.table_name == _pick(body, "tableName"))
    if _pick(body, "columnName"):
        query = query.filter(JobQualityReport.column_name == _pick(body, "columnName"))
    row = query.order_by(JobQualityReport.report_date.desc()).first()
    return ok(dump_row(row) if row else {"score": None})


@router.post("/job/quality-report/score-trend")
def report_trend(body: dict, db: Session = Depends(get_db)):
    query = db.query(JobQualityReport).filter(
        JobQualityReport.datasource_id == _pick(body, "datasourceId"),
        JobQualityReport.entity_level == _pick(body, "entityLevel", default="DATASOURCE"),
    )
    if _pick(body, "databaseName"):
        query = query.filter(JobQualityReport.database_name == _pick(body, "databaseName"))
    if _pick(body, "tableName"):
        query = query.filter(JobQualityReport.table_name == _pick(body, "tableName"))
    rows = query.order_by(JobQualityReport.report_date.asc()).all()
    return ok([{"date": row.report_date.isoformat() if row.report_date else None, "score": float(row.score or 0)} for row in rows])


@router.get("/job/quality-report/listColumnExecution")
def list_column_execution(datasourceId: int, databaseName: str, tableName: str, columnName: str, db: Session = Depends(get_db)):
    rows = (
        db.query(JobExecutionResult)
        .filter(
            JobExecutionResult.database_name == databaseName,
            JobExecutionResult.table_name == tableName,
            JobExecutionResult.column_name == columnName,
        )
        .order_by(JobExecutionResult.id.desc())
        .limit(50)
        .all()
    )
    return ok([dump_row(row) for row in rows])


# ---------- catalog ----------

@router.post("/catalog/refresh")
def catalog_refresh(body: dict, db: Session = Depends(get_db)):
    datasource_id = _pick(body, "datasourceId", "datasource_id")
    task_id = enqueue_common(db, "CATALOG_METADATA", int(datasource_id), _pick(body, "database"), None, json.dumps(body))
    return ok({"taskId": task_id})


@router.post("/catalog/refresh/sync")
def catalog_refresh_sync(body: dict, db: Session = Depends(get_db)):
    try:
        data = refresh_datasource(db, int(_pick(body, "datasourceId")), _pick(body, "database"))
    except Exception as exc:
        return fail(str(exc))
    return ok(data)


@router.get("/catalog/list/database/{upstream_uuid}")
def catalog_databases(upstream_uuid: str, db: Session = Depends(get_db)):
    # upstreamUuid here is the datasource id encoded as the entity of databases: we also accept datasource id path via query.
    rows = children(db, upstream_uuid, "database")
    if not rows:
        ds_rows = db.query(CatalogEntityInstance).filter(CatalogEntityInstance.datasource_id == _maybe_int(upstream_uuid), CatalogEntityInstance.type == "database", CatalogEntityInstance.status == "active").all()
        rows = ds_rows
    return ok([dump_row(row) for row in rows])


def _maybe_int(value: str):
    try:
        return int(value)
    except ValueError:
        return -1


@router.get("/catalog/databases/{datasource_id}")
def catalog_db_by_ds(datasource_id: int, db: Session = Depends(get_db)):
    rows = db.query(CatalogEntityInstance).filter(CatalogEntityInstance.datasource_id == datasource_id, CatalogEntityInstance.type == "database", CatalogEntityInstance.status == "active").all()
    return ok([dump_row(row) for row in rows])


@router.get("/catalog/list/table/{upstream_uuid}")
def catalog_tables(upstream_uuid: str, db: Session = Depends(get_db)):
    return ok([dump_row(row) for row in children(db, upstream_uuid, "table")])


@router.get("/catalog/list/column/{upstream_uuid}")
def catalog_columns(upstream_uuid: str, db: Session = Depends(get_db)):
    return ok([dump_row(row) for row in children(db, upstream_uuid, "column")])


@router.get("/catalog/detail/{entity_uuid}")
def catalog_detail(entity_uuid: str, db: Session = Depends(get_db)):
    row = db.query(CatalogEntityInstance).filter(CatalogEntityInstance.uuid == entity_uuid).one_or_none()
    if row is None:
        return fail("实体不存在", 404)
    data = dump_row(row)
    data["tags"] = entity_tags(db, entity_uuid)
    return ok(data)


@router.get("/catalog/list/schema-change/{uuid}")
def schema_by_parent(uuid: str, db: Session = Depends(get_db)):
    rows = db.query(CatalogSchemaChange).filter((CatalogSchemaChange.parent_uuid == uuid) | (CatalogSchemaChange.entity_uuid == uuid)).order_by(CatalogSchemaChange.id.desc()).all()
    return ok([dump_row(row) for row in rows])


@router.get("/catalog/page/schema-change")
def schema_page(datasourceId: int | None = None, pageNumber: int = 1, pageSize: int = 10, db: Session = Depends(get_db)):
    query = db.query(CatalogSchemaChange)
    if datasourceId:
        entities = db.query(CatalogEntityInstance.uuid).filter(CatalogEntityInstance.datasource_id == datasourceId).all()
        uuids = [item[0] for item in entities]
        query = query.filter(CatalogSchemaChange.entity_uuid.in_(uuids or ["-"]))
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(CatalogSchemaChange.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.get("/catalog/profile/table/{entity_uuid}")
def profile_table_api(entity_uuid: str, db: Session = Depends(get_db)):
    rows = db.query(CatalogEntityProfile).filter(CatalogEntityProfile.entity_uuid == entity_uuid).order_by(CatalogEntityProfile.data_date.asc()).all()
    return ok([dump_row(row) for row in rows])


@router.get("/catalog/profile/column/{entity_uuid}")
def profile_column_api(entity_uuid: str, db: Session = Depends(get_db)):
    rows = db.query(CatalogEntityProfile).filter(CatalogEntityProfile.entity_uuid == entity_uuid).all()
    payload = []
    for row in rows:
        item = dump_row(row)
        if row.actual_value_type == "list":
            item["actualValue"] = parse_json(row.actual_value, row.actual_value)
        payload.append(item)
    return ok(payload)


@router.get("/catalog/profile/table/records")
def profile_records(uuid: str, metric: str = "table_row_count", db: Session = Depends(get_db)):
    rows = (
        db.query(CatalogEntityProfile)
        .filter(CatalogEntityProfile.entity_uuid == uuid, CatalogEntityProfile.metric_name == metric)
        .order_by(CatalogEntityProfile.data_date.asc())
        .all()
    )
    return ok([{"date": row.data_date, "value": row.actual_value} for row in rows])


@router.post("/catalog/profile/execute")
def profile_execute(body: dict, db: Session = Depends(get_db)):
    task_id = enqueue_common(
        db,
        "DATA_PROFILE",
        int(_pick(body, "datasourceId")),
        _pick(body, "database"),
        _pick(body, "table"),
        json.dumps({"database": _pick(body, "database"), "table": _pick(body, "table"), "columns": _pick(body, "columns")}),
    )
    return ok({"taskId": task_id})


@router.get("/catalog/lineage/getByUUID/{entity_uuid}")
def lineage_get(entity_uuid: str, db: Session = Depends(get_db)):
    try:
        data = lineage(db, entity_uuid)
    except ValueError as exc:
        return fail(str(exc), 404)
    return ok(data)


@router.post("/catalog/lineage/add")
def lineage_add(body: dict, db: Session = Depends(get_db)):
    add_lineage(db, _pick(body, "fromUUID", "from"), _pick(body, "toUUID", "to"), _pick(body, "sourceType", default="manual"))
    db.commit()
    return ok(True)


@router.delete("/catalog/lineage/{from_uuid}/{to_uuid}")
def lineage_delete(from_uuid: str, to_uuid: str, db: Session = Depends(get_db)):
    db.query(CatalogEntityRel).filter(
        CatalogEntityRel.entity1_uuid == from_uuid,
        CatalogEntityRel.entity2_uuid == to_uuid,
    ).delete()
    db.commit()
    return ok(True)


@router.post("/catalog/lineage/addByParseSql")
def lineage_parse(body: dict, db: Session = Depends(get_db)):
    created = parse_lineage_sql(db, int(_pick(body, "datasourceId")), _pick(body, "sql", default=""))
    db.commit()
    return ok({"edges": created})


@router.post("/catalog/tag/category")
def tag_category_create(body: dict, db: Session = Depends(get_db)):
    row = CatalogTagCategory(
        uuid=uuid.uuid4().hex,
        name=_pick(body, "name"),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.get("/catalog/tag/category/list/{workspace_id}")
def tag_category_list(workspace_id: int, db: Session = Depends(get_db)):
    rows = db.query(CatalogTagCategory).filter(CatalogTagCategory.workspace_id == workspace_id).all()
    return ok([dump_row(row) for row in rows])


@router.delete("/catalog/tag/category/{category_uuid}")
def tag_category_delete(category_uuid: str, db: Session = Depends(get_db)):
    db.query(CatalogTag).filter(CatalogTag.category_uuid == category_uuid).delete()
    db.query(CatalogTagCategory).filter(CatalogTagCategory.uuid == category_uuid).delete()
    db.commit()
    return ok(True)


@router.post("/catalog/tag")
def tag_create(body: dict, db: Session = Depends(get_db)):
    row = CatalogTag(
        uuid=uuid.uuid4().hex,
        category_uuid=_pick(body, "categoryUuid", "category_uuid"),
        name=_pick(body, "name"),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.get("/catalog/tag/list-in-category/{category_uuid}")
def tags_in_category(category_uuid: str, db: Session = Depends(get_db)):
    rows = db.query(CatalogTag).filter(CatalogTag.category_uuid == category_uuid).all()
    return ok([dump_row(row) for row in rows])


@router.get("/catalog/tag/list-in-workspace/{workspace_id}")
def tags_in_workspace(workspace_id: int, db: Session = Depends(get_db)):
    cats = db.query(CatalogTagCategory).filter(CatalogTagCategory.workspace_id == workspace_id).all()
    ids = [c.uuid for c in cats]
    rows = db.query(CatalogTag).filter(CatalogTag.category_uuid.in_(ids or ["-"])).all()
    return ok([dump_row(row) for row in rows])


@router.get("/catalog/tag/list-in-entity/{entity_uuid}")
def tags_in_entity(entity_uuid: str, db: Session = Depends(get_db)):
    return ok(entity_tags(db, entity_uuid))


@router.delete("/catalog/tag/{tag_uuid}")
def tag_delete(tag_uuid: str, db: Session = Depends(get_db)):
    db.query(CatalogEntityTagRel).filter(CatalogEntityTagRel.tag_uuid == tag_uuid).delete()
    db.query(CatalogTag).filter(CatalogTag.uuid == tag_uuid).delete()
    db.commit()
    return ok(True)


@router.post("/catalog/tag/entity-tag")
def entity_tag_add(body: dict, db: Session = Depends(get_db)):
    entity_uuid = _pick(body, "entityUuid", "entityUUID")
    tag_uuid = _pick(body, "tagUuid", "tagUUID")
    exists = db.query(CatalogEntityTagRel).filter(CatalogEntityTagRel.entity_uuid == entity_uuid, CatalogEntityTagRel.tag_uuid == tag_uuid).one_or_none()
    if exists is None:
        db.add(CatalogEntityTagRel(entity_uuid=entity_uuid, tag_uuid=tag_uuid, create_by=settings.default_user_id, update_by=settings.default_user_id))
        db.commit()
    return ok(True)


@router.delete("/catalog/tag/entity-tag")
def entity_tag_delete(entityUuid: str, tagUuid: str, db: Session = Depends(get_db)):
    db.query(CatalogEntityTagRel).filter(CatalogEntityTagRel.entity_uuid == entityUuid, CatalogEntityTagRel.tag_uuid == tagUuid).delete()
    db.commit()
    return ok(True)


@router.get("/catalog/page/entity/issue")
def entity_issues(datasourceId: int | None = None, pageNumber: int = 1, pageSize: int = 10, db: Session = Depends(get_db)):
    query = db.query(Issue)
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(Issue.id.desc()), page, size)
    payload = []
    for row in rows:
        rel = db.query(JobIssueRel).filter(JobIssueRel.issue_id == row.id).first()
        payload.append(dump_row(row, extra={"jobId": rel.job_id if rel else None}))
    return ok(page_payload(payload, total, page, size))


@router.post("/catalog/issue/update-status")
def issue_status(body: dict, db: Session = Depends(get_db)):
    row = db.get(Issue, _pick(body, "id", "issueId"))
    if row is None:
        return fail("Issue 不存在", 404)
    row.status = _pick(body, "status", default=row.status)
    db.commit()
    return ok(dump_row(row))


# ---------- SLA ----------

@router.get("/sla/plugin/support")
def sla_plugins():
    return ok([_item("飞书", "feishu")])


@router.get("/sla/sender/config/{sender_type}")
def sla_sender_config(sender_type: str):
    if sender_type.lower() not in ("feishu", "lark"):
        return fail("仅实现飞书 webhook")
    return ok([{"key": "webhook", "label": "飞书机器人 Webhook", "required": True}])


@router.get("/sla/notification/config/{sender_type}")
def sla_notification_config(sender_type: str):
    return ok([{"key": "atAll", "label": "是否@所有人", "required": False}])


@router.post("/sla/sender")
def sla_sender_create(body: dict, db: Session = Depends(get_db)):
    if str(_pick(body, "type", default="feishu")).lower() not in ("feishu", "lark"):
        return fail("仅支持飞书")
    row = SlaSender(
        type="feishu",
        name=_pick(body, "name"),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        config=json_text(_pick(body, "config", default={})),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.put("/sla/sender")
def sla_sender_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(SlaSender, _pick(body, "id"))
    if row is None:
        return fail("发送器不存在", 404)
    row.name = _pick(body, "name", default=row.name)
    if _pick(body, "config") is not None:
        row.config = json_text(_pick(body, "config"))
    db.commit()
    return ok(dump_row(row))


@router.delete("/sla/sender/{sender_id}")
def sla_sender_delete(sender_id: int, db: Session = Depends(get_db)):
    row = db.get(SlaSender, sender_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/sla/sender/page")
def sla_sender_page(pageNumber: int = 1, pageSize: int = 10, workspaceId: int | None = None, db: Session = Depends(get_db)):
    query = db.query(SlaSender)
    if workspaceId:
        query = query.filter(SlaSender.workspace_id == workspaceId)
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(SlaSender.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.get("/sla/sender/list")
def sla_sender_list(workspaceId: int = 1, db: Session = Depends(get_db)):
    rows = db.query(SlaSender).filter(SlaSender.workspace_id == workspaceId).all()
    return ok([dump_row(row) for row in rows])


@router.post("/sla/sender/test")
def sla_sender_test(body: dict, db: Session = Depends(get_db)):
    from app.alerts import send_feishu, write_log

    webhook = None
    sender_id = _pick(body, "id", "senderId")
    sender = db.get(SlaSender, sender_id) if sender_id else None
    if sender:
        webhook = parse_json(sender.config, {}).get("webhook")
    webhook = _pick(body, "webhook", default=webhook)
    success, response = send_feishu(webhook, "DataVines 测试告警", "这是一条飞书 webhook 测试消息。")
    write_log(db, sla_id=None, job_id=None, execution_id=None, sender_id=sender.id if sender else None, webhook=webhook, title="DataVines 测试告警", content="测试消息", success=success, response=response)
    db.commit()
    return ok({"success": success, "response": response})


@router.post("/sla")
def sla_create(body: dict, db: Session = Depends(get_db)):
    row = Sla(
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        name=_pick(body, "name"),
        description=_pick(body, "description", default="") or "",
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.put("/sla")
def sla_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(Sla, _pick(body, "id"))
    if row is None:
        return fail("SLA 不存在", 404)
    row.name = _pick(body, "name", default=row.name)
    row.description = _pick(body, "description", default=row.description) or ""
    db.commit()
    return ok(dump_row(row))


@router.get("/sla/page")
def sla_page(pageNumber: int = 1, pageSize: int = 10, workspaceId: int | None = None, searchVal: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Sla)
    if workspaceId:
        query = query.filter(Sla.workspace_id == workspaceId)
    if searchVal:
        query = query.filter(Sla.name.like(f"%{searchVal}%"))
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(Sla.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.get("/sla/{sla_id}")
def sla_get(sla_id: int, db: Session = Depends(get_db)):
    if str(sla_id) in ("page",):
        return fail("not found", 404)
    row = db.get(Sla, sla_id)
    if row is None:
        return fail("SLA 不存在", 404)
    jobs = db.query(SlaJob).filter(SlaJob.sla_id == sla_id).all()
    notes = db.query(SlaNotification).filter(SlaNotification.sla_id == sla_id).all()
    return ok({**dump_row(row), "jobs": [dump_row(j) for j in jobs], "notifications": [dump_row(n) for n in notes]})


@router.delete("/sla/{sla_id}")
def sla_delete(sla_id: int, db: Session = Depends(get_db)):
    db.query(SlaJob).filter(SlaJob.sla_id == sla_id).delete()
    db.query(SlaNotification).filter(SlaNotification.sla_id == sla_id).delete()
    row = db.get(Sla, sla_id)
    if row:
        db.delete(row)
    db.commit()
    return ok(True)


@router.post("/sla/job/createOrUpdate")
def sla_job_save(body: dict, db: Session = Depends(get_db)):
    sla_id = _pick(body, "slaId", "sla_id")
    job_id = _pick(body, "jobId", "job_id")
    row = db.query(SlaJob).filter(SlaJob.sla_id == sla_id, SlaJob.job_id == job_id).one_or_none()
    if row is None:
        row = SlaJob(
            workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
            sla_id=sla_id,
            job_id=job_id,
            create_by=settings.default_user_id,
            update_by=settings.default_user_id,
        )
        db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.delete("/sla/job/{sla_job_id}")
def sla_job_delete(sla_job_id: int, db: Session = Depends(get_db)):
    row = db.get(SlaJob, sla_job_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/sla/job/list")
def sla_job_list(slaId: int, db: Session = Depends(get_db)):
    rows = db.query(SlaJob).filter(SlaJob.sla_id == slaId).all()
    return ok([dump_row(row) for row in rows])


@router.get("/sla/job/{job_id}")
def sla_by_job(job_id: int, db: Session = Depends(get_db)):
    rows = db.query(SlaJob).filter(SlaJob.job_id == job_id).all()
    return ok([dump_row(row) for row in rows])


@router.post("/sla/notification")
def sla_note_create(body: dict, db: Session = Depends(get_db)):
    row = SlaNotification(
        type=_pick(body, "type", default="feishu"),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        sla_id=_pick(body, "slaId"),
        sender_id=_pick(body, "senderId"),
        config=json_text(_pick(body, "config", default={})),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.put("/sla/notification")
def sla_note_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(SlaNotification, _pick(body, "id"))
    if row is None:
        return fail("通知不存在", 404)
    row.sender_id = _pick(body, "senderId", default=row.sender_id)
    row.config = json_text(_pick(body, "config", default=row.config))
    db.commit()
    return ok(dump_row(row))


@router.delete("/sla/notification/{note_id}")
def sla_note_delete(note_id: int, db: Session = Depends(get_db)):
    row = db.get(SlaNotification, note_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/sla/notification/page")
def sla_note_page(slaId: int | None = None, pageNumber: int = 1, pageSize: int = 10, db: Session = Depends(get_db)):
    query = db.query(SlaNotification)
    if slaId:
        query = query.filter(SlaNotification.sla_id == slaId)
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(SlaNotification.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.get("/sla/test/{sla_id}")
def sla_test(sla_id: int, db: Session = Depends(get_db)):
    from app.alerts import send_feishu, write_log

    notes = db.query(SlaNotification).filter(SlaNotification.sla_id == sla_id).all()
    results = []
    for note in notes:
        sender = db.get(SlaSender, note.sender_id)
        webhook = parse_json(sender.config, {}).get("webhook") if sender else None
        success, response = send_feishu(webhook, f"SLA {sla_id} 测试", "DataVines SLA 测试通知")
        write_log(db, sla_id=sla_id, job_id=None, execution_id=None, sender_id=note.sender_id, webhook=webhook, title="SLA 测试", content="测试", success=success, response=response)
        results.append({"success": success, "response": response, "senderId": note.sender_id})
    db.commit()
    return ok(results)


@router.post("/sla/mock/receive")
def sla_mock_receive(body: dict, db: Session = Depends(get_db)):
    from app.alerts import record_mock, write_log

    title = "mock"
    content = json.dumps(body, ensure_ascii=False)[:2000]
    record_mock(title, content, "mock-receive", body)
    write_log(db, sla_id=None, job_id=None, execution_id=None, sender_id=None, webhook="mock-receive", title=title, content=content, success=True, response="received")
    db.commit()
    return ok(True)


@router.get("/sla/mock/messages")
def sla_mock_messages(db: Session = Depends(get_db)):
    from app.alerts import mock_messages

    rows = db.query(AlertSendLog).order_by(AlertSendLog.id.desc()).limit(50).all()
    return ok({"memory": mock_messages(), "logs": [dump_row(row) for row in rows]})


# ---------- system ----------

@router.get("/config/page")
def config_page(pageNumber: int = 1, pageSize: int = 20, workspaceId: int | None = None, searchVal: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Config)
    if workspaceId is not None:
        query = query.filter(Config.workspace_id == workspaceId)
    if searchVal:
        query = query.filter(Config.var_key.like(f"%{searchVal}%"))
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(Config.id.asc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.post("/config")
def config_create(body: dict, db: Session = Depends(get_db)):
    row = Config(
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        var_key=_pick(body, "varKey", "key"),
        var_value=str(_pick(body, "varValue", "value", default="")),
        is_default=1 if _pick(body, "isDefault", default=0) else 0,
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.put("/config")
def config_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(Config, _pick(body, "id"))
    if row is None:
        return fail("配置不存在", 404)
    row.var_key = _pick(body, "varKey", default=row.var_key)
    row.var_value = str(_pick(body, "varValue", default=row.var_value))
    db.commit()
    return ok(dump_row(row))


@router.delete("/config/{config_id}")
def config_delete(config_id: int, db: Session = Depends(get_db)):
    row = db.get(Config, config_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/env/list/{workspace_id}")
def env_list(workspace_id: int, db: Session = Depends(get_db)):
    rows = db.query(Env).filter(Env.workspace_id == workspace_id).all()
    return ok([dump_row(row) for row in rows])


@router.post("/env")
def env_create(body: dict, db: Session = Depends(get_db)):
    row = Env(
        name=_pick(body, "name"),
        env=json_text(_pick(body, "env", default={})),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.put("/env")
def env_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(Env, _pick(body, "id"))
    if row is None:
        return fail("环境不存在", 404)
    row.name = _pick(body, "name", default=row.name)
    row.env = json_text(_pick(body, "env", default=row.env))
    db.commit()
    return ok(dump_row(row))


@router.delete("/env/{env_id}")
def env_delete(env_id: int, db: Session = Depends(get_db)):
    row = db.get(Env, env_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/errorDataStorage/type/list")
def eds_types():
    return ok([_item("MySQL", "mysql", supported=True), _item("本地文件", "local", supported=False)])


@router.get("/errorDataStorage/config/{dtype}")
def eds_config(dtype: str):
    return ok([
        {"key": "host", "label": "主机"},
        {"key": "port", "label": "端口"},
        {"key": "database", "label": "数据库"},
        {"key": "user", "label": "用户名"},
        {"key": "password", "label": "密码"},
    ])


@router.post("/errorDataStorage/test")
def eds_test(body: dict):
    try:
        test_connection(_pick(body, "type", default="mysql"), _pick(body, "param", default={}))
    except Exception as exc:
        return fail(str(exc))
    return ok(True)


@router.post("/errorDataStorage")
def eds_create(body: dict, db: Session = Depends(get_db)):
    row = ErrorDataStorage(
        name=_pick(body, "name"),
        type=_pick(body, "type", default="mysql"),
        param=json.dumps(validate_param(_pick(body, "param", default={}), _pick(body, "type", default="mysql"))),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row, mask_password=True))


@router.put("/errorDataStorage")
def eds_update(body: dict, db: Session = Depends(get_db)):
    row = db.get(ErrorDataStorage, _pick(body, "id"))
    if row is None:
        return fail("存储不存在", 404)
    row.name = _pick(body, "name", default=row.name)
    if _pick(body, "param") is not None:
        row.param = json.dumps(validate_param(_pick(body, "param"), row.type))
    db.commit()
    return ok(dump_row(row, mask_password=True))


@router.delete("/errorDataStorage/{storage_id}")
def eds_delete(storage_id: int, db: Session = Depends(get_db)):
    row = db.get(ErrorDataStorage, storage_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/errorDataStorage/list/{workspace_id}")
def eds_list(workspace_id: int, db: Session = Depends(get_db)):
    rows = db.query(ErrorDataStorage).filter(ErrorDataStorage.workspace_id == workspace_id).all()
    return ok([dump_row(row, mask_password=True) for row in rows])


@router.post("/errorDataStorage/page")
def eds_page(body: dict | None = None, db: Session = Depends(get_db)):
    body = body or {}
    query = db.query(ErrorDataStorage)
    page, size = _page_args(body)
    total, rows = _slice(query.order_by(ErrorDataStorage.id.desc()), page, size)
    return ok(page_payload([dump_row(row, mask_password=True) for row in rows], total, page, size))


@router.get("/common-task/page")
def common_page(pageNumber: int = 1, pageSize: int = 10, datasourceId: int | None = None, db: Session = Depends(get_db)):
    query = db.query(CommonTask)
    if datasourceId:
        query = query.filter(CommonTask.datasource_id == datasourceId)
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(query.order_by(CommonTask.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.post("/common-task/schedule")
def common_schedule_save(body: dict, db: Session = Depends(get_db)):
    row = CommonTaskSchedule(
        task_type=_pick(body, "taskType", default="CATALOG_METADATA"),
        type=_pick(body, "type", default="cycle"),
        param=json_text(_pick(body, "param", default={})),
        datasource_id=_pick(body, "datasourceId"),
        cron_expression=_pick(body, "cronExpression"),
        status=1 if _pick(body, "status", default=1) else 0,
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.get("/common-task/schedule/page")
def common_schedule_page(pageNumber: int = 1, pageSize: int = 10, db: Session = Depends(get_db)):
    page, size = _page_args({}, pageNumber, pageSize)
    total, rows = _slice(db.query(CommonTaskSchedule).order_by(CommonTaskSchedule.id.desc()), page, size)
    return ok(page_payload([dump_row(row) for row in rows], total, page, size))


@router.delete("/common-task/schedule/{schedule_id}")
def common_schedule_delete(schedule_id: int, db: Session = Depends(get_db)):
    row = db.get(CommonTaskSchedule, schedule_id)
    if row:
        db.delete(row)
        db.commit()
    return ok(True)


@router.get("/tenant/list/{workspace_id}")
def tenant_list(workspace_id: int, db: Session = Depends(get_db)):
    rows = db.query(Tenant).filter(Tenant.workspace_id == workspace_id).all()
    return ok([dump_row(row) for row in rows])


@router.post("/tenant")
def tenant_create(body: dict, db: Session = Depends(get_db)):
    row = Tenant(
        tenant=_pick(body, "tenant", "name"),
        workspace_id=_pick(body, "workspaceId", default=settings.default_workspace_id),
        create_by=settings.default_user_id,
        update_by=settings.default_user_id,
    )
    db.add(row)
    db.commit()
    return ok(dump_row(row))


@router.get("/token/page")
def token_page(request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    allowed = member_workspace_ids(db, user.id)
    rows = db.query(AccessToken).filter(AccessToken.workspace_id.in_(allowed or [-1])).all()
    return ok([dump_row(row) for row in rows] or [{"token": "JWT", "note": "登录令牌由 /login 签发，请求头 Authorization。指标目录无需登录。"}])


@router.post("/demo/bootstrap")
def demo_bootstrap(request: Request, db: Session = Depends(get_db)):
    user = _actor(request, db)
    if user is None:
        return fail("未登录", 401)
    allowed = member_workspace_ids(db, user.id)
    if not allowed:
        return fail("当前用户没有工作空间", 403)
    workspace_id = settings.default_workspace_id if settings.default_workspace_id in allowed else min(allowed)
    try:
        return ok(bootstrap_demo(workspace_id, user.id))
    except Exception as exc:
        return fail(str(exc))


@router.post("/demo/schema-change")
def demo_schema():
    try:
        return ok(apply_schema_change())
    except Exception as exc:
        return fail(str(exc))
