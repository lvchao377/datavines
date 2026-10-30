"""Load the upstream dv_user / dv_workspace / dv_config inserts once."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import func, text

from app.auth import hash_password, verify_password
from app.db import SessionLocal
from app.models import User, UserWorkspace, Workspace

DEMO_ACCOUNTS = (
    {"username": "admin", "email": "admin@gmail.com", "admin": 1, "workspace": "admin's default"},
    {"username": "user", "email": "user@gmail.com", "admin": 0, "workspace": "user's default"},
)


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


def _sqlite_id(session, model) -> int | None:
    bind = session.get_bind()
    if bind is None or bind.dialect.name != "sqlite":
        return None
    current = session.query(func.max(model.id)).scalar() or 0
    return int(current) + 1


def ensure_auth_users(session) -> None:
    """Keep the two demo accounts and give each a private default workspace."""
    for spec in DEMO_ACCOUNTS:
        user = session.query(User).filter(User.username == spec["username"]).one_or_none()
        if user is None:
            user = User(
                username=spec["username"],
                password=hash_password("123456"),
                email=spec["email"],
                admin=spec["admin"],
            )
            assigned = _sqlite_id(session, User)
            if assigned is not None:
                user.id = assigned
            session.add(user)
            session.flush()
        else:
            if not verify_password("123456", user.password):
                user.password = hash_password("123456")
            if spec["username"] == "admin":
                user.admin = 1
        workspace = session.query(Workspace).filter(Workspace.name == spec["workspace"]).one_or_none()
        if workspace is None:
            workspace = Workspace(name=spec["workspace"], create_by=user.id, update_by=user.id)
            assigned = _sqlite_id(session, Workspace)
            if assigned is not None:
                workspace.id = assigned
            session.add(workspace)
            session.flush()
        link = (
            session.query(UserWorkspace)
            .filter(UserWorkspace.user_id == user.id, UserWorkspace.workspace_id == workspace.id)
            .one_or_none()
        )
        if link is None:
            link = UserWorkspace(
                user_id=user.id,
                workspace_id=workspace.id,
                role_id=1,
                create_by=user.id,
                update_by=user.id,
            )
            assigned = _sqlite_id(session, UserWorkspace)
            if assigned is not None:
                link.id = assigned
            session.add(link)
    session.flush()


def seed() -> None:
    with SessionLocal() as session:
        if session.query(User).count() == 0:
            path = sql_file()
            if path is None:
                session.flush()
            else:
                raw = path.read_text(encoding="utf-8")
                start = raw.find("INSERT INTO `dv_config`")
                if start >= 0:
                    for statement in _split(raw[start:]):
                        if not statement.upper().startswith("INSERT"):
                            continue
                        session.execute(text(statement))
                    session.flush()
        ensure_auth_users(session)
        session.commit()
