from datetime import datetime
from unittest.mock import MagicMock

import httpx
import pytest

from app.alerts import send_feishu
from app.connectors import normalize_type, sqlalchemy_url, validate_param
from app.scheduler import cron_due, normalize_cron, upcoming


def test_doris_uses_mysql_protocol_and_default_port():
    clean = validate_param({"host": "fe.doris.local", "user": "root", "password": "secret"}, "doris")
    assert clean["port"] == 9030
    url = sqlalchemy_url(clean)
    assert url.startswith("mysql+pymysql://")
    assert "@fe.doris.local:9030/" in url
    explicit = validate_param({"host": "127.0.0.1", "port": 3306, "user": "datavines", "password": "datavines", "database": "demo"}, "Doris")
    assert explicit["port"] == 3306
    assert "/demo?" in sqlalchemy_url(explicit)


def test_stub_datasource_types_are_rejected():
    with pytest.raises(ValueError, match="未实现"):
        normalize_type("postgresql")
    with pytest.raises(ValueError):
        validate_param({"host": "h", "user": "u"}, "hive")


def test_feishu_mock_and_http(monkeypatch):
    ok, message = send_feishu("mock://bot", "标题", "正文")
    assert ok and "mock" in message
    ok, message = send_feishu("http://127.0.0.1:9/api/v1/sla/mock/receive", "标题", "正文")
    assert ok and "mock" in message

    response = MagicMock(status_code=200, text='{"code":0}')
    response.json.return_value = {"code": 0}
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response)
    ok, body = send_feishu("https://open.feishu.cn/open-apis/bot/v2/hook/demo", "告警", "空值未通过")
    assert ok and "code" in body

    bad = MagicMock(status_code=200, text='{"code":19024}')
    bad.json.return_value = {"code": 19024}
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: bad)
    ok, _ = send_feishu("https://open.feishu.cn/open-apis/bot/v2/hook/demo", "告警", "失败")
    assert ok is False

    ok, message = send_feishu("", "t", "c")
    assert ok is False and "webhook" in message


def test_cron_normalization_and_window():
    expr, seconds = normalize_cron("0 10 2 * * ?")
    assert seconds is True and expr == "0 10 2 * * *"
    five, seconds = normalize_cron("10 2 * * *")
    assert seconds is False and five == "10 2 * * *"
    times = upcoming("10 2 * * *", 2, start=datetime(2026, 10, 30, 0, 0, 0))
    assert times[0] == "2026-10-30 02:10:00"
    assert cron_due("* * * * *", datetime(2026, 10, 30, 12, 0, 10)) is True
    assert cron_due("* * * * *", datetime(2026, 10, 30, 12, 0, 50)) is False
    with pytest.raises(ValueError):
        normalize_cron("not a cron")
