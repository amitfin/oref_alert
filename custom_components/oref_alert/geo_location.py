"""Support for oref alerts geo location events."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.geo_location import ATTR_SOURCE, GeolocationEvent
from homeassistant.const import (
    ATTR_DATE,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_FRIENDLY_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant, callback

from .const import (
    ATTR_AREA,
    ATTR_DISTRICT,
    ATTR_HOME_DISTANCE,
    ATTR_TYPE,
    CATEGORY_FIELD,
    DOMAIN,
    LOCATION_ID_SUFFIX,
    OREF_ALERT_UNIQUE_ID,
    TITLE_FIELD,
    PublishedData,
    RecordAndMetadata,
    RecordType,
)
from .entity import OrefAlertEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry
    from .coordinator import OrefAlertDataUpdateCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OrefAlertConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    OrefAlertLocationEventManager(hass, config_entry, async_add_entities)


class OrefAlertLocationEvent(OrefAlertEntity, GeolocationEvent):
    """Represents an oref alert."""

    _attr_source = DOMAIN
    _unrecorded_attributes = frozenset(
        {
            ATTR_SOURCE,
            ATTR_LATITUDE,
            ATTR_LONGITUDE,
            ATTR_DATE,
            ATTR_HOME_DISTANCE,
            ATTR_DISTRICT,
            CONF_FRIENDLY_NAME,
            CONF_UNIT_OF_MEASUREMENT,
            CATEGORY_FIELD,
            TITLE_FIELD,
        }
    )

    def __init__(
        self,
        config_entry: OrefAlertConfigEntry,
        area: str,
        record: RecordAndMetadata,
        data: PublishedData,
    ) -> None:
        """Initialize entity."""
        super().__init__(config_entry)
        self._attr_name = area
        self._attr_latitude = data[ATTR_LATITUDE]
        self._attr_longitude = data[ATTR_LONGITUDE]
        self._attr_unit_of_measurement = UnitOfLength.KILOMETERS
        self._attr_distance = data[ATTR_HOME_DISTANCE]
        self._record: RecordAndMetadata | None = None
        self._alert_attributes: dict[str, Any] = {}
        self._update_record(record, data)

    @property
    def suggested_object_id(self) -> str | None:
        """Return input for object id."""
        return f"{OREF_ALERT_UNIQUE_ID}_{LOCATION_ID_SUFFIX}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {**self._alert_attributes, ATTR_HOME_DISTANCE: self._attr_distance}

    @callback
    def async_remove_self(self) -> None:
        """Remove this entity."""
        self.hass.async_create_task(self.async_remove(force_remove=True))

    @callback
    def _update_record(self, record: RecordAndMetadata, data: PublishedData) -> None:
        """Update the record and attributes."""
        self._record = record
        attributes = {
            key: value
            for key, value in data.items()
            if key
            not in {
                ATTR_AREA,
                ATTR_HOME_DISTANCE,
                ATTR_LATITUDE,
                ATTR_LONGITUDE,
                ATTR_TYPE,
            }
        }
        self._alert_attributes = attributes

    @callback
    def async_update(self, record: RecordAndMetadata) -> None:
        """Update the record and extra attributes when needed."""
        if self._record and record != self._record and record.published_data:
            self._update_record(record, record.published_data)
            self.async_write_ha_state()


class OrefAlertLocationEventManager:
    """Add and remove location event entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        """Initialize object with defaults."""
        self._location_events: dict[str, OrefAlertLocationEvent] = {}
        self._hass = hass
        self._config_entry = config_entry
        self._async_add_entities = async_add_entities
        self._coordinator: OrefAlertDataUpdateCoordinator = (
            config_entry.runtime_data.coordinator
        )
        self._coordinator.async_add_listener(self._async_update)
        self._async_update()

    @callback
    def _async_update(self) -> None:
        """Add and/or remove entities according to the new records list."""
        exists = set(self._location_events.keys())
        for area in exists:
            if (
                record := self._coordinator.data.areas.get(area)
            ) and record.record_type == RecordType.ALERT:
                self._location_events[area].async_update(record)
            else:
                self._location_events.pop(area).async_remove_self()

        to_add = {
            area: OrefAlertLocationEvent(
                self._config_entry, area, record, record.published_data
            )
            for area in set(self._coordinator.data.areas.keys()) - exists
            if (record := self._coordinator.data.areas.get(area))
            and record.record_type == RecordType.ALERT
            and record.published_data is not None
        }
        self._location_events.update(to_add)
        self._async_add_entities(to_add.values())
