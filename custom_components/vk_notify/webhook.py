"""Webhook endpoint for receiving VK Callback API updates."""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_CONFIRMATION_CODE,
    CONF_GROUP_ID,
    CONF_RECEIVE_MODE,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    EVENT_VK_NOTIFY_RECEIVED,
    RECEIVE_MODE_WEBHOOK,
    VK_WEBHOOK_PATH_PREFIX,
)


def get_webhook_url_path(entry: ConfigEntry) -> str:
    """Return webhook path for one config entry."""
    return f"{VK_WEBHOOK_PATH_PREFIX}/{entry.entry_id}"


def _event_data(entry: ConfigEntry, payload: dict[str, Any]) -> dict[str, Any]:
    """Build event payload for HA bus."""
    update_type = payload.get("type")
    obj = payload.get("object") or {}
    message = obj.get("message") if isinstance(obj, dict) else {}
    if not isinstance(message, dict):
        message = {}

    data = {
        "config_entry_id": entry.entry_id,
        "update_type": update_type,
        "peer_id": message.get("peer_id") or obj.get("peer_id"),
        "from_id": message.get("from_id") or obj.get("user_id"),
        "text": message.get("text"),
        "payload": message.get("payload") or obj.get("payload"),
        "conversation_message_id": message.get("conversation_message_id"),
        "event_id": obj.get("event_id"),
    }
    if isinstance(data["payload"], str):
        try:
            data["payload"] = json.loads(data["payload"])
        except json.JSONDecodeError:
            pass
    return {k: v for k, v in data.items() if v is not None}


class VkNotifyWebhookView(HomeAssistantView):
    """HTTP view for VK callback."""

    url = f"{VK_WEBHOOK_PATH_PREFIX}/{{entry_id}}"
    name = "api:vk_notify:webhook"
    requires_auth = False

    async def post(self, request: web.Request) -> web.Response:
        """Handle webhook callback from VK."""
        entry_id = request.match_info.get("entry_id")
        hass = request.app["hass"]
        entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if not entry or entry.domain != DOMAIN:
            return web.Response(status=404, text="not found")

        options = entry.options or {}
        if options.get(CONF_RECEIVE_MODE) != RECEIVE_MODE_WEBHOOK:
            return web.Response(status=404, text="webhook not enabled")

        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")

        if not isinstance(body, dict):
            return web.Response(status=400, text="body must be object")

        group_id = body.get("group_id")
        if int(group_id or 0) != int(entry.data.get(CONF_GROUP_ID, 0)):
            return web.Response(status=403, text="wrong group")

        expected_secret = (options.get(CONF_WEBHOOK_SECRET) or "").strip()
        received_secret = (body.get("secret") or "").strip()
        if expected_secret and expected_secret != received_secret:
            return web.Response(status=401, text="wrong secret")

        update_type = body.get("type")
        if update_type == "confirmation":
            confirmation = (options.get(CONF_CONFIRMATION_CODE) or "").strip() or "ok"
            return web.Response(status=200, text=confirmation)

        if update_type in {"message_new", "message_event"}:
            hass.bus.async_fire(EVENT_VK_NOTIFY_RECEIVED, _event_data(entry, body))

        return web.Response(status=200, text="ok")
