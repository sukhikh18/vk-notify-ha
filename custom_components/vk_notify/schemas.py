"""Voluptuous schemas for VK Notify services."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CONFIG_ENTRY_ID,
    CONF_RECIPIENT_ID,
)

SERVICE_SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("title"): cv.string,
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_RECIPIENT_ID): vol.Coerce(int),
    }
)

SERVICE_SEND_PHOTO_SCHEMA = vol.Schema(
    {
        vol.Required("file"): cv.string,
        vol.Optional("caption"): cv.string,
        vol.Optional(CONF_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(CONF_RECIPIENT_ID): vol.Coerce(int),
    }
)
