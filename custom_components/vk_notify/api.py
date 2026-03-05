"""Calls to VK API."""

from __future__ import annotations

import logging
import random
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    VK_API_BASE_URL,
    VK_API_VERSION,
)

_LOGGER = logging.getLogger(__name__)


async def _vk_api_call(
    hass: HomeAssistant,
    token: str,
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Call VK API method and return decoded JSON object."""
    url = f"{VK_API_BASE_URL}/{method}"
    data = {**params, "access_token": token, "v": VK_API_VERSION}
    session = async_get_clientsession(hass)
    async with session.post(
        url,
        data=data,
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        body = await resp.json(content_type=None)
    return body


async def validate_token(hass: HomeAssistant, token: str, group_id: int) -> str | None:
    """Validate VK group token by calling groups.getById."""
    if not token:
        return "invalid_token"
    try:
        body = await _vk_api_call(
            hass,
            token,
            "groups.getById",
            {"group_id": group_id},
        )
    except (aiohttp.ClientError, ValueError) as err:
        _LOGGER.warning("VK token validation failed: %s", err)
        return "cannot_connect"

    if "error" in body:
        code = body["error"].get("error_code")
        msg = body["error"].get("error_msg")
        _LOGGER.warning(
            "VK token validation API error: code=%s message=%s group_id=%s",
            code,
            msg,
            group_id,
        )
        if code in {5, 27, 28}:
            return "invalid_auth"
        if code == 100:
            return "invalid_group_id"
        return "cannot_connect"

    response = body.get("response")
    if isinstance(response, list):
        if not response:
            return "cannot_connect"
        return None
    if isinstance(response, dict):
        groups = response.get("groups")
        if isinstance(groups, list) and groups:
            return None
        return "cannot_connect"
    return "cannot_connect"


async def send_message(
    hass: HomeAssistant,
    token: str,
    peer_id: int,
    message: str,
) -> None:
    """Send plain text message via messages.send."""
    text = message[:4000]
    body = await _vk_api_call(
        hass,
        token,
        "messages.send",
        {
            "peer_id": int(peer_id),
            "random_id": random.randint(1, 2_147_483_647),
            "message": text,
        },
    )
    if "error" in body:
        error = body["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )
