"""Oref Alert Integration."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING, Final

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.const import CONF_ENTITY_ID, CONF_NAME, Platform
from homeassistant.helpers import entity_registry, selector
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service

from custom_components.oref_alert.areas_checker import AreasChecker
from custom_components.oref_alert.metadata.areas_and_groups import AREAS_AND_GROUPS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

from .config_flow import AREAS_CONFIG
from .const import (
    ADD_SENSOR_SERVICE,
    ATTR_CATEGORY,
    ATTR_TITLE,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALERT_MAX_AGE_DEPRECATED,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DATA_COORDINATOR,
    DOMAIN,
    END_TIME_ID_SUFFIX,
    PREEMPTIVE_UPDATE_ID_SUFFIX,
    REMOVE_SENSOR_SERVICE,
    SYNTHETIC_ALERT_SERVICE,
    TIME_TO_SHELTER_ID_SUFFIX,
    TITLE,
)
from .coordinator import OrefAlertDataUpdateCoordinator
from .metadata.areas import AREAS

AREAS_CHECKER: Final = "areas_checker"
PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR, Platform.GEO_LOCATION)

ADD_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),  # type: ignore[reportArgumentType]
    },
    extra=vol.ALLOW_EXTRA,
)

REMOVE_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(
                exclude_entities=[
                    "binary_sensor.oref_alert",
                    "binary_sensor.oref_alert_all_areas",
                ],
                filter=selector.EntityFilterSelectorConfig(
                    integration="oref_alert", domain="binary_sensor"
                ),
            )
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

SYNTHETIC_ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AREA): vol.All(cv.string, vol.In(AREAS)),
        vol.Required(CONF_DURATION, default=10): cv.positive_int,
        vol.Required(ATTR_CATEGORY, default=1): cv.positive_int,
        vol.Optional(ATTR_TITLE): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up entity from a config entry."""
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    if CONF_ALERT_MAX_AGE_DEPRECATED in entry.options:
        options = {**entry.options}
        options[CONF_ALERT_ACTIVE_DURATION] = options.pop(CONF_ALERT_MAX_AGE_DEPRECATED)
        hass.config_entries.async_update_entry(entry, options=options)
        # config_entry_update_listener will be called and trigger a reload.
        return True

    for area in itertools.chain(
        entry.options[CONF_AREAS],
        itertools.chain.from_iterable(entry.options.get(CONF_SENSORS, {}).values()),
    ):
        if area not in AREAS_AND_GROUPS:
            ir.async_create_issue(
                hass,
                DOMAIN,
                f"{DOMAIN}_{area}",
                is_fixable=False,
                learn_more_url="https://github.com/amitfin/oref_alert",
                severity=ir.IssueSeverity.ERROR,
                translation_key="unknown_area",
                translation_placeholders={
                    "area": area,
                },
            )

    coordinator = OrefAlertDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
        AREAS_CHECKER: AreasChecker(hass),
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def add_sensor(service_call: ServiceCall) -> None:
        """Add an additional sensor (different areas)."""
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if config_entry is not None:
            sensors = {**config_entry.options.get(CONF_SENSORS, {})}
            sensors[f"{TITLE} {service_call.data[CONF_NAME]}"] = service_call.data[
                CONF_AREAS
            ]
            hass.config_entries.async_update_entry(
                config_entry,
                options={**config_entry.options, CONF_SENSORS: sensors},
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
        entity_name = getattr(
            entity_reg.async_get(service_call.data[CONF_ENTITY_ID]), "original_name", ""
        )
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if config_entry is not None:
            sensors = {
                name: areas
                for name, areas in config_entry.options.get(CONF_SENSORS, {}).items()
                if name != entity_name
            }
            entity_reg.async_remove(service_call.data[CONF_ENTITY_ID])
            entity_reg.async_remove(
                f"{service_call.data[CONF_ENTITY_ID]}_{PREEMPTIVE_UPDATE_ID_SUFFIX}"
            )
            for suffix in [TIME_TO_SHELTER_ID_SUFFIX, END_TIME_ID_SUFFIX]:
                entity_id = (
                    f"{Platform.SENSOR}."
                    f"{service_call.data[CONF_ENTITY_ID].split('.')[1]}_{suffix}"
                )
                if entity_reg.async_get(entity_id) is not None:
                    entity_reg.async_remove(entity_id)
            hass.config_entries.async_update_entry(
                config_entry,
                options={**config_entry.options, CONF_SENSORS: sensors},
            )

    async_register_admin_service(
        hass,
        DOMAIN,
        REMOVE_SENSOR_SERVICE,
        remove_sensor,
        REMOVE_SENSOR_SCHEMA,
    )

    async def synthetic_alert(service_call: ServiceCall) -> None:
        """Add a synthetic alert for testing purposes."""
        coordinator.add_synthetic_alert(service_call.data)

    async_register_admin_service(
        hass,
        DOMAIN,
        SYNTHETIC_ALERT_SERVICE,
        synthetic_alert,
        SYNTHETIC_ALERT_SCHEMA,
    )

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if DOMAIN not in hass.data:
        return True
    if (data := hass.data[DOMAIN].pop(entry.entry_id)) is not None:
        data[AREAS_CHECKER].stop()
    for service in [ADD_SENSOR_SERVICE, REMOVE_SENSOR_SERVICE, SYNTHETIC_ALERT_SERVICE]:
        hass.services.async_remove(DOMAIN, service)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
