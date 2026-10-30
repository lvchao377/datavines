import logging
import time
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings
from app.seed import seed

logger = logging.getLogger("datavines.bootstrap")


def init_database() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    last_error: Exception | None = None
    for attempt in range(1, 31):
        try:
            command.upgrade(cfg, "head")
            seed()
            return
        except Exception as exc:
            last_error = exc
            logger.warning("database not ready (attempt %s): %s", attempt, exc)
            time.sleep(2)
    raise RuntimeError("metadata database is not reachable") from last_error
