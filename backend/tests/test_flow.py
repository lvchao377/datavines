"""End-to-end check against the metadata MySQL: demo null check fails, row count passes."""

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
def test_demo_jobs_judge_on_mysql():
    from app.bootstrap import init_database
    from app.demo import bootstrap_demo
    from app.models import AlertSendLog, ErrorDataRow, Job, JobExecution, JobExecutionResult
    from app.runner import run_execution, submit_execution

    init_database()
    info = bootstrap_demo()
    expectations = {
        "demo_email_null_check": {"actual": 1, "state": 2},
        "demo_orders_row_count": {"actual": 8, "state": 1},
    }
    with SessionLocal() as session:
        jobs = session.query(Job).filter(Job.name.in_(expectations)).all()
        assert {job.name for job in jobs} == set(expectations)
        pairs = [(job.id, job.name) for job in jobs]
    for job_id, name in pairs:
        with SessionLocal() as session:
            execution = submit_execution(session, job_id)
            session.commit()
            execution_id = execution.id
        run_execution(execution_id)
        with SessionLocal() as session:
            execution = session.get(JobExecution, execution_id)
            result = session.query(JobExecutionResult).filter(JobExecutionResult.job_execution_id == execution_id).one()
            assert execution.status == 7
            assert float(result.actual_value) == expectations[name]["actual"]
            assert result.state == expectations[name]["state"]
            if name == "demo_email_null_check":
                assert session.query(ErrorDataRow).filter(ErrorDataRow.job_execution_id == execution_id).count() >= 1
                assert session.query(AlertSendLog).filter(AlertSendLog.job_execution_id == execution_id, AlertSendLog.success == 1).count() >= 1
    assert info["datasourceId"]
