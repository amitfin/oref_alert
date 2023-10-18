"""Config flow for oref_alert integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .areas import AREAS
from .const import CONF_AREAS, CONF_ALERT_MAX_AGE, DEFAULT_ALERT_MAX_AGE, DOMAIN

AREAS_CONFIG = selector.SelectSelectorConfig(
    options=AREAS,
    mode=selector.SelectSelectorMode.DROPDOWN,
    multiple=True,
    custom_value=True,
    sort=True,
)
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_AREAS): selector.SelectSelector(AREAS_CONFIG),
        vol.Required(
            CONF_ALERT_MAX_AGE, default=DEFAULT_ALERT_MAX_AGE
        ): cv.positive_int,
    }
)


def _get_selected_ares(user_input: dict[str, Any]):
    """Read and normalize the list of selected areas."""
    return [area.strip() for area in user_input.get(CONF_AREAS, [])]


class RetryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title=DOMAIN.replace("_", " ").title(),
                data={},
                options={
                    CONF_AREAS: _get_selected_ares(user_input),
                    CONF_ALERT_MAX_AGE: user_input.get(
                        CONF_ALERT_MAX_AGE, DEFAULT_ALERT_MAX_AGE
                    ),
                },
            )

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle an options flow."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_AREAS: _get_selected_ares(user_input),
                    CONF_ALERT_MAX_AGE: user_input.get(
                        CONF_ALERT_MAX_AGE, DEFAULT_ALERT_MAX_AGE
                    ),
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AREAS, default=self._config_entry.options[CONF_AREAS]
                    ): selector.SelectSelector(AREAS_CONFIG),
                    vol.Required(
                        CONF_ALERT_MAX_AGE,
                        default=self._config_entry.options[CONF_ALERT_MAX_AGE],
                    ): cv.positive_int,
                }
            ),
        )
