"""Command execution: metric SQL, expected value, formula, error data, report, SLA."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.constants import EXEC_FAILURE, EXEC_KILLED, EXEC_RUNNING, EXEC_SUBMITTED, EXEC_SUCCESS
from app.db import SessionLocal
from app.engine.local import Cancelled, run_plan, scalar_on_source, write_external_errors
from app.engine.spark import SparkEngine
from app.metrics.judge import compute_expected, judge
from app.metrics.registry import get_metric
from app.metrics.sqlgen import build_sql, table_ref
from app.models import (
    ActualValue,
    DataSource,
    ErrorDataRow,
    ErrorDataStorage,
    Issue,
    Job,
    JobExecution,
    JobExecutionResult,
    JobExecutionResultReportRel,
    JobIssueRel,
    JobQualityReport,
    MetricPayload,
    SlaJob,
    SlaNotification,
    SlaSender,
)
from app.util import parse_json

logger = logging.getLogger("datavines.runner")

_cancel: set[int] = set()
_holders: dict[int, dict] = {}
_lock = threading.Lock()


def request_cancel(execution_id: int) -> None:
    with _lock:
        _cancel.add(execution_id)
        holder = _holders.get(execution_id)
    if holder and holder.get("engine") is not None:
        try:
            holder["engine"].dispose()
        except Exception:
            logger.exception("dispose engine on cancel failed")


def _cancelled(execution_id: int) -> bool:
    return execution_id in _cancel


class JobLog:
    def __init__(self, execution_id: int):
        Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
        self.path = str(Path(settings.log_dir) / f"job-{execution_id}.log")
        self._fp = open(self.path, "a", encoding="utf-8")

    def line(self, message: str) -> None:
        text_line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n"
        self._fp.write(text_line)
        self._fp.flush()

    def close(self) -> None:
        self._fp.close()


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def _param(job: Job) -> dict:
    data = parse_json(job.parameter, {})
    if not isinstance(data, dict):
        data = {}
    metric_parameter = dict(data.get("metricParameter") or data.get("metric_parameter") or {})
    metric_parameter.setdefault("database", job.schema_name)
    metric_parameter.setdefault("table", job.table_name)
    metric_parameter.setdefault("column", job.column_name)
    expected_parameter = data.get("expectedParameter") or data.get("expected_parameter") or {}
    return {
        "metric": data.get("metricType") or data.get("metric_type") or job.metric_type,
        "metricParameter": metric_parameter,
        "expectedType": data.get("expectedType") or data.get("expected_type") or "fix_value",
        "expectedParameter": expected_parameter if isinstance(expected_parameter, dict) else {},
        "resultFormula": data.get("resultFormula") or data.get("result_formula") or "count",
        "operator": data.get("operator") or "eq",
        "threshold": data.get("threshold", 0),
    }


def unique_code(datasource_id: int, metric: str, metric_parameter: dict) -> str:
    raw = "|".join(
        [
            str(datasource_id),
            str(metric_parameter.get("database") or ""),
            str(metric_parameter.get("table") or ""),
            str(metric_parameter.get("column") or ""),
            metric,
        ]
    )
    return raw[:250]


def submit_execution(session: Session, job_id: int, schedule_time: datetime | None = None) -> JobExecution:
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError("作业不存在")
    moment = _now()
    execution = JobExecution(
        name=f"{job.name}-{moment:%Y%m%d%H%M%S}",
        job_id=job.id,
        job_type=job.type or 0,
        schema_name=job.schema_name,
        table_name=job.table_name,
        column_name=job.column_name,
        metric_type=job.metric_type,
        datasource_id=job.datasource_id,
        execute_platform_type=job.execute_platform_type or "local",
        execute_platform_parameter=job.execute_platform_parameter,
        engine_type=job.engine_type or "local",
        engine_parameter=job.engine_parameter,
        parameter=job.parameter or "{}",
        status=EXEC_SUBMITTED,
        retry_times=job.retry_times or 0,
        retry_interval=job.retry_interval or 0,
        timeout=job.timeout or 0,
        timeout_strategy=job.timeout_strategy or 0,
        pre_sql=job.pre_sql,
        post_sql=job.post_sql,
        tenant_code=str(job.tenant_code) if job.tenant_code is not None else None,
        execute_host=socket.gethostname(),
        process_id=os.getpid(),
        submit_time=moment,
        schedule_time=schedule_time or moment,
    )
    if job.error_data_storage_id:
        storage = session.get(ErrorDataStorage, job.error_data_storage_id)
        if storage:
            execution.error_data_storage_type = storage.type
            execution.error_data_storage_parameter = storage.param
    session.add(execution)
    session.flush()
    return execution


def run_execution(execution_id: int) -> None:
    holder = {"engine": None, "timed_out": False}
    with _lock:
        _holders[execution_id] = holder
        _cancel.discard(execution_id)
    log = JobLog(execution_id)
    timer = None
    try:
        with SessionLocal() as session:
            execution = session.get(JobExecution, execution_id)
            if execution is None:
                return
            execution.status = EXEC_RUNNING
            execution.start_time = _now()
            execution.log_path = log.path
            execution.execute_host = socket.gethostname()
            session.commit()
            timeout = execution.timeout or 0
            if timeout and timeout > 0:
                def _fire():
                    holder["timed_out"] = True
                    request_cancel(execution_id)
                    log.line(f"TIMEOUT 超过 {timeout} 秒，尝试中断连接")
                timer = threading.Timer(timeout, _fire)
                timer.daemon = True
                timer.start()
            attempts = (execution.retry_times or 0) + 1
            interval = execution.retry_interval or 0
            last_error = None
            for attempt in range(1, attempts + 1):
                if _cancelled(execution_id):
                    break
                try:
                    log.line(f"开始执行 attempt={attempt}/{attempts} engine={execution.engine_type}")
                    _run_once(session, execution, log, holder)
                    last_error = None
                    break
                except Cancelled:
                    last_error = "killed" if not holder["timed_out"] else "timeout"
                    break
                except NotImplementedError as exc:
                    last_error = str(exc)
                    log.line(f"ERROR {exc}")
                    break
                except Exception as exc:
                    last_error = str(exc)
                    log.line(f"ERROR attempt={attempt} {exc}")
                    logger.exception("execution %s failed", execution_id)
                    session.rollback()
                    if attempt < attempts and interval:
                        log.line(f"等待 {interval} 秒后重试")
                        threading.Event().wait(interval)
            execution = session.get(JobExecution, execution_id)
            if _cancelled(execution_id) or last_error in ("killed", "timeout"):
                execution.status = EXEC_KILLED if last_error != "timeout" else EXEC_FAILURE
                if last_error == "timeout":
                    log.line("执行超时，状态记为失败")
                else:
                    log.line("执行已终止")
            elif last_error:
                execution.status = EXEC_FAILURE
                log.line("执行失败")
                _open_issue_and_alert(session, execution, failed_quality=False, message=last_error, log=log)
            else:
                execution.status = EXEC_SUCCESS
                log.line("执行完成")
            execution.end_time = _now()
            session.commit()
    finally:
        if timer:
            timer.cancel()
        log.close()
        with _lock:
            _holders.pop(execution_id, None)
            _cancel.discard(execution_id)


def _run_once(session: Session, execution: JobExecution, log: JobLog, holder: dict) -> None:
    job = session.get(Job, execution.job_id)
    if job is None:
        raise ValueError("作业已被删除")
    engine_type = (execution.engine_type or "local").lower()
    if engine_type == "spark":
        SparkEngine().execute({"executionId": execution.id})
    if engine_type not in ("local", "jdbc"):
        raise ValueError(f"不支持的执行引擎: {engine_type}")
    spec = _param(job)
    metric = get_metric(spec["metric"])
    ds = session.get(DataSource, execution.datasource_id)
    if ds is None:
        raise ValueError("数据源不存在")
    src_param = parse_json(ds.param, {})
    tables = [part.strip() for part in str(spec["metricParameter"].get("table") or "").split(",") if part.strip()] or [""]
    if metric.kind != "row_count":
        tables = tables[:1]
    any_fail = False
    messages = []
    for table_name in tables:
        if _cancelled(execution.id):
            raise Cancelled("killed")
        mp = dict(spec["metricParameter"])
        if table_name:
            mp["table"] = table_name
        plan = build_sql(metric.name, mp)
        log.line(f"指标 {metric.zh_name} ({metric.name})")
        log.line(f"ACTUAL_SQL {plan.actual_sql}")
        if plan.invalidate_sql:
            log.line(f"INVALIDATE_SQL {plan.invalidate_sql}")
        if plan.expected_sql:
            log.line(f"TARGET_SQL {plan.expected_sql}")
        want_errors = bool(metric.error_output)
        outcome = run_plan(
            src_param,
            ds.type,
            plan,
            pre_sql=execution.pre_sql if table_name == tables[0] else None,
            post_sql=execution.post_sql if table_name == tables[-1] else None,
            collect_errors=want_errors,
            cancel_probe=lambda: _cancelled(execution.id) or holder.get("timed_out", False),
            engine_holder=holder,
        )
        if holder.get("timed_out"):
            raise Cancelled("timeout")
        code = unique_code(ds.id, metric.name, mp)
        history = [
            (row.data_time, Decimal(str(row.actual_value)))
            for row in session.query(ActualValue).filter(ActualValue.unique_code == code).all()
            if row.actual_value is not None and row.data_time is not None
        ]
        expected_type = spec["expectedType"]
        if metric.kind == "multi_compare" and outcome["expected_from_target"] is not None:
            expected = outcome["expected_from_target"]
            expected_type = "target_metric"
            log.line("两表值比对：期望值取目标表聚合结果")
        else:
            table_rows = target_rows = None
            if expected_type == "table_total_rows":
                table_rows = _count_table(src_param, ds.type, mp, holder, execution.id)
            if expected_type == "target_table_total_rows":
                target_rows = _count_target(src_param, ds.type, mp, holder, execution.id)
            expected = compute_expected(
                expected_type,
                fix_value=(spec["expectedParameter"] or {}).get("expected_value"),
                history=history,
                data_time=execution.schedule_time or _now(),
                table_rows=table_rows,
                target_table_rows=target_rows,
            )
        judgment = judge(
            outcome["actual"],
            expected,
            spec["resultFormula"],
            spec["operator"],
            spec["threshold"],
            metric.direction,
        )
        log.line(
            f"actual={judgment.actual} expected={judgment.expected} formula={judgment.formula} "
            f"result={judgment.result} operator={judgment.operator} threshold={judgment.threshold} "
            f"state={'SUCCESS' if judgment.success else 'FAIL'} score={judgment.score}"
        )
        key = code if len(tables) == 1 else f"{code}|{table_name}"
        result = JobExecutionResult(
            job_execution_id=execution.id,
            metric_unique_key=key[:250],
            metric_type=metric.name,
            metric_dimension=metric.dimension,
            metric_name=metric.zh_name,
            database_name=mp.get("database"),
            table_name=mp.get("table"),
            column_name=mp.get("column"),
            actual_value=judgment.actual,
            expected_value=judgment.expected,
            expected_type=expected_type,
            result_formula=judgment.formula,
            operator=judgment.operator,
            threshold=judgment.threshold,
            score=judgment.score,
            state=judgment.state,
        )
        session.add(result)
        session.flush()
        if outcome["payload"] is not None:
            session.add(MetricPayload(job_execution_result_id=result.id, payload=json.dumps(outcome["payload"], ensure_ascii=False)))
        session.add(
            ActualValue(
                job_execution_id=execution.id,
                metric_name=metric.name,
                unique_code=code,
                actual_value=judgment.actual,
                data_time=execution.schedule_time or _now(),
            )
        )
        if not judgment.success:
            any_fail = True
            messages.append(f"{metric.zh_name} {mp.get('table')}.{mp.get('column') or ''} 实际值 {judgment.actual} 未通过")
            _store_errors(session, execution, job, outcome["errors"], log)
        _refresh_reports(session, execution, result)
    if any_fail:
        _open_issue_and_alert(session, execution, failed_quality=True, message="\n".join(messages), log=log)
    session.commit()


def _count_table(src_param, dtype, mp, holder, execution_id) -> Decimal:
    ref = table_ref(mp.get("database"), mp.get("table"))
    sql = f"select count(1) as actual_value from {ref}"
    return scalar_on_source(src_param, dtype, sql, holder, lambda: _cancelled(execution_id))


def _count_target(src_param, dtype, mp, holder, execution_id) -> Decimal:
    database = mp.get("database2") or mp.get("database")
    ref = table_ref(database, mp.get("table2"))
    sql = f"select count(1) as actual_value from {ref}"
    return scalar_on_source(src_param, dtype, sql, holder, lambda: _cancelled(execution_id))


def _store_errors(session, execution, job, rows: list[dict], log: JobLog) -> None:
    if not rows:
        log.line("规则失败，但该指标没有可导出的错误行")
        return
    for row in rows:
        session.add(ErrorDataRow(job_execution_id=execution.id, storage_type="metadata", row_data=json.dumps(row, ensure_ascii=False, default=str)))
    log.line(f"写入元数据库错误样本 {len(rows)} 行")
    if job.error_data_storage_id:
        storage = session.get(ErrorDataStorage, job.error_data_storage_id)
        if storage:
            try:
                write_external_errors(parse_json(storage.param, {}), storage.type, execution.id, rows)
                log.line(f"错误样本已写入外部存储 {storage.name}")
            except Exception as exc:
                log.line(f"外部错误存储写入失败: {exc}")
    if job.is_error_data_output_to_datasource:
        ds = session.get(DataSource, execution.datasource_id)
        database = job.error_data_output_to_datasource_database or execution.schema_name
        param = parse_json(ds.param, {})
        param = dict(param)
        if database:
            param["database"] = database
        try:
            write_external_errors(param, ds.type, execution.id, rows)
            log.line("错误样本已写回被检数据源 datavines_error_data")
        except Exception as exc:
            log.line(f"写回被检数据源失败: {exc}")


def _refresh_reports(session: Session, execution: JobExecution, result: JobExecutionResult) -> None:
    report_date = (execution.schedule_time or _now()).date()
    levels = [("DATASOURCE", None, None, None), ("DATABASE", result.database_name, None, None)]
    if result.table_name:
        levels.append(("TABLE", result.database_name, result.table_name, None))
    if result.column_name:
        levels.append(("COLUMN", result.database_name, result.table_name, result.column_name))
    start = datetime.combine(report_date, datetime.min.time())
    end = datetime.combine(report_date, datetime.max.time())
    today_results = (
        session.query(JobExecutionResult)
        .join(JobExecution, JobExecution.id == JobExecutionResult.job_execution_id)
        .filter(
            JobExecution.datasource_id == execution.datasource_id,
            JobExecution.schedule_time >= start,
            JobExecution.schedule_time <= end,
        )
        .all()
    )
    # include the just-flushed result even if schedule filter misses it
    if result not in today_results:
        today_results.append(result)
    for level, database_name, table_name, column_name in levels:
        matched = []
        for item in today_results:
            if level == "DATASOURCE":
                matched.append(item)
            elif level == "DATABASE" and item.database_name == database_name:
                matched.append(item)
            elif level == "TABLE" and item.database_name == database_name and item.table_name == table_name:
                matched.append(item)
            elif level == "COLUMN" and item.database_name == database_name and item.table_name == table_name and item.column_name == column_name:
                matched.append(item)
        if not matched:
            continue
        score = sum((Decimal(str(item.score or 0)) for item in matched), Decimal("0")) / Decimal(len(matched))
        report = (
            session.query(JobQualityReport)
            .filter(
                JobQualityReport.datasource_id == execution.datasource_id,
                JobQualityReport.entity_level == level,
                JobQualityReport.database_name == database_name,
                JobQualityReport.table_name == table_name,
                JobQualityReport.column_name == column_name,
                JobQualityReport.report_date == report_date,
            )
            .one_or_none()
        )
        # NULL comparisons in SQL are unknown. Fall back to python filter when names are None.
        if report is None:
            candidates = (
                session.query(JobQualityReport)
                .filter(
                    JobQualityReport.datasource_id == execution.datasource_id,
                    JobQualityReport.entity_level == level,
                    JobQualityReport.report_date == report_date,
                )
                .all()
            )
            report = next(
                (
                    item
                    for item in candidates
                    if item.database_name == database_name and item.table_name == table_name and item.column_name == column_name
                ),
                None,
            )
        if report is None:
            report = JobQualityReport(
                datasource_id=execution.datasource_id,
                entity_level=level,
                database_name=database_name,
                table_name=table_name,
                column_name=column_name,
                score=score,
                report_date=report_date,
            )
            session.add(report)
            session.flush()
        else:
            report.score = score
            report.update_time = _now()
        exists = (
            session.query(JobExecutionResultReportRel)
            .filter(
                JobExecutionResultReportRel.quality_report_id == report.id,
                JobExecutionResultReportRel.job_execution_result_id == result.id,
            )
            .one_or_none()
        )
        if exists is None:
            session.add(JobExecutionResultReportRel(quality_report_id=report.id, job_execution_result_id=result.id))


def _open_issue_and_alert(session, execution: JobExecution, failed_quality: bool, message: str, log: JobLog) -> None:
    title = f"{'质量检查未通过' if failed_quality else '作业执行失败'}: {execution.name}"
    issue = Issue(title=title, content=message or title, status="bad")
    session.add(issue)
    session.flush()
    session.add(JobIssueRel(job_id=execution.job_id, issue_id=issue.id))
    log.line(f"生成 Issue #{issue.id} status=bad")
    _notify(session, execution, title, message, log)


def _notify(session, execution: JobExecution, title: str, message: str, log: JobLog) -> None:
    from app.alerts import send_feishu, write_log

    links = session.query(SlaJob).filter(SlaJob.job_id == execution.job_id).all()
    if not links:
        log.line("作业未关联 SLA，跳过飞书通知")
        return
    for link in links:
        notes = session.query(SlaNotification).filter(SlaNotification.sla_id == link.sla_id).all()
        if not notes:
            log.line(f"SLA {link.sla_id} 没有通知配置")
            continue
        for note in notes:
            sender = session.get(SlaSender, note.sender_id)
            if sender is None:
                continue
            if (sender.type or "").lower() not in ("feishu", "lark"):
                log.line(f"发送器 {sender.name} 类型 {sender.type} 未实现，仅支持飞书")
                continue
            config = parse_json(sender.config, {})
            webhook = config.get("webhook") or config.get("url")
            success, response = send_feishu(webhook, title, message)
            write_log(
                session,
                sla_id=link.sla_id,
                job_id=execution.job_id,
                execution_id=execution.id,
                sender_id=sender.id,
                webhook=webhook,
                title=title,
                content=message,
                success=success,
                response=response,
            )
            log.line(f"飞书通知 sender={sender.name} success={success} response={response[:300]}")
