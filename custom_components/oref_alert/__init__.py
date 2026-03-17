"""Oref Alert Integration."""

from __future__ import annotations

import asyncio
import itertools
from typing import TYPE_CHECKING, Final, cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from attr import dataclass
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import entity_registry, selector
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_platform import async_get_platforms
from homeassistant.helpers.service import async_register_admin_service

from custom_components.oref_alert.classifier import Classifier
from custom_components.oref_alert.custom_cards import publish_cards

from .areas_checker import AreasChecker
from .bus_events import OrefAlertBusEventManager
from .metadata.areas_and_groups import AREAS_AND_GROUPS
from .pushy import PushyNotifications
from .template import inject_template_extensions
from .tzevaadom import TzevaAdomNotifications

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import (
        HomeAssistant,
        ServiceCall,
        ServiceResponse,
    )
    from homeassistant.helpers.typing import ConfigType

    from .binary_sensor import AlertSensor

from homeassistant.core import (
    SupportsResponse,
    callback,
)

from .config_flow import AREAS_CONFIG
from .const import (
    ADD_AREAS,
    ADD_SENSOR_ACTION,
    CATEGORY_FIELD,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DOMAIN,
    EDIT_SENSOR_ACTION,
    LOGGER,
    MANUAL_EVENT_END_ACTION,
    REMOVE_AREAS,
    REMOVE_SENSOR_ACTION,
    SYNTHETIC_ALERT_ACTION,
    TIME_TO_SHELTER_ID_SUFFIX,
    TITLE,
    TITLE_FIELD,
)
from .coordinator import OrefAlertCoordinatorUpdater, OrefAlertDataUpdateCoordinator
from .metadata.areas import AREAS

CONFIG_SCHEMA: Final = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = (
    Platform.EVENT,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.GEO_LOCATION,
)

ADD_SENSOR_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_NAME): selector.TextSelector(),
        vol.Required(CONF_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)

EXISTING_SENSOR_SELECTOR: Final = selector.EntitySelector(
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

REMOVE_SENSOR_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): EXISTING_SENSOR_SELECTOR,
    },
    extra=vol.ALLOW_EXTRA,
)

EDIT_SENSOR_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_ENTITY_ID): EXISTING_SENSOR_SELECTOR,
        vol.Required(ADD_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
        vol.Required(REMOVE_AREAS, default=[]): selector.SelectSelector(AREAS_CONFIG),
    },
    extra=vol.ALLOW_EXTRA,
)

SYNTHETIC_ALERT_SCHEMA: Final = vol.Schema(
    {
        vol.Required(CONF_AREA): vol.All(
            cv.ensure_list, [vol.All(cv.string, vol.In(AREAS))]
        ),
        vol.Required(CONF_DURATION, default=10): cv.positive_int,
        vol.Required(CATEGORY_FIELD, default=1): cv.positive_int,
        vol.Optional(TITLE_FIELD): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

MANUAL_EVENT_END_SCHEMA: Final = vol.Schema(
    {
        vol.Optional(CONF_AREA): vol.All(
            cv.ensure_list, [vol.All(cv.string, vol.In(AREAS))]
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class OrefAlertRuntimeData:
    """Oref Alert runtime data dataclass."""

    coordinator: OrefAlertDataUpdateCoordinator
    updater: OrefAlertCoordinatorUpdater
    areas_checker: AreasChecker
    unload_template_extensions: Callable[[], None]
    pushy: PushyNotifications
    tzevaadom: TzevaAdomNotifications
    classifier: Classifier
    bus_events: OrefAlertBusEventManager

    async def stop(self) -> None:
        """Stop background managers and release resources."""
        self.areas_checker.stop()
        self.updater.stop()
        self.unload_template_extensions()
        self.bus_events.stop()
        await asyncio.gather(
            self.coordinator.async_save(),
            self.bus_events.async_save(),
            self.pushy.stop(),
            self.tzevaadom.stop(),
            return_exceptions=True,
        )


type OrefAlertConfigEntry = ConfigEntry[OrefAlertRuntimeData]


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:  # noqa: PLR0915
    """Set up custom actions."""
    await publish_cards(hass)

    def get_config_entry() -> OrefAlertConfigEntry:
        """Get the integration's config first (and only) entry."""
        config_entries = hass.config_entries.async_entries(DOMAIN)
        if not config_entries:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="no_config_entry",
            )
        if config_entries[0].state is not ConfigEntryState.LOADED:
            raise ConfigEntryNotReady(
                translation_domain=DOMAIN, translation_key="config_entry_not_loaded"
            )
        return config_entries[0]

    async def add_sensor(service_call: ServiceCall) -> None:
        """Add an additional sensor (different areas)."""
        config_entry = get_config_entry()
        sensors = {**config_entry.options.get(CONF_SENSORS, {})}
        sensors[service_call.data[CONF_NAME]] = service_call.data[CONF_AREAS]
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

    def _get_sensor_key(entity_id: str) -> str:
        """Return the entity by a given entity_id."""
        sensor_key = ""
        for platform in async_get_platforms(hass, DOMAIN):
            if entity_id in platform.entities:
                sensor_key = cast(
                    "AlertSensor", platform.entities[entity_id]
                ).get_sensor_key()
                break
        return sensor_key

    async def remove_sensor(service_call: ServiceCall) -> None:
        """Remove an additional sensor."""
        entity_reg = entity_registry.async_get(hass)
        entity_id = service_call.data[CONF_ENTITY_ID]
        sensor_key = _get_sensor_key(entity_id)
        config_entry = get_config_entry()
        sensors = {
            name: areas
            for name, areas in config_entry.options.get(CONF_SENSORS, {}).items()
            if name != sensor_key
        }
        entity_reg.async_remove(entity_id)
        for platform, suffix in [
            (Platform.SENSOR, f"_{TIME_TO_SHELTER_ID_SUFFIX}"),
            (Platform.SENSOR, None),
            (Platform.EVENT, None),
        ]:
            delete_entity = f"{platform}.{entity_id.split('.')[1]}{suffix or ''}"
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
        entity_id = service_call.data[CONF_ENTITY_ID]
        sensor_key = _get_sensor_key(entity_id)
        config_entry = get_config_entry()
        sensors = {**get_config_entry().options.get(CONF_SENSORS, {})}
        if areas := sensors.get(sensor_key):
            sensors[sensor_key] = [
                area
                for area in (areas + service_call.data[ADD_AREAS])
                if area not in service_call.data[REMOVE_AREAS]
            ]
            hass.config_entries.async_update_entry(
                config_entry,
                options={**config_entry.options, CONF_SENSORS: sensors},
            )
            if service_call.return_response:
                return {CONF_AREAS: sensors[sensor_key]}
        return None

    async_register_admin_service(
        hass,
        DOMAIN,
        EDIT_SENSOR_ACTION,
        edit_sensor,
        EDIT_SENSOR_SCHEMA,
        SupportsResponse.OPTIONAL,
    )

    async def synthetic_alert(service_call: ServiceCall) -> None:
        """Add a synthetic alert for testing purposes."""
        get_config_entry().runtime_data.coordinator.add_synthetic_alert(
            service_call.data
        )
        await get_config_entry().runtime_data.coordinator.async_refresh()

    async_register_admin_service(
        hass,
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        synthetic_alert,
        SYNTHETIC_ALERT_SCHEMA,
    )

    async def manual_event_end(service_call: ServiceCall) -> None:
        """Mark active alerts as ended manually."""
        get_config_entry().runtime_data.coordinator.add_manual_event_end(
            service_call.data.get(CONF_AREA)
        )
        await get_config_entry().runtime_data.coordinator.async_refresh()

    async_register_admin_service(
        hass,
        DOMAIN,
        MANUAL_EVENT_END_ACTION,
        manual_event_end,
        MANUAL_EVENT_END_SCHEMA,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: OrefAlertConfigEntry) -> bool:
    """Set up entity from a config entry."""
    entry.async_on_unload(entry.add_update_listener(config_entry_update_listener))

    sensor_key_renamed = False
    sensors = {**entry.options.get(CONF_SENSORS, {})}
    sensor_names = set(sensors.keys())
    for sensor_name in sensor_names:
        if sensor_name.startswith(TITLE):
            sensors[sensor_name.removeprefix(TITLE).strip()] = sensors.pop(sensor_name)
            sensor_key_renamed = True
    if sensor_key_renamed:
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_SENSORS: sensors},
        )
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
    coordinator = OrefAlertDataUpdateCoordinator(
        hass, entry, [pushy.alerts, tzevaadom.alerts]
    )

    entry.runtime_data = OrefAlertRuntimeData(
        coordinator,
        OrefAlertCoordinatorUpdater(hass, coordinator),
        AreasChecker(hass),
        await inject_template_extensions(hass, entry),
        pushy,
        tzevaadom,
        Classifier(),
        OrefAlertBusEventManager(hass, entry),
    )

    @callback
    def _handle_shutdown(*_: object) -> None:
        """Persist coordinator state on Home Assistant shutdown."""
        hass.async_create_task(entry.runtime_data.coordinator.async_save())
        hass.async_create_task(entry.runtime_data.bus_events.async_save())

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _handle_shutdown)
    )

    entry.runtime_data.bus_events.start()

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        await asyncio.gather(
            entry.runtime_data.coordinator.async_restore(),
            entry.runtime_data.bus_events.async_restore(),
        )
        await entry.runtime_data.coordinator.async_config_entry_first_refresh()

        await asyncio.gather(
            entry.runtime_data.pushy.start(), entry.runtime_data.tzevaadom.start()
        )
    except Exception as exc:
        LOGGER.exception(f"Error loading {DOMAIN} config entry. Will retry later.")
        await entry.runtime_data.stop()
        raise ConfigEntryNotReady from exc

    entry.runtime_data.updater.start()

    return True


async def config_entry_update_listener(
    hass: HomeAssistant, entry: OrefAlertConfigEntry
) -> None:
    """Update listener, called when the config entry options are changed."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OrefAlertConfigEntry) -> bool:
    """Unload a config entry."""
    if not getattr(entry, "runtime_data", None):
        return True
    await entry.runtime_data.stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
