"""Load the upstream dv_user / dv_workspace / dv_config inserts once."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.models import User


def sql_file() -> Path | None:
    env = os.environ.get("DATAVINES_SQL_PATH")
    candidates = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "scripts" / "sql" / "datavines-mysql.sql",
            here.parents[1] / "sql" / "datavines-mysql.sql",
            Path("/app/sql/datavines-mysql.sql"),
        ]
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _split(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    for char in sql:
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            statement = "".join(buf).strip()
            if statement:
                parts.append(statement)
            buf = []
        else:
            buf.append(char)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def seed() -> None:
    with SessionLocal() as session:
        if session.query(User).count():
            return
        path = sql_file()
        if path is None:
            session.add(User(id=1, username="admin", password="admin", email="admin@example.com", admin=1))
            session.commit()
            return
        raw = path.read_text(encoding="utf-8")
        start = raw.find("INSERT INTO `dv_config`")
        if start < 0:
            return
        for statement in _split(raw[start:]):
            if not statement.upper().startswith("INSERT"):
                continue
            session.execute(text(statement))
        session.commit()
