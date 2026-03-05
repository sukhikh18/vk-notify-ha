"""Notify platform for VK Notify integration."""

from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import send_message
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_RECIPIENT_ID,
    DOMAIN,
    MAX_MESSAGE_LENGTH,
)

_LOGGER = logging.getLogger(__name__)


async def async_send_plain_message(
    hass: HomeAssistant,
    entry: ConfigEntry,
    recipient_id: int,
    message: str,
    title: str | None = None,
) -> None:
    """Send plain text message to peer_id."""
    token = str(entry.data.get(CONF_ACCESS_TOKEN, "")).strip()
    if not token:
        raise RuntimeError("No VK token in config entry")

    text = f"{title}\n{message}" if title else message
    if len(text) > MAX_MESSAGE_LENGTH:
        _LOGGER.warning(
            "Message truncated from %d to %d characters",
            len(text),
            MAX_MESSAGE_LENGTH,
        )
        text = text[:MAX_MESSAGE_LENGTH]

    await send_message(hass, token, int(recipient_id), text)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VK notify entity for one default recipient."""
    recipient_id = int(entry.data.get(CONF_RECIPIENT_ID, 0))
    if recipient_id == 0:
        return
    async_add_entities([VkNotifyEntity(entry, recipient_id)])


class VkNotifyEntity(NotifyEntity):
    """Representation of VK Notify entity."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry: ConfigEntry, recipient_id: int) -> None:
        """Initialize entity."""
        self._entry = entry
        self._recipient_id = recipient_id
        self._attr_unique_id = f"{entry.entry_id}_{recipient_id}"
        self._attr_name = f"Peer {recipient_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
        )
        self._attr_extra_state_attributes = {
            "recipient_id": recipient_id,
            "integration_config_path": f"/config/integrations/integration/{entry.entry_id}",
        }

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send message through VK API."""
        await async_send_plain_message(
            self.hass,
            self._entry,
            self._recipient_id,
            message,
            title=title,
        )
