"""Oref Alert Integration."""

from __future__ import annotations

import asyncio
import inspect
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
from custom_components.oref_alert.pushy import PushyNotifications
from custom_components.oref_alert.template import inject_template_extensions
from custom_components.oref_alert.tzevaadom import TzevaAdomNotifications
from custom_components.oref_alert.update_events import OrefAlertUpdateEventManager

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import (
        HomeAssistant,
        ServiceCall,
        ServiceResponse,
    )

from homeassistant.core import (
    SupportsResponse,
)

from .config_flow import AREAS_CONFIG
from .const import (
    ADD_AREAS,
    ADD_SENSOR_ACTION,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALERT_MAX_AGE_DEPRECATED,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DATA_COORDINATOR,
    DOMAIN,
    EDIT_SENSOR_ACTION,
    END_TIME_ID_SUFFIX,
    REMOVE_AREAS,
    REMOVE_SENSOR_ACTION,
    SYNTHETIC_ALERT_ACTION,
    TIME_TO_SHELTER_ID_SUFFIX,
    TITLE,
    AlertField,
)
from .coordinator import OrefAlertDataUpdateCoordinator
from .metadata.areas import AREAS

AREAS_CHECKER: Final = "areas_checker"
UNLOAD_TEMPLATE_EXTENSIONS: Final = "unload_template_extensions"
PUSHY: Final = "pushy"
TZEVAADOM: Final = "tzevaadom"
PLATFORMS = (Platform.BINARY_SENSOR, Platform.SENSOR, Platform.GEO_LOCATION)

ADD_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)

EXISTING_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(
        exclude_entities=[
            "binary_sensor.oref_alert",
            "binary_sensor.oref_alert_all_areas",
        ],
        filter=selector.EntityFilterSelectorConfig(
            integration="oref_alert", domain="binary_sensor"
        ),
    )
)

REMOVE_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): EXISTING_SENSOR_SELECTOR,
    },
    extra=vol.ALLOW_EXTRA,
)

EDIT_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): EXISTING_SENSOR_SELECTOR,
        vol.Required(ADD_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
        vol.Required(REMOVE_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)

SYNTHETIC_ALERT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AREA): vol.All(
            cv.ensure_list, [vol.All(cv.string, vol.In(AREAS))]
        ),
        vol.Required(CONF_DURATION, default=10): cv.positive_int,
        vol.Required(AlertField.CATEGORY.value, default=1): cv.positive_int,
        vol.Optional(AlertField.TITLE.value): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # noqa: PLR0915
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

    pushy = PushyNotifications(hass, entry)
    tzevaadom = TzevaAdomNotifications(hass, entry)

    entry.runtime_data = {
        DATA_COORDINATOR: OrefAlertDataUpdateCoordinator(
            hass, entry, [pushy.alerts, tzevaadom.alerts]
        ),
        AREAS_CHECKER: AreasChecker(hass),
        UNLOAD_TEMPLATE_EXTENSIONS: await inject_template_extensions(hass),
        PUSHY: pushy,
        TZEVAADOM: tzevaadom,
    }

    await entry.runtime_data[DATA_COORDINATOR].async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    OrefAlertUpdateEventManager(hass, entry)

    await asyncio.gather(
        entry.runtime_data[PUSHY].start(), entry.runtime_data[TZEVAADOM].start()
    )

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
        ADD_SENSOR_ACTION,
        add_sensor,
        ADD_SENSOR_SCHEMA,
    )

    async def remove_sensor(service_call: ServiceCall) -> None:
        """Remove an additional sensor."""
        entity_reg = entity_registry.async_get(hass)
        entity_id = service_call.data[CONF_ENTITY_ID]
        entity_name = getattr(entity_reg.async_get(entity_id), "original_name", "")
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if config_entry is not None:
            sensors = {
                name: areas
                for name, areas in config_entry.options.get(CONF_SENSORS, {}).items()
                if name != entity_name
            }
            entity_reg.async_remove(entity_id)
            for suffix in [TIME_TO_SHELTER_ID_SUFFIX, END_TIME_ID_SUFFIX]:
                delete_entity = f"{Platform.SENSOR}.{entity_id.split('.')[1]}_{suffix}"
                if entity_reg.async_get(delete_entity) is not None:
                    entity_reg.async_remove(delete_entity)
            hass.config_entries.async_update_entry(
                config_entry,
                options={**config_entry.options, CONF_SENSORS: sensors},
            )

    async_register_admin_service(
        hass,
        DOMAIN,
        REMOVE_SENSOR_ACTION,
        remove_sensor,
        REMOVE_SENSOR_SCHEMA,
    )

    async def edit_sensor(service_call: ServiceCall) -> ServiceResponse | None:
        """Edit sensor."""
        entity_reg = entity_registry.async_get(hass)
        entity_id = service_call.data[CONF_ENTITY_ID]
        entity_name = getattr(entity_reg.async_get(entity_id), "original_name", "")
        config_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if config_entry is not None:
            sensors = {**config_entry.options.get(CONF_SENSORS, {})}
            if areas := sensors.get(entity_name):
                sensors[entity_name] = [
                    area
                    for area in (areas + service_call.data[ADD_AREAS])
                    if area not in service_call.data[REMOVE_AREAS]
                ]
                hass.config_entries.async_update_entry(
                    config_entry,
                    options={**config_entry.options, CONF_SENSORS: sensors},
                )
                if service_call.return_response:
                    return {CONF_AREAS: sensors[entity_name]}
        return None

    async_register_admin_service(
        hass,
        DOMAIN,
        EDIT_SENSOR_ACTION,
        edit_sensor,
        EDIT_SENSOR_SCHEMA,
        **(
            {"supports_response": SupportsResponse.OPTIONAL}
            if "supports_response"
            in inspect.signature(async_register_admin_service).parameters
            else {}
        ),
    )

    async def synthetic_alert(service_call: ServiceCall) -> None:
        """Add a synthetic alert for testing purposes."""
        entry.runtime_data[DATA_COORDINATOR].add_synthetic_alert(service_call.data)

    async_register_admin_service(
        hass,
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        synthetic_alert,
        SYNTHETIC_ALERT_SCHEMA,
    )

    return True


async def config_entry_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener, called when the config entry options are changed."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not getattr(entry, "runtime_data", None):
        return True
    entry.runtime_data[AREAS_CHECKER].stop()
    await asyncio.gather(
        entry.runtime_data[PUSHY].stop(), entry.runtime_data[TZEVAADOM].stop()
    )
    entry.runtime_data[UNLOAD_TEMPLATE_EXTENSIONS]()
    entry.runtime_data = None
    for service in [
        ADD_SENSOR_ACTION,
        REMOVE_SENSOR_ACTION,
        EDIT_SENSOR_ACTION,
        SYNTHETIC_ALERT_ACTION,
    ]:
        hass.services.async_remove(DOMAIN, service)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
