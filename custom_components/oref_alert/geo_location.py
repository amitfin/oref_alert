"""Support for oref alerts geo location events."""
from __future__ import annotations

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DATA_COORDINATOR, DOMAIN, OREF_ALERT_UNIQUE_ID, LOCATION_ID_SUFFIX
from .coordinator import OrefAlertDataUpdateCoordinator
from .metadata.area_info import AREA_INFO


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    OrefAlertLocationEventManager(hass, config_entry, async_add_entities)


class OrefAlertLocationEvent(GeolocationEvent):
    """Represents an oref alert."""

    _attr_should_poll = False
    _attr_source = DOMAIN
    _attr_has_entity_name = True

    def __init__(
        self,
        area: str,
    ) -> None:
        """Initialize entity."""
        self._attr_name = area
        self._attr_unique_id = f"{OREF_ALERT_UNIQUE_ID}_{LOCATION_ID_SUFFIX}_{slugify(AREA_INFO[area]['en'])}"
        self._attr_latitude = AREA_INFO[area]["lat"]
        self._attr_longitude = AREA_INFO[area]["long"]

    @property
    def suggested_object_id(self) -> str | None:
        """Return input for object id."""
        return self._attr_unique_id

    def _async_remove_self(self) -> None:
        """Remove this entity."""
        self.hass.async_create_task(self.async_remove(force_remove=True))


class OrefAlertLocationEventManager:
    """Add and remove location event entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Initialize object with defaults."""
        self._location_events: dict[str, OrefAlertLocationEvent] = {}
        self._hass = hass
        self._config_entry = config_entry
        self._async_add_entities = async_add_entities
        self._coordinator: OrefAlertDataUpdateCoordinator = hass.data[DOMAIN][
            config_entry.entry_id
        ][DATA_COORDINATOR]
        self._async_clean_start()
        self._coordinator.async_add_listener(self._async_update)
        self._async_update()

    def _async_clean_start(self) -> None:
        """Remove all geo_location entities for a clean start."""
        entity_registry = er.async_get(self._hass)
        entries = er.async_entries_for_config_entry(
            entity_registry, self._config_entry.entry_id
        )
        for entry in entries or []:
            if entry.domain == Platform.GEO_LOCATION:
                entity_registry.async_remove(entry.entity_id)

    @callback
    def _async_update(self) -> None:
        """Add and/or remove entities according to the new active alerts list."""
        current = {alert["data"] for alert in self._coordinator.data.active_alerts}
        previous = set(self._location_events.keys())
        for to_delete in previous - current:
            self._location_events[to_delete]._async_remove_self()
            del self._location_events[to_delete]
        to_add = {area: OrefAlertLocationEvent(area) for area in current - previous}
        self._async_add_entities(to_add.values())
        self._location_events.update(to_add)
