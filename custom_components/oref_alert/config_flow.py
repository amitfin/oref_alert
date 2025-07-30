"""Config flow for oref_alert integration."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import async_get_hass, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .metadata import ALL_AREAS_ALIASES

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

from .const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREAS,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DOMAIN,
    TITLE,
)
from .metadata.area_to_polygon import async_find_area
from .metadata.areas_and_groups import AREAS_AND_GROUPS

AREAS_CONFIG = selector.SelectSelectorConfig(
    options=[area for area in AREAS_AND_GROUPS if area not in ALL_AREAS_ALIASES],
    mode=selector.SelectSelectorMode.DROPDOWN,
    multiple=True,
    custom_value=False,
)
CONFIG_SCHEMA = vol.Schema(
    {vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG)}
)


class OrefAlertConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    def __init__(self) -> None:
        """Initialize object with defaults."""
        self._auto_detected_area: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return await self.async_step_confirm(user_input)

        hass = None
        with contextlib.suppress(HomeAssistantError):
            hass = async_get_hass()
        if hass:
            self._auto_detected_area = (
                await async_find_area(hass.config.latitude, hass.config.longitude) or ""
            )

        if not self._auto_detected_area:
            return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

        return await self.async_step_confirm(None)

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup."""
        if user_input is not None:
            return self.async_create_entry(
                title=TITLE,
                data={},
                options={
                    CONF_AREAS: user_input.get(CONF_AREAS, [self._auto_detected_area]),
                    CONF_ALERT_ACTIVE_DURATION: DEFAULT_ALERT_ACTIVE_DURATION,
                    CONF_ALL_ALERTS_ATTRIBUTES: False,
                },
            )
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"area": self._auto_detected_area},
        )

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

    async def async_step_init(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Handle an options flow."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={**self._config_entry.options, **user_input},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AREAS, default=self._config_entry.options[CONF_AREAS]
                    ): selector.SelectSelector(AREAS_CONFIG),
                    vol.Required(
                        CONF_ALERT_ACTIVE_DURATION,
                        default=self._config_entry.options[CONF_ALERT_ACTIVE_DURATION],
                    ): cv.positive_int,
                    vol.Required(
                        CONF_ALL_ALERTS_ATTRIBUTES,
                        default=self._config_entry.options.get(
                            CONF_ALL_ALERTS_ATTRIBUTES, False
                        ),
                    ): selector.BooleanSelector(),
                }
            ),
        )
