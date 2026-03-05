"""Config flow for VK Notify integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import validate_token
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CONFIRMATION_CODE,
    CONF_GROUP_ID,
    CONF_RECEIVE_MODE,
    CONF_RECIPIENT_ID,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    RECEIVE_MODE_SEND_ONLY,
    RECEIVE_MODE_WEBHOOK,
)


class VkNotifyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VK Notify."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            group_id = int(user_input[CONF_GROUP_ID])
            recipient_id = int(user_input[CONF_RECIPIENT_ID])
            receive_mode = user_input[CONF_RECEIVE_MODE]
            webhook_secret = (user_input.get(CONF_WEBHOOK_SECRET) or "").strip()
            confirmation_code = (user_input.get(CONF_CONFIRMATION_CODE) or "").strip()

            if recipient_id == 0:
                errors["base"] = "invalid_id_format"
            else:
                err = await validate_token(self.hass, token, group_id)
                if err:
                    errors["base"] = err
                else:
                    await self.async_set_unique_id(f"{DOMAIN}_{group_id}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"VK Notify ({group_id})",
                        data={
                            CONF_ACCESS_TOKEN: token,
                            CONF_GROUP_ID: group_id,
                            CONF_RECIPIENT_ID: recipient_id,
                        },
                        options={
                            CONF_RECEIVE_MODE: receive_mode,
                            CONF_WEBHOOK_SECRET: webhook_secret,
                            CONF_CONFIRMATION_CODE: confirmation_code,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Required(CONF_GROUP_ID): vol.Coerce(int),
                    vol.Required(CONF_RECIPIENT_ID): vol.Coerce(int),
                    vol.Required(CONF_RECEIVE_MODE, default=RECEIVE_MODE_SEND_ONLY): vol.In(
                        [RECEIVE_MODE_SEND_ONLY, RECEIVE_MODE_WEBHOOK]
                    ),
                    vol.Optional(CONF_WEBHOOK_SECRET, default=""): str,
                    vol.Optional(CONF_CONFIRMATION_CODE, default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> VkNotifyOptionsFlow:
        """Return options flow."""
        return VkNotifyOptionsFlow(entry)


class VkNotifyOptionsFlow(OptionsFlow):
    """Handle options flow for VK Notify."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage VK Notify options."""
        if user_input is not None:
            data = dict(self.entry.data)
            token_input = (user_input.get(CONF_ACCESS_TOKEN) or "").strip()
            group_id = int(user_input[CONF_GROUP_ID])
            recipient_id = int(user_input[CONF_RECIPIENT_ID])
            if recipient_id == 0:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": "invalid_id_format"},
                )

            token = token_input or data.get(CONF_ACCESS_TOKEN, "")
            err = await validate_token(self.hass, token, group_id)
            if err:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._schema(user_input),
                    errors={"base": err},
                )

            data[CONF_GROUP_ID] = group_id
            data[CONF_RECIPIENT_ID] = recipient_id
            if token_input:
                data[CONF_ACCESS_TOKEN] = token_input

            self.hass.config_entries.async_update_entry(self.entry, data=data)
            return self.async_create_entry(
                data={
                    CONF_RECEIVE_MODE: user_input[CONF_RECEIVE_MODE],
                    CONF_WEBHOOK_SECRET: (user_input.get(CONF_WEBHOOK_SECRET) or "").strip(),
                    CONF_CONFIRMATION_CODE: (user_input.get(CONF_CONFIRMATION_CODE) or "").strip(),
                }
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(),
        )

    def _schema(self, user_input: dict[str, Any] | None = None) -> vol.Schema:
        """Build options schema."""
        opts = self.entry.options or {}
        data = self.entry.data
        suggested = user_input or {}
        return vol.Schema(
            {
                vol.Optional(CONF_ACCESS_TOKEN, default=suggested.get(CONF_ACCESS_TOKEN, "")): str,
                vol.Required(CONF_GROUP_ID, default=suggested.get(CONF_GROUP_ID, data.get(CONF_GROUP_ID, 0))): vol.Coerce(int),
                vol.Required(
                    CONF_RECIPIENT_ID,
                    default=suggested.get(CONF_RECIPIENT_ID, data.get(CONF_RECIPIENT_ID, 0)),
                ): vol.Coerce(int),
                vol.Required(
                    CONF_RECEIVE_MODE,
                    default=suggested.get(CONF_RECEIVE_MODE, opts.get(CONF_RECEIVE_MODE, RECEIVE_MODE_SEND_ONLY)),
                ): vol.In([RECEIVE_MODE_SEND_ONLY, RECEIVE_MODE_WEBHOOK]),
                vol.Optional(
                    CONF_WEBHOOK_SECRET,
                    default=suggested.get(CONF_WEBHOOK_SECRET, opts.get(CONF_WEBHOOK_SECRET, "")),
                ): str,
                vol.Optional(
                    CONF_CONFIRMATION_CODE,
                    default=suggested.get(CONF_CONFIRMATION_CODE, opts.get(CONF_CONFIRMATION_CODE, "")),
                ): str,
            }
        )
