"""Oref Alert Integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry, selector
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    ADD_SENSOR_SERVICE,
    REMOVE_SENSOR_SERVICE,
    CONF_AREAS,
    CONF_POLL_INTERVAL,
    CONF_SENSORS,
    DATA_COORDINATOR,
    DOMAIN,
    DEFAULT_POLL_INTERVAL,
    TITLE,
)
from .config_flow import AREAS_CONFIG
from .coordinator import OrefAlertDataUpdateCoordinator

ADD_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)

REMOVE_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(
                exclude_entities=["binary_sensor.oref_alert"],
                filter=selector.EntityFilterSelectorConfig(
                    integration="oref_alert", domain="binary_sensor"
                ),
            )
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entity from a config entry."""
    coordinator = OrefAlertDataUpdateCoordinator(
        hass, entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    )
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(
        entry, (Platform.BINARY_SENSOR,)
    )
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    async def add_sensor(service_call: ServiceCall) -> None:
        """Add an additional sensor (different areas)."""
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        sensors = {**config_entry.options.get(CONF_SENSORS, {})}
        sensors[f"{TITLE} {service_call.data[CONF_NAME]}"] = service_call.data[
            CONF_AREAS
        ]
        hass.config_entries.async_update_entry(
            config_entry,
            options={**config_entry.options, **{CONF_SENSORS: sensors}},
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        ADD_SENSOR_SERVICE,
        add_sensor,
        ADD_SENSOR_SCHEMA,
    )

    async def remove_sensor(service_call: ServiceCall) -> None:
        """Remove an additional sensor."""
        entity_reg = entity_registry.async_get(hass)
        entity_name = entity_reg.async_get(
            service_call.data[CONF_ENTITY_ID]
        ).original_name
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        sensors = {
            name: areas
            for name, areas in config_entry.options.get(CONF_SENSORS, {}).items()
            if name != entity_name
        }
        entity_reg.async_remove(service_call.data[CONF_ENTITY_ID])
        hass.config_entries.async_update_entry(
            config_entry,
            options={**config_entry.options, **{CONF_SENSORS: sensors}},
        )

    async_register_admin_service(
        hass,
        DOMAIN,
        REMOVE_SENSOR_SERVICE,
        remove_sensor,
        REMOVE_SENSOR_SCHEMA,
    )

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data[DOMAIN].pop(entry.entry_id)
    hass.services.async_remove(DOMAIN, ADD_SENSOR_SERVICE)
    return await hass.config_entries.async_unload_platforms(
        entry, (Platform.BINARY_SENSOR,)
    )
