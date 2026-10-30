"""Single-node scheduler: cron on dv_job_schedule / dv_common_task_schedule plus a command worker."""

from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime, timedelta

from croniter import croniter

from app.config import settings
from app.constants import CMD_START, CMD_STOP, EXEC_FAILURE, EXEC_RUNNING, TASK_FAILURE, TASK_PENDING, TASK_RUNNING, TASK_SUCCESS
from app.db import SessionLocal
from app.models import Command, CommonTask, CommonTaskCommand, CommonTaskSchedule, JobExecution, JobSchedule
from app.runner import request_cancel, run_execution, submit_execution

logger = logging.getLogger("datavines.scheduler")
_wake = threading.Event()
_started = False
_lock = threading.Lock()


def wake() -> None:
    _wake.set()


def normalize_cron(expression: str) -> tuple[str, bool]:
    expr = " ".join((expression or "").strip().replace("?", "*").split())
    parts = expr.split(" ")
    if len(parts) == 7:
        parts = parts[:6]
    if len(parts) == 6:
        return " ".join(parts), True
    if len(parts) == 5:
        return " ".join(parts), False
    raise ValueError("Cron 需要 5 位（分 时 日 月 周）或 6 位 Quartz（秒在前）")


def cron_due(expression: str, now: datetime) -> bool:
    try:
        norm, with_seconds = normalize_cron(expression)
    except ValueError:
        return False
    if with_seconds:
        previous = croniter(norm, now, second_at_beginning=True).get_prev(datetime)
    else:
        previous = croniter(norm, now).get_prev(datetime)
    return 0 <= (now - previous).total_seconds() <= settings.schedule_interval_seconds + 5


def upcoming(expression: str, count: int = 5, start: datetime | None = None) -> list[str]:
    norm, with_seconds = normalize_cron(expression)
    moment = start or datetime.now()
    iterator = croniter(norm, moment, second_at_beginning=with_seconds) if with_seconds else croniter(norm, moment)
    return [iterator.get_next(datetime).strftime("%Y-%m-%d %H:%M:%S") for _ in range(count)]


def enqueue_job(session, job_id: int, schedule_time: datetime | None = None) -> int:
    execution = submit_execution(session, job_id, schedule_time=schedule_time)
    session.add(Command(type=CMD_START, job_execution_id=execution.id, priority=2, parameter="{}"))
    session.commit()
    wake()
    return execution.id


def enqueue_stop(session, execution_id: int) -> None:
    session.add(Command(type=CMD_STOP, job_execution_id=execution_id, priority=0, parameter="{}"))
    session.commit()
    request_cancel(execution_id)
    wake()


def enqueue_common(session, task_type: str, datasource_id: int, database: str | None, table: str | None, parameter: str, schedule_time: datetime | None = None) -> int:
    moment = datetime.now().replace(microsecond=0)
    task = CommonTask(
        task_type=task_type,
        type="manual" if schedule_time is None else "schedule",
        datasource_id=datasource_id,
        database_name=database,
        table_name=table,
        status=TASK_PENDING,
        parameter=parameter or "{}",
        submit_time=moment,
        schedule_time=schedule_time or moment,
        execute_host=socket.gethostname(),
    )
    session.add(task)
    session.flush()
    session.add(CommonTaskCommand(task_id=task.id))
    session.commit()
    wake()
    return task.id


def _tick_schedules() -> None:
    now = datetime.now().replace(microsecond=0)
    with SessionLocal() as session:
        for schedule in session.query(JobSchedule).filter(JobSchedule.status == 1).all():
            if not schedule.cron_expression:
                continue
            if schedule.start_time and now < schedule.start_time:
                continue
            if schedule.end_time and now > schedule.end_time:
                continue
            if not cron_due(schedule.cron_expression, now):
                continue
            recent = (
                session.query(JobExecution)
                .filter(JobExecution.job_id == schedule.job_id, JobExecution.submit_time >= now - timedelta(seconds=70))
                .first()
            )
            if recent:
                continue
            try:
                enqueue_job(session, schedule.job_id, schedule_time=now)
                logger.info("scheduled job %s", schedule.job_id)
            except Exception:
                logger.exception("schedule job %s failed", schedule.job_id)
        for schedule in session.query(CommonTaskSchedule).filter(CommonTaskSchedule.status == 1).all():
            if not schedule.cron_expression or not cron_due(schedule.cron_expression, now):
                continue
            recent = (
                session.query(CommonTask)
                .filter(
                    CommonTask.datasource_id == schedule.datasource_id,
                    CommonTask.task_type == schedule.task_type,
                    CommonTask.submit_time >= now - timedelta(seconds=70),
                )
                .first()
            )
            if recent:
                continue
            enqueue_common(
                session,
                schedule.task_type or "CATALOG_METADATA",
                schedule.datasource_id,
                None,
                None,
                schedule.param or "{}",
                schedule_time=now,
            )


def _run_common(task_id: int) -> None:
    from app.catalog import refresh_datasource
    from app.profile import profile_table
    from app.util import parse_json

    with SessionLocal() as session:
        task = session.get(CommonTask, task_id)
        if task is None:
            return
        task.status = TASK_RUNNING
        task.start_time = datetime.now()
        session.commit()
        try:
            param = parse_json(task.parameter, {})
            if not isinstance(param, dict):
                param = {}
            if task.task_type == "DATA_PROFILE":
                columns = param.get("columns")
                profile_table(session, task.datasource_id, param.get("database") or task.database_name, param.get("table") or task.table_name, columns)
            else:
                refresh_datasource(session, task.datasource_id, param.get("database") or task.database_name)
            task = session.get(CommonTask, task_id)
            task.status = TASK_SUCCESS
        except Exception as exc:
            logger.exception("common task %s failed", task_id)
            session.rollback()
            task = session.get(CommonTask, task_id)
            task.status = TASK_FAILURE
            task.parameter = str(exc)[:2000]
        task.end_time = datetime.now()
        session.commit()


def _drain_once() -> bool:
    did = False
    with SessionLocal() as session:
        command = session.query(Command).order_by(Command.priority.asc(), Command.id.asc()).with_for_update(skip_locked=True).first()
        if command is not None:
            execution_id = command.job_execution_id
            kind = command.type
            session.delete(command)
            session.commit()
            did = True
            if kind == CMD_STOP:
                request_cancel(execution_id)
                with SessionLocal() as inner:
                    execution = inner.get(JobExecution, execution_id)
                    if execution and execution.status in (EXEC_RUNNING, 0):
                        execution.status = 9
                        execution.end_time = datetime.now()
                        inner.commit()
            else:
                run_execution(execution_id)
            return did
        common = session.query(CommonTaskCommand).order_by(CommonTaskCommand.id.asc()).with_for_update(skip_locked=True).first()
        if common is not None:
            task_id = common.task_id
            session.delete(common)
            session.commit()
            did = True
            _run_common(task_id)
    return did


def _recover() -> None:
    with SessionLocal() as session:
        now = datetime.now()
        for execution in session.query(JobExecution).filter(JobExecution.status == EXEC_RUNNING).all():
            execution.status = EXEC_FAILURE
            execution.end_time = now
        for task in session.query(CommonTask).filter(CommonTask.status == TASK_RUNNING).all():
            task.status = TASK_FAILURE
            task.end_time = now
        session.commit()


def _worker() -> None:
    while True:
        try:
            while _drain_once():
                pass
        except Exception:
            logger.exception("worker loop error")
        _wake.wait(timeout=settings.worker_interval_seconds)
        _wake.clear()


def _scheduler() -> None:
    while True:
        try:
            _tick_schedules()
        except Exception:
            logger.exception("schedule tick error")
        _wake.wait(timeout=settings.schedule_interval_seconds)


def start_background() -> None:
    global _started
    with _lock:
        if _started or not settings.enable_worker:
            return
        _started = True
    _recover()
    threading.Thread(target=_worker, name="dv-worker", daemon=True).start()
    threading.Thread(target=_scheduler, name="dv-scheduler", daemon=True).start()
