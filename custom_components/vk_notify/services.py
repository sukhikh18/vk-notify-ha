"""Services for VK Notify integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from .const import (
    CONF_CONFIG_ENTRY_ID,
    CONF_RECIPIENT_ID,
    DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from .notify import async_send_plain_message
from .schemas import SERVICE_SEND_MESSAGE_SCHEMA

_LOGGER = logging.getLogger(__name__)


def register_send_message_service(hass: HomeAssistant) -> None:
    """Register vk_notify.send_message service (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_MESSAGE):
        return
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MESSAGE,
        async_send_message_handler,
        schema=SERVICE_SEND_MESSAGE_SCHEMA,
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
