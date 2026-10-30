"""JWT login tokens and workspace membership checks.

Metric catalog GETs stay public. Every other /api/v1 route needs a Bearer token
from POST /login. Passwords are bcrypt hashes; the token does not carry the hash.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

_PUBLIC_EXACT = {"/login", "/register", "/health"}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username,
        "uid": int(user.id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.jwt_expire_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def is_public(method: str, path: str) -> bool:
    if method.upper() == "OPTIONS":
        return True
    prefix = settings.api_prefix.rstrip("/")
    if not path.startswith(prefix):
        return True
    rest = path[len(prefix):] or "/"
    if rest in _PUBLIC_EXACT:
        return True
    if rest == "/metric" or rest.startswith("/metric/"):
        return method.upper() == "GET"
    return False


def extract_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header:
        value = header.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        return value or None
    query = request.query_params.get("Authorization") or request.query_params.get("token")
    return query.strip() if query else None


def member_workspace_ids(db, user_id: int) -> set[int]:
    from app.models import UserWorkspace

    rows = db.query(UserWorkspace.workspace_id).filter(UserWorkspace.user_id == user_id).all()
    return {int(row[0]) for row in rows}


class AuthMiddleware:
    """Reject /api/v1 calls that are not public and do not carry a valid JWT."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET")
        path = scope.get("path") or ""
        if is_public(method, path):
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        token = extract_token(request)
        if not token:
            await _unauthorized("未登录")(scope, receive, send)
            return
        try:
            payload = decode_token(token)
            uid = int(payload["uid"])
            username = str(payload.get("sub") or "")
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            await _unauthorized("登录已失效")(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        state["user_id"] = uid
        state["username"] = username
        await self.app(scope, receive, send)


def _unauthorized(msg: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"code": 401, "msg": msg, "data": None})
