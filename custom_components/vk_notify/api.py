"""Calls to VK API."""

from __future__ import annotations

import json
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


def _build_keyboard(buttons: list[list[dict[str, Any]]]) -> str:
    """Build VK inline keyboard JSON string from buttons."""
    rows: list[list[dict[str, Any]]] = []
    for row in buttons:
        api_row: list[dict[str, Any]] = []
        for btn in row:
            if not isinstance(btn, dict):
                continue
            label = str(btn.get("text", "")).strip()
            command = btn.get("command")
            if not label:
                continue
            if not command:
                command = label
            payload = json.dumps({"command": command}, ensure_ascii=False)
            action = {
                "type": "callback",
                "label": label,
                "payload": payload,
            }
            api_btn: dict[str, Any] = {"action": action}
            color = btn.get("color")
            if color:
                api_btn["color"] = str(color)
            api_row.append(api_btn)
        if api_row:
            rows.append(api_row)
    keyboard = {
        "inline": True,
        "buttons": rows,
    }
    return json.dumps(keyboard, ensure_ascii=False)


async def answer_message_event(
    hass: HomeAssistant,
    token: str,
    event_id: str,
    user_id: int,
    peer_id: int,
    text: str | None = None,
) -> None:
    """Answer message_event to stop spinner in VK client."""
    event_data = {"type": "show_snackbar", "text": text or "OK"}
    body = await _vk_api_call(
        hass,
        token,
        "messages.sendMessageEventAnswer",
        {
            "event_id": event_id,
            "user_id": int(user_id),
            "peer_id": int(peer_id),
            "event_data": json.dumps(event_data, ensure_ascii=False),
        },
    )
    if "error" in body:
        error = body["error"]
        _LOGGER.warning(
            "VK sendMessageEventAnswer failed: code=%s msg=%s",
            error.get("error_code"),
            error.get("error_msg"),
        )


async def send_message(
    hass: HomeAssistant,
    token: str,
    peer_id: int,
    message: str,
    buttons: list[list[dict[str, Any]]] | None = None,
) -> None:
    """Send plain text message via messages.send (optionally with inline buttons)."""
    text = message[:4000]
    params: dict[str, Any] = {
        "peer_id": int(peer_id),
        "random_id": random.randint(1, 2_147_483_647),
        "message": text,
    }
    if buttons:
        params["keyboard"] = _build_keyboard(buttons)
    body = await _vk_api_call(
        hass,
        token,
        "messages.send",
        params,
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
    buttons: list[list[dict[str, Any]]] | None = None,
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
    params: dict[str, Any] = {
        "peer_id": int(peer_id),
        "random_id": random.randint(1, 2_147_483_647),
        "message": message_text,
        "attachment": attachment,
    }
    if buttons:
        params["keyboard"] = _build_keyboard(buttons)
    send_resp = await _vk_api_call(
        hass,
        token,
        "messages.send",
        params,
    )
    if "error" in send_resp:
        error = send_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )


async def send_document(
    hass: HomeAssistant,
    token: str,
    peer_id: int,
    file: str,
    caption: str | None = None,
    buttons: list[list[dict[str, Any]]] | None = None,
) -> None:
    """Upload file and send it to VK peer as document."""
    source = file.strip()
    if source.startswith(("http://", "https://")):
        raw, filename, content_type = await _read_remote_file(hass, source)
    else:
        raw, filename, content_type = await _read_local_file(hass, source)
    if not raw:
        raise RuntimeError("Document payload is empty")

    upload_server_resp = await _vk_api_call(
        hass,
        token,
        "docs.getMessagesUploadServer",
        {"peer_id": int(peer_id)},
    )
    if "error" in upload_server_resp:
        error = upload_server_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )

    upload_url = (upload_server_resp.get("response") or {}).get("upload_url")
    if not upload_url:
        raise RuntimeError("VK docs upload URL is missing")

    session = async_get_clientsession(hass)
    form = aiohttp.FormData()
    form.add_field("file", raw, filename=filename, content_type=content_type)
    async with session.post(
        upload_url,
        data=form,
        timeout=aiohttp.ClientTimeout(total=180),
    ) as upload_resp:
        if upload_resp.status >= 400:
            body = await upload_resp.text()
            raise RuntimeError(
                f"VK video upload failed: status={upload_resp.status}, body={body[:200]}"
            )
        upload_body = await upload_resp.json(content_type=None)
    upload_file = upload_body.get("file")
    if not upload_file:
        raise RuntimeError("VK docs upload response has no file token")

    docs_save_resp = await _vk_api_call(
        hass,
        token,
        "docs.save",
        {"file": upload_file, "title": filename},
    )
    if "error" in docs_save_resp:
        error = docs_save_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )
    docs_response = docs_save_resp.get("response")
    doc_obj: dict[str, Any] | None = None
    if isinstance(docs_response, dict):
        if isinstance(docs_response.get("doc"), dict):
            doc_obj = docs_response["doc"]
        elif isinstance(docs_response.get("docs"), list) and docs_response["docs"]:
            first = docs_response["docs"][0]
            if isinstance(first, dict):
                doc_obj = first
    elif isinstance(docs_response, list) and docs_response:
        first = docs_response[0]
        if isinstance(first, dict):
            doc_obj = first

    if not doc_obj:
        raise RuntimeError("VK docs.save returned empty response")

    owner_id = doc_obj.get("owner_id")
    doc_id = doc_obj.get("id")
    access_key = doc_obj.get("access_key")
    if owner_id is None or doc_id is None:
        raise RuntimeError("VK document attachment fields are missing")
    attachment = f"doc{owner_id}_{doc_id}"
    if access_key:
        attachment = f"{attachment}_{access_key}"

    params: dict[str, Any] = {
        "peer_id": int(peer_id),
        "random_id": random.randint(1, 2_147_483_647),
        "message": (caption or "")[:4000],
        "attachment": attachment,
    }
    if buttons:
        params["keyboard"] = _build_keyboard(buttons)
    send_resp = await _vk_api_call(
        hass,
        token,
        "messages.send",
        params,
    )
    if "error" in send_resp:
        error = send_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )


async def send_video(
    hass: HomeAssistant,
    token: str,
    peer_id: int,
    file: str,
    video_access_token: str,
    caption: str | None = None,
) -> None:
    """Upload video and send native VK video attachment."""
    source = file.strip()
    if source.startswith(("http://", "https://")):
        raw, filename, content_type = await _read_remote_file(hass, source)
    else:
        raw, filename, content_type = await _read_local_file(hass, source)
    if not raw:
        raise RuntimeError("Video payload is empty")

    user_video_token = video_access_token.strip()
    if not user_video_token:
        raise RuntimeError("video_access_token is required")

    video_save_resp = await _vk_api_call(
        hass,
        user_video_token,
        "video.save",
        {
            "name": filename,
            "description": (caption or "")[:4000],
            "is_private": 0,
        },
    )
    if "error" in video_save_resp:
        error = video_save_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )
    saved = video_save_resp.get("response")
    if not isinstance(saved, dict):
        raise RuntimeError("VK video.save returned invalid response")
    upload_url = saved.get("upload_url")
    owner_id = saved.get("owner_id")
    video_id = saved.get("video_id") or saved.get("id")
    access_key = saved.get("access_key")
    if not upload_url or owner_id is None or video_id is None:
        raise RuntimeError("VK video.save missing upload_url/owner_id/video_id")

    session = async_get_clientsession(hass)
    form = aiohttp.FormData()
    form.add_field("video_file", raw, filename=filename, content_type=content_type)
    async with session.post(
        upload_url,
        data=form,
        timeout=aiohttp.ClientTimeout(total=300),
    ) as upload_resp:
        if upload_resp.status >= 400:
            body = await upload_resp.text()
            raise RuntimeError(
                f"VK video upload failed: status={upload_resp.status}, body={body[:200]}"
            )
        await upload_resp.read()

    attachment = f"video{owner_id}_{video_id}"
    if access_key:
        attachment = f"{attachment}_{access_key}"
    send_resp = await _vk_api_call(
        hass,
        token,
        "messages.send",
        {
            "peer_id": int(peer_id),
            "random_id": random.randint(1, 2_147_483_647),
            "message": (caption or "")[:4000],
            "attachment": attachment,
        },
    )
    if "error" in send_resp:
        error = send_resp["error"]
        raise RuntimeError(
            f"VK API error {error.get('error_code')}: {error.get('error_msg')}"
        )
