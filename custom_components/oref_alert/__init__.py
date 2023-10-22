"""Oref Alert Integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import SOURCE_USER, ConfigEntry
from homeassistant.components.template.const import DOMAIN as TEMPLATE_DOMAIN
from homeassistant.const import CONF_NAME, CONF_STATE, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import selector
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.schema_config_entry_flow import SchemaConfigFlowHandler

from .area_utils import expand_areas_and_groups
from .const import (
    ADD_SENSOR_SERVICE,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    CONF_AREAS,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
    TITLE,
)
from .config_flow import AREAS_CONFIG

ADD_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)


def _compose_template(areas: list[str]) -> str:
    """Compose template for list of areas."""
    areas.sort()
    template = f"""
        {'{{'}
            [areas] |
            select('in', (
                state_attr(
                    '{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}',
                    '{ATTR_COUNTRY_ACTIVE_ALERTS}'
                )
                | map(attribute='data')
            ))
            | list | length > 0
        {'}}'}
        """
    for token, replace in (("\n", ""), (" ", ""), ("[areas]", str(areas))):
        template = template.replace(token, replace)
    return template


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entity from a config entry."""
    await hass.config_entries.async_forward_entry_setups(
        entry, (Platform.BINARY_SENSOR,)
    )
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    async def add_sensor(service_call: ServiceCall) -> None:
        """Add an additional sensor (different areas)."""
        await hass.config_entries.async_add(
            ConfigEntry(
                SchemaConfigFlowHandler.VERSION,
                TEMPLATE_DOMAIN,
                f"{TITLE} {service_call.data[CONF_NAME]}",
                {},
                SOURCE_USER,
                options={
                    "template_type": Platform.BINARY_SENSOR,
                    CONF_NAME: f"{TITLE} {service_call.data[CONF_NAME]}",
                    CONF_STATE: _compose_template(
                        expand_areas_and_groups(service_call.data[CONF_AREAS])
                    ),
                },
            )
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        ADD_SENSOR_SERVICE,
        add_sensor,
        ADD_SENSOR_SCHEMA,
    )

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.services.async_remove(DOMAIN, ADD_SENSOR_SERVICE)
    return await hass.config_entries.async_unload_platforms(
        entry, (Platform.BINARY_SENSOR,)
    )
