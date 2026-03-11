"""Services for VK Notify integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CONFIG_ENTRY_ID,
    CONF_RECIPIENT_ID,
    DOMAIN,
    SERVICE_SEND_DOCUMENT,
    SERVICE_SEND_MESSAGE,
    SERVICE_SEND_PHOTO,
    SERVICE_SEND_VIDEO,
)
from .notify import async_send_plain_message
from .api import send_document, send_message, send_photo, send_video

try:
    import yaml
except Exception:  # pragma: no cover - fallback if yaml missing
    yaml = None
from .schemas import (
    SERVICE_SEND_DOCUMENT_SCHEMA,
    SERVICE_SEND_MESSAGE_SCHEMA,
    SERVICE_SEND_PHOTO_SCHEMA,
    SERVICE_SEND_VIDEO_SCHEMA,
)

_LOGGER = logging.getLogger(__name__)


def register_send_message_service(hass: HomeAssistant) -> None:
    """Register vk_notify services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        pass
    else:
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_MESSAGE,
            async_send_message_handler,
            schema=SERVICE_SEND_MESSAGE_SCHEMA,
        )
    if hass.services.has_service(DOMAIN, SERVICE_SEND_PHOTO):
        pass
    else:
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_PHOTO,
            async_send_photo_handler,
            schema=SERVICE_SEND_PHOTO_SCHEMA,
        )
    if hass.services.has_service(DOMAIN, SERVICE_SEND_DOCUMENT):
        pass
    else:
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_DOCUMENT,
            async_send_document_handler,
            schema=SERVICE_SEND_DOCUMENT_SCHEMA,
        )
    if hass.services.has_service(DOMAIN, SERVICE_SEND_VIDEO):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_VIDEO,
        async_send_video_handler,
        schema=SERVICE_SEND_VIDEO_SCHEMA,
    )


def _resolve_entry(hass: HomeAssistant, config_entry_id: str | None) -> ConfigEntry:
    """Resolve config entry from id or single existing entry."""
    if config_entry_id:
        entry = hass.config_entries.async_get_entry(config_entry_id)
        if entry and entry.domain == DOMAIN:
            return entry
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_config_entry",
            translation_placeholders={"config_entry_id": config_entry_id},
        )

    entries = hass.config_entries.async_entries(DOMAIN)
    if len(entries) == 1:
        return entries[0]
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="missing_config_entry_id",
    )


async def async_send_message_handler(service: ServiceCall) -> None:
    """Handle vk_notify.send_message."""
    hass = service.hass
    data = service.data
    entry = _resolve_entry(hass, data.get(CONF_CONFIG_ENTRY_ID))

    recipient_id = data.get(CONF_RECIPIENT_ID, entry.data.get(CONF_RECIPIENT_ID))
    if recipient_id in (None, 0):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    try:
        buttons = data.get("buttons")
        if isinstance(buttons, str):
            if yaml is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_buttons",
                )
            try:
                buttons = yaml.safe_load(buttons)
            except Exception as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_buttons",
                    translation_placeholders={"reason": str(err)},
                ) from err
            if buttons is None:
                buttons = []
        if buttons and not isinstance(buttons, list):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_buttons",
            )
        if buttons:
            text = f"{data.get('title')}\n{data['message']}" if data.get("title") else data["message"]
            if not str(text).strip():
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="empty_message",
                )
            token = str(entry.data.get(CONF_ACCESS_TOKEN, "")).strip()
            if not token:
                raise RuntimeError("No VK token in config entry")
            await send_message(
                hass,
                token=token,
                peer_id=int(recipient_id),
                message=text,
                buttons=buttons,
            )
        else:
            if not str(data.get("message", "")).strip():
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="empty_message",
                )
            await async_send_plain_message(
                hass,
                entry,
                int(recipient_id),
                data["message"],
                title=data.get("title"),
            )
    except RuntimeError as err:
        _LOGGER.error("VK send message failed: %s", err)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_failed",
            translation_placeholders={"reason": str(err)},
        ) from err


async def async_send_photo_handler(service: ServiceCall) -> None:
    """Handle vk_notify.send_photo."""
    hass = service.hass
    data = service.data
    entry = _resolve_entry(hass, data.get(CONF_CONFIG_ENTRY_ID))

    recipient_id = data.get(CONF_RECIPIENT_ID, entry.data.get(CONF_RECIPIENT_ID))
    if recipient_id in (None, 0):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    token = str(entry.data.get(CONF_ACCESS_TOKEN, "")).strip()
    if not token:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_photo_failed",
            translation_placeholders={"reason": "No VK token in config entry"},
        )

    try:
        await send_photo(
            hass,
            token=token,
            peer_id=int(recipient_id),
            file=data["file"],
            caption=data.get("caption"),
        )
    except (RuntimeError, OSError) as err:
        _LOGGER.error("VK send photo failed: %s", err)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_photo_failed",
            translation_placeholders={"reason": str(err)},
        ) from err


async def async_send_video_handler(service: ServiceCall) -> None:
    """Handle vk_notify.send_video."""
    hass = service.hass
    data = service.data
    entry = _resolve_entry(hass, data.get(CONF_CONFIG_ENTRY_ID))

    recipient_id = data.get(CONF_RECIPIENT_ID, entry.data.get(CONF_RECIPIENT_ID))
    if recipient_id in (None, 0):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    token = str(entry.data.get(CONF_ACCESS_TOKEN, "")).strip()
    if not token:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_video_failed",
            translation_placeholders={"reason": "No VK token in config entry"},
        )

    try:
        await send_video(
            hass,
            token=token,
            peer_id=int(recipient_id),
            file=data["file"],
            caption=data.get("caption"),
            video_access_token=data["video_access_token"],
        )
    except (RuntimeError, OSError) as err:
        _LOGGER.error("VK send video failed: %s", err)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_video_failed",
            translation_placeholders={"reason": str(err)},
        ) from err


async def async_send_document_handler(service: ServiceCall) -> None:
    """Handle vk_notify.send_document."""
    hass = service.hass
    data = service.data
    entry = _resolve_entry(hass, data.get(CONF_CONFIG_ENTRY_ID))

    recipient_id = data.get(CONF_RECIPIENT_ID, entry.data.get(CONF_RECIPIENT_ID))
    if recipient_id in (None, 0):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

    token = str(entry.data.get(CONF_ACCESS_TOKEN, "")).strip()
    if not token:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_document_failed",
            translation_placeholders={"reason": "No VK token in config entry"},
        )

    try:
        await send_document(
            hass,
            token=token,
            peer_id=int(recipient_id),
            file=data["file"],
            caption=data.get("caption"),
        )
    except (RuntimeError, OSError) as err:
        _LOGGER.error("VK send document failed: %s", err)
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="send_document_failed",
            translation_placeholders={"reason": str(err)},
        ) from err
