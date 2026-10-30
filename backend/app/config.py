from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "DataVines"
    database_url: str = "mysql+pymysql://datavines:datavines@127.0.0.1:3306/datavines?charset=utf8mb4"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 5600
    log_dir: str = "/tmp/datavines/logs"
    enable_worker: bool = True
    auto_bootstrap_demo: bool = False
    default_user_id: int = 1
    default_workspace_id: int = 1
    worker_interval_seconds: int = 2
    schedule_interval_seconds: int = 20


settings = Settings()
