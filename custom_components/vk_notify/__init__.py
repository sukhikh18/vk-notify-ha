"""The VK Notify integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_RECEIVE_MODE,
    DOMAIN,
    RECEIVE_MODE_WEBHOOK,
)
from .services import register_send_message_service
from .webhook import VkNotifyWebhookView

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.NOTIFY]


def _ensure_webhook_view_registered(hass: HomeAssistant) -> None:
    """Register webhook view once (idempotent)."""
    if getattr(_ensure_webhook_view_registered, "_registered", False):
        return
    hass.http.register_view(VkNotifyWebhookView())
    _ensure_webhook_view_registered._registered = True


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the VK Notify component."""
    register_send_message_service(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VK Notify from a config entry."""
    register_send_message_service(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    if (entry.options or {}).get(CONF_RECEIVE_MODE) == RECEIVE_MODE_WEBHOOK:
        _ensure_webhook_view_registered(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("VK Notify setup entry: %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options/data are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
