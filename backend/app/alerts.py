"""Feishu webhook alerts. Other channels are intentionally not implemented."""

from __future__ import annotations

import json
import logging

import httpx

from app.models import AlertSendLog

logger = logging.getLogger("datavines.alert")

_mock_inbox: list[dict] = []


def mock_messages() -> list[dict]:
    return list(_mock_inbox)


def record_mock(title: str, content: str, webhook: str, payload: dict | None = None) -> None:
    _mock_inbox.append({"title": title, "content": content, "webhook": webhook, "payload": payload or {}})
    if len(_mock_inbox) > 200:
        del _mock_inbox[:-200]


def send_feishu(webhook: str, title: str, content: str) -> tuple[bool, str]:
    if not webhook:
        return False, "webhook 为空"
    if webhook.startswith("mock://") or "/api/v1/sla/mock/receive" in webhook:
        record_mock(title, content, webhook)
        return True, "mock webhook accepted"
    body = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": [[{"tag": "text", "text": content}]],
                }
            }
        },
    }
    try:
        response = httpx.post(webhook, json=body, timeout=10.0)
        text = response.text[:2000]
        success = response.status_code < 300
        try:
            parsed = response.json()
            if isinstance(parsed, dict) and parsed.get("code") not in (None, 0):
                success = False
        except json.JSONDecodeError:
            pass
        return success, text
    except Exception as exc:  # network errors stay on the audit row
        logger.warning("feishu send failed: %s", exc)
        return False, str(exc)


def write_log(session, *, sla_id, job_id, execution_id, sender_id, webhook, title, content, success, response) -> None:
    session.add(
        AlertSendLog(
            sla_id=sla_id,
            job_id=job_id,
            job_execution_id=execution_id,
            sender_id=sender_id,
            channel="feishu",
            webhook=webhook,
            title=title,
            content=content,
            success=1 if success else 0,
            response_body=response,
        )
    )
