import json
import re
from datetime import date, datetime
from decimal import Decimal

from fastapi.responses import JSONResponse

_camel_re = re.compile(r"_([a-zA-Z0-9])")


def camelize(key: str) -> str:
    return _camel_re.sub(lambda m: m.group(1).upper(), key)


def ok(data=None, msg: str = "Success"):
    return {"code": 200, "msg": msg, "data": data}


def fail(msg: str, code: int = 400):
    return JSONResponse(status_code=code, content={"code": code, "msg": msg, "data": None})


def dump_value(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


JSON_COLUMNS = {
    "param",
    "parameter",
    "config",
    "properties",
    "env",
    "engine_parameter",
    "execute_platform_parameter",
    "error_data_storage_parameter",
    "selected_column",
}


def dump_row(obj, *, mask_password: bool = False, extra: dict | None = None) -> dict:
    data = {}
    for column in obj.__table__.columns:
        value = dump_value(getattr(obj, column.name))
        if column.name in JSON_COLUMNS and isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                pass
        if mask_password and column.name == "param" and isinstance(value, dict) and "password" in value:
            value = {**value, "password": "******"}
        data[camelize(column.name)] = value
    if extra:
        data.update(extra)
    return data


def page_payload(records, total: int, page: int, size: int) -> dict:
    pages = (total + size - 1) // size if size else 0
    return {"records": records, "total": total, "size": size, "current": page, "pages": pages}


def as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_json(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def json_text(value) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
