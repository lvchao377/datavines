"""Metadata tables aligned with upstream scripts/sql/datavines-mysql.sql (dv_*).

Two extension tables used by this clone are defined at the bottom:
dv_error_data (error-row samples in the metadata database) and
dv_alert_send_log (Feishu delivery audit) and dv_metric_payload (LIST metrics).
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

TABLE_ARGS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def _ts():
    return mapped_column(DateTime, nullable=False, default=datetime.now, server_default=text("CURRENT_TIMESTAMP"))


class User(Base):
    __tablename__ = "dv_user"
    __table_args__ = (UniqueConstraint("username", name="user_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(127))
    admin: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class Workspace(Base):
    __tablename__ = "dv_workspace"
    __table_args__ = (UniqueConstraint("name", name="workspace_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class UserWorkspace(Base):
    __tablename__ = "dv_user_workspace"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role_id: Mapped[int | None] = mapped_column(BigInteger)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class AccessToken(Base):
    __tablename__ = "dv_access_token"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    token: Mapped[str] = mapped_column(String(1024), nullable=False)
    expire_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class Config(Base):
    __tablename__ = "dv_config"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    var_key: Mapped[str] = mapped_column(String(255), nullable=False)
    var_value: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class DataSource(Base):
    __tablename__ = "dv_datasource"
    __table_args__ = (UniqueConstraint("name", name="datasource_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(255), default="database", server_default="database")
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    param: Mapped[str] = mapped_column(Text, nullable=False)
    param_code: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class Env(Base):
    __tablename__ = "dv_env"
    __table_args__ = (UniqueConstraint("name", name="env_name"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    env: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class Tenant(Base):
    __tablename__ = "dv_tenant"
    __table_args__ = (UniqueConstraint("tenant", name="tenant_name"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class ErrorDataStorage(Base):
    __tablename__ = "dv_error_data_storage"
    __table_args__ = (UniqueConstraint("name", "workspace_id", name="name_wp_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    param: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class Job(Base):
    __tablename__ = "dv_job"
    __table_args__ = (
        UniqueConstraint("name", "datasource_id", "schema_name", "table_name", "column_name", name="unique_name"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str | None] = mapped_column(String(255))
    type: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    datasource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    datasource_id_2: Mapped[int | None] = mapped_column(BigInteger)
    schema_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str | None] = mapped_column(String(128))
    column_name: Mapped[str | None] = mapped_column(String(128))
    selected_column: Mapped[str | None] = mapped_column(Text)
    metric_type: Mapped[str | None] = mapped_column(String(255))
    execute_platform_type: Mapped[str | None] = mapped_column(String(128))
    execute_platform_parameter: Mapped[str | None] = mapped_column(Text)
    engine_type: Mapped[str | None] = mapped_column(String(128))
    engine_parameter: Mapped[str | None] = mapped_column(Text)
    error_data_storage_id: Mapped[int | None] = mapped_column(BigInteger)
    is_error_data_output_to_datasource: Mapped[bool | None] = mapped_column(Boolean, default=False, server_default="0")
    error_data_output_to_datasource_database: Mapped[str | None] = mapped_column(String(255))
    parameter: Mapped[str | None] = mapped_column(Text)
    retry_times: Mapped[int | None] = mapped_column(Integer)
    retry_interval: Mapped[int | None] = mapped_column(Integer)
    timeout: Mapped[int | None] = mapped_column(Integer)
    timeout_strategy: Mapped[int | None] = mapped_column(Integer)
    pre_sql: Mapped[str | None] = mapped_column(Text)
    post_sql: Mapped[str | None] = mapped_column(Text)
    tenant_code: Mapped[int | None] = mapped_column(BigInteger)
    env: Mapped[int | None] = mapped_column(BigInteger)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class JobSchedule(Base):
    __tablename__ = "dv_job_schedule"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    param: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int | None] = mapped_column(SmallInteger)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class JobExecution(Base):
    __tablename__ = "dv_job_execution"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1, server_default="-1")
    job_type: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    schema_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str | None] = mapped_column(String(128))
    column_name: Mapped[str | None] = mapped_column(String(128))
    metric_type: Mapped[str | None] = mapped_column(String(255))
    datasource_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1, server_default="-1")
    execute_platform_type: Mapped[str | None] = mapped_column(String(128))
    execute_platform_parameter: Mapped[str | None] = mapped_column(Text)
    engine_type: Mapped[str | None] = mapped_column(String(128))
    engine_parameter: Mapped[str | None] = mapped_column(Text)
    error_data_storage_type: Mapped[str | None] = mapped_column(String(128))
    error_data_storage_parameter: Mapped[str | None] = mapped_column(Text)
    error_data_file_name: Mapped[str | None] = mapped_column(String(255))
    parameter: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[int | None] = mapped_column(Integer)
    retry_times: Mapped[int | None] = mapped_column(Integer)
    retry_interval: Mapped[int | None] = mapped_column(Integer)
    timeout: Mapped[int | None] = mapped_column(Integer)
    timeout_strategy: Mapped[int | None] = mapped_column(Integer)
    pre_sql: Mapped[str | None] = mapped_column(Text)
    post_sql: Mapped[str | None] = mapped_column(Text)
    tenant_code: Mapped[str | None] = mapped_column(String(255))
    execute_host: Mapped[str | None] = mapped_column(String(255))
    application_id: Mapped[str | None] = mapped_column(String(255))
    application_tag: Mapped[str | None] = mapped_column(String(255))
    process_id: Mapped[int | None] = mapped_column(Integer)
    execute_file_path: Mapped[str | None] = mapped_column(String(255))
    log_path: Mapped[str | None] = mapped_column(String(255))
    env: Mapped[str | None] = mapped_column(Text)
    submit_time: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_time: Mapped[datetime | None] = mapped_column(DateTime)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class JobExecutionResult(Base):
    __tablename__ = "dv_job_execution_result"
    __table_args__ = (
        UniqueConstraint("job_execution_id", "metric_unique_key", name="execution_id_un"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_execution_id: Mapped[int | None] = mapped_column(BigInteger)
    metric_unique_key: Mapped[str | None] = mapped_column(String(255))
    metric_type: Mapped[str | None] = mapped_column(String(255))
    metric_dimension: Mapped[str | None] = mapped_column(String(255))
    metric_name: Mapped[str | None] = mapped_column(String(255))
    database_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str | None] = mapped_column(String(128))
    column_name: Mapped[str | None] = mapped_column(String(128))
    actual_value: Mapped[float | None] = mapped_column(Numeric(20, 4))
    expected_value: Mapped[float | None] = mapped_column(Numeric(20, 4))
    expected_type: Mapped[str | None] = mapped_column(String(255))
    result_formula: Mapped[str | None] = mapped_column(String(255))
    operator: Mapped[str | None] = mapped_column(String(255))
    threshold: Mapped[float | None] = mapped_column(Numeric(20, 4))
    score: Mapped[float | None] = mapped_column(Numeric(20, 4), default=0, server_default="0")
    state: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class ActualValue(Base):
    __tablename__ = "dv_actual_values"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_execution_id: Mapped[int | None] = mapped_column(BigInteger)
    metric_name: Mapped[str | None] = mapped_column(String(255))
    unique_code: Mapped[str | None] = mapped_column(String(255))
    actual_value: Mapped[float | None] = mapped_column(Numeric(20, 4))
    data_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class Command(Base):
    __tablename__ = "dv_command"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    parameter: Mapped[str | None] = mapped_column(Text)
    execute_host: Mapped[str | None] = mapped_column(String(255))
    job_execution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    priority: Mapped[int | None] = mapped_column(Integer)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class JobQualityReport(Base):
    __tablename__ = "dv_job_quality_report"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    datasource_id: Mapped[int | None] = mapped_column(BigInteger)
    entity_level: Mapped[str | None] = mapped_column(String(128))
    database_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str | None] = mapped_column(String(128))
    column_name: Mapped[str | None] = mapped_column(String(128))
    score: Mapped[float | None] = mapped_column(Numeric(20, 4))
    report_date: Mapped[datetime | None] = mapped_column(Date)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class JobExecutionResultReportRel(Base):
    __tablename__ = "dv_job_execution_result_report_rel"
    __table_args__ = (
        UniqueConstraint("job_execution_result_id", "quality_report_id", name="dv_execution_report_rel_un"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    quality_report_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_execution_result_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class Issue(Base):
    __tablename__ = "dv_issue"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class JobIssueRel(Base):
    __tablename__ = "dv_job_issue_rel"
    __table_args__ = (
        UniqueConstraint("job_id", "issue_id", name="dv_entity_rel_un"),
        Index("idx_issue_id", "issue_id"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issue_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class Server(Base):
    __tablename__ = "dv_server"
    __table_args__ = (UniqueConstraint("host", "port", name="server_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class RegistryLock(Base):
    __tablename__ = "dv_registry_lock"
    __table_args__ = (
        UniqueConstraint("lock_key", name="uniq_lock_key"),
        Index("idx_upt", "update_time"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lock_key: Mapped[str] = mapped_column(String(256), nullable=False)
    lock_owner: Mapped[str] = mapped_column(String(256), nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class Sla(Base):
    __tablename__ = "dv_sla"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class SlaJob(Base):
    __tablename__ = "dv_sla_job"
    __table_args__ = (UniqueConstraint("workspace_id", "sla_id", "job_id", name="sla_job_unique"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sla_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class SlaNotification(Base):
    __tablename__ = "dv_sla_notification"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sla_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    config: Mapped[str | None] = mapped_column(Text)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class SlaSender(Base):
    __tablename__ = "dv_sla_sender"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogEntityDefinition(Base):
    __tablename__ = "dv_catalog_entity_definition"
    __table_args__ = (UniqueConstraint("uuid", name="dv_entity_definition_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    properties: Mapped[str | None] = mapped_column(Text)
    super_uuid: Mapped[str] = mapped_column(String(64), nullable=False, default="-1", server_default="-1")
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    updated_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogEntityInstance(Base):
    __tablename__ = "dv_catalog_entity_instance"
    __table_args__ = (
        UniqueConstraint("uuid", name="uuid_un"),
        UniqueConstraint("datasource_id", "fully_qualified_name", "status", name="datasource_fqn_status_un"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(127), nullable=False)
    datasource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fully_qualified_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))
    properties: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0", server_default="1.0")
    status: Mapped[str | None] = mapped_column(String(255), default="active", server_default="active")
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CatalogEntityMetricJobRel(Base):
    __tablename__ = "dv_catalog_entity_metric_job_rel"
    __table_args__ = (
        UniqueConstraint("entity_uuid", "metric_job_id", "metric_job_type", name="dv_catalog_entity_metric_rel_un"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_job_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    metric_job_type: Mapped[str] = mapped_column(String(255), nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogEntityProfile(Base):
    __tablename__ = "dv_catalog_entity_profile"
    __table_args__ = (
        UniqueConstraint("entity_uuid", "metric_name", "data_date", name="dv_entity_profile_un"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_value: Mapped[str] = mapped_column(Text, nullable=False)
    actual_value_type: Mapped[str | None] = mapped_column(String(255))
    data_date: Mapped[str | None] = mapped_column(String(255))
    update_time: Mapped[datetime] = _ts()


class CatalogEntityRel(Base):
    __tablename__ = "dv_catalog_entity_rel"
    __table_args__ = (
        UniqueConstraint("entity1_uuid", "entity2_uuid", "type", name="dv_entity_rel_un"),
        Index("idx_entity2_uuid", "entity2_uuid"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity1_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    entity2_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(64))
    related_script: Mapped[str | None] = mapped_column(Text)
    update_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)


class CatalogEntityTagRel(Base):
    __tablename__ = "dv_catalog_entity_tag_rel"
    __table_args__ = (
        UniqueConstraint("entity_uuid", "tag_uuid", name="dv_entity_tag_rel_un"),
        Index("idx_tag_uuid", "tag_uuid"),
        TABLE_ARGS,
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    tag_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogSchemaChange(Base):
    __tablename__ = "dv_catalog_schema_change"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(255))
    table_name: Mapped[str | None] = mapped_column(String(255))
    column_name: Mapped[str | None] = mapped_column(String(255))
    change_before: Mapped[str | None] = mapped_column(Text)
    change_after: Mapped[str | None] = mapped_column(Text)
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogTag(Base):
    __tablename__ = "dv_catalog_tag"
    __table_args__ = (UniqueConstraint("uuid", "category_uuid", "name", name="cu_uuid_name_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    category_uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CatalogTagCategory(Base):
    __tablename__ = "dv_catalog_tag_category"
    __table_args__ = (UniqueConstraint("uuid", "name", name="uuid_name_un"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class CommonTask(Base):
    __tablename__ = "dv_common_task"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_type: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(128))
    datasource_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=-1, server_default="-1")
    database_name: Mapped[str | None] = mapped_column(String(128))
    table_name: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[int | None] = mapped_column(Integer)
    parameter: Mapped[str | None] = mapped_column(Text)
    execute_host: Mapped[str | None] = mapped_column(String(255))
    submit_time: Mapped[datetime | None] = mapped_column(DateTime)
    schedule_time: Mapped[datetime | None] = mapped_column(DateTime)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class CommonTaskCommand(Base):
    __tablename__ = "dv_common_task_command"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_time: Mapped[datetime] = _ts()


class CommonTaskSchedule(Base):
    __tablename__ = "dv_common_task_schedule"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_type: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(255), nullable=False)
    param: Mapped[str | None] = mapped_column(Text)
    datasource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cron_expression: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int | None] = mapped_column(SmallInteger)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    create_time: Mapped[datetime] = _ts()
    update_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    update_time: Mapped[datetime] = _ts()


class ErrorDataRow(Base):
    """Extension table: sampled failing rows kept in the metadata database."""

    __tablename__ = "dv_error_data"
    __table_args__ = (Index("idx_error_exec", "job_execution_id"), TABLE_ARGS)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_execution_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_type: Mapped[str | None] = mapped_column(String(64))
    row_data: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[datetime] = _ts()


class AlertSendLog(Base):
    """Extension table: Feishu (and mock) delivery audit."""

    __tablename__ = "dv_alert_send_log"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sla_id: Mapped[int | None] = mapped_column(BigInteger)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    job_execution_id: Mapped[int | None] = mapped_column(BigInteger)
    sender_id: Mapped[int | None] = mapped_column(BigInteger)
    channel: Mapped[str | None] = mapped_column(String(40))
    webhook: Mapped[str | None] = mapped_column(String(1024))
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str | None] = mapped_column(Text)
    success: Mapped[int | None] = mapped_column(SmallInteger)
    response_body: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = _ts()


class MetricPayload(Base):
    """Extension table: LIST actual values such as column_histogram."""

    __tablename__ = "dv_metric_payload"
    __table_args__ = (TABLE_ARGS,)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_execution_result_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    create_time: Mapped[datetime] = _ts()
