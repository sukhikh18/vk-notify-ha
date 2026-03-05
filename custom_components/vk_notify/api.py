"""Calls to VK API."""

from __future__ import annotations

import logging
import mimetypes
import os
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


def _guess_content_type(filename: str) -> str:
    """Guess content type from file name."""
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or "image/jpeg"


async def _read_local_file(hass: HomeAssistant, path: str) -> tuple[bytes, str, str]:
    """Read local file from absolute path or path relative to HA config dir."""
    resolved = path
    if not os.path.isabs(resolved):
        resolved = os.path.join(hass.config.config_dir, resolved)

    def _read() -> bytes:
        with open(resolved, "rb") as file:
            return file.read()

    body = await hass.async_add_executor_job(_read)
    filename = os.path.basename(resolved) or "photo.jpg"
    return body, filename, _guess_content_type(filename)


async def _read_remote_file(
    hass: HomeAssistant, file_url: str
) -> tuple[bytes, str, str]:
    """Download file by URL."""
    session = async_get_clientsession(hass)
    async with session.get(
        file_url, timeout=aiohttp.ClientTimeout(total=45)
    ) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"Failed to download file, status={resp.status}")
        body = await resp.read()
        raw_content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    filename = os.path.basename(file_url.split("?", 1)[0]) or "photo.jpg"
    content_type = raw_content_type or _guess_content_type(filename)
    return body, filename, content_type


async def send_photo(
    hass: HomeAssistant,
    token: str,
    peer_id: int,
    file: str,
    caption: str | None = None,
) -> None:
    """Upload image and send it to VK peer."""
    upload_server_resp = await _vk_api_call(
        hass,
        token,
        "photos.getMessagesUploadServer",
        {"peer_id": int(peer_id)},
    )
    if "error" in upload_server_resp:
        error = upload_server_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )

    upload_url = (upload_server_resp.get("response") or {}).get("upload_url")
    if not upload_url:
        raise RuntimeError("VK upload URL is missing")

    source = file.strip()
    if source.startswith(("http://", "https://")):
        raw, filename, content_type = await _read_remote_file(hass, source)
    else:
        raw, filename, content_type = await _read_local_file(hass, source)
    if not raw:
        raise RuntimeError("Photo payload is empty")

    session = async_get_clientsession(hass)
    form = aiohttp.FormData()
    form.add_field("photo", raw, filename=filename, content_type=content_type)
    async with session.post(
        upload_url,
        data=form,
        timeout=aiohttp.ClientTimeout(total=60),
    ) as upload_resp:
        upload_body = await upload_resp.json(content_type=None)

    if "error" in upload_body:
        error = upload_body["error"]
        raise RuntimeError(
            f"VK upload error {error.get('error_code')}: {error.get('error_msg')}"
        )

    saved_photo_resp = await _vk_api_call(
        hass,
        token,
        "photos.saveMessagesPhoto",
        {
            "photo": upload_body.get("photo"),
            "server": upload_body.get("server"),
            "hash": upload_body.get("hash"),
        },
    )
    if "error" in saved_photo_resp:
        error = saved_photo_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )

    photos = saved_photo_resp.get("response")
    if not isinstance(photos, list) or not photos:
        raise RuntimeError("VK saveMessagesPhoto returned empty response")
    photo = photos[0]
    owner_id = photo.get("owner_id")
    photo_id = photo.get("id")
    access_key = photo.get("access_key")
    if owner_id is None or photo_id is None:
        raise RuntimeError("VK photo attachment fields are missing")

    attachment = f"photo{owner_id}_{photo_id}"
    if access_key:
        attachment = f"{attachment}_{access_key}"

    message_text = (caption or "")[:4000]
    send_resp = await _vk_api_call(
        hass,
        token,
        "messages.send",
        {
            "peer_id": int(peer_id),
            "random_id": random.randint(1, 2_147_483_647),
            "message": message_text,
            "attachment": attachment,
        },
    )
    if "error" in send_resp:
        error = send_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )
