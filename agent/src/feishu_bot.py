"""Feishu bot: receive messages via webhook, reply via agent."""

from __future__ import annotations
import asyncio
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN", "")

_token_cache: dict[str, Any] = {"token": "", "expires_at": 0}


def _get_tenant_token() -> str:
    """Get or refresh Feishu tenant access token."""
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]

    import requests
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    data = r.json()
    code = data.get("code", -1)
    if code != 0:
        raise RuntimeError(f"Feishu auth failed: {data.get('msg', 'unknown')}")
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires_at"] = now + data.get("expire", 7200) - 300
    return _token_cache["token"]


def reply_message(message_id: str, content: str) -> bool:
    """Reply to a Feishu message with text content."""
    if not FEISHU_APP_ID:
        logger.warning("Feishu not configured, skip reply")
        return False
    try:
        import requests
        token = _get_tenant_token()
        r = requests.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"content": json.dumps({"text": content})},
            timeout=15,
        )
        data = r.json()
        return data.get("code") == 0
    except Exception as e:
        logger.error("Feishu reply failed: %s", e)
        return False


def handle_event(event: dict) -> dict:
    """Handle a Feishu event callback. Returns response dict."""
    # URL verification challenge
    if event.get("type") == "url_verification":
        return {"challenge": event.get("challenge", "")}

    # Verify token
    token = event.get("token", "")
    if FEISHU_VERIFY_TOKEN and token != FEISHU_VERIFY_TOKEN:
        logger.warning("Feishu token mismatch")
        return {"code": 401}

    # Handle message received
    header = event.get("header", {})
    event_type = header.get("event_type", "")

    if event_type == "im.message.receive_v1":
        ev = event.get("event", {})
        msg = ev.get("message", {})
        msg_type = msg.get("message_type", "")
        msg_id = msg.get("message_id", "")
        chat_id = msg.get("chat_id", "")
        content_str = msg.get("content", "{}")

        # Skip bot's own messages and non-text
        if msg_type != "text":
            return {"code": 0}

        try:
            content = json.loads(content_str)
            text = content.get("text", "").strip()
        except json.JSONDecodeError:
            return {"code": 0}

        if not text:
            return {"code": 0}

        logger.info("Feishu message from %s: %s", chat_id, text[:100])

        # Run agent in background
        asyncio.create_task(_run_agent_and_reply(msg_id, chat_id, text))

    return {"code": 0}


async def _run_agent_and_reply(message_id: str, chat_id: str, prompt: str) -> None:
    """Run the AI agent and reply to Feishu."""
    from src.session.service import SessionService
    from src.session.store import SessionStore
    from src.session.events import EventBus
    from pathlib import Path

    try:
        # Initialize session service
        runs_dir = Path(__file__).resolve().parent.parent / "runs"
        sessions_dir = Path(__file__).resolve().parent.parent / "sessions"
        store = SessionStore(base_dir=sessions_dir)
        event_bus = EventBus()
        svc = SessionService(store=store, event_bus=event_bus, runs_dir=runs_dir)

        # Create session
        title = prompt[:30]
        session = svc.create_session(title=title)
        session_id = session.session_id

        # Send thinking indicator
        reply_message(message_id, "正在分析中，请稍候...")

        # Run agent
        result = await svc.send_message(session_id, prompt)
        attempt_id = result.get("attempt_id", "")

        # Wait for attempt to complete (poll)
        for _ in range(120):  # max 120s wait
            await asyncio.sleep(2)
            attempt = store.get_attempt(session_id, attempt_id)
            if attempt and attempt.status.value in ("completed", "failed", "cancelled"):
                break

        # Get agent response
        messages = store.get_messages(session_id, limit=20)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        if assistant_msgs:
            reply = assistant_msgs[-1].content
            if len(reply) > 5000:
                reply = reply[:5000] + "\n...(内容过长已截断)"
            reply_message(message_id, reply)
        else:
            reply_message(message_id, "分析完成，但未生成回复。请检查 Orange Trade 网页。")

    except Exception as e:
        logger.error("Agent reply failed: %s", e)
        try:
            reply_message(message_id, f"分析过程出错：{str(e)[:200]}")
        except Exception:
            pass
