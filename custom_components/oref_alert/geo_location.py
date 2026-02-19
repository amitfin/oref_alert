"""Support for oref alerts geo location events."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from homeassistant.components.geo_location import ATTR_SOURCE, GeolocationEvent
from homeassistant.const import (
    ATTR_DATE,
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_FRIENDLY_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.location import vincenty

from custom_components.oref_alert.records_schema import RecordType

from .categories import (
    category_to_emoji,
    category_to_icon,
)
from .const import (
    AREA_FIELD,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    CATEGORY_FIELD,
    DATE_FIELD,
    DOMAIN,
    LOCATION_ID_SUFFIX,
    OREF_ALERT_UNIQUE_ID,
    TITLE_FIELD,
    RecordAndMetadata,
)
from .entity import OrefAlertEntity
from .metadata.area_info import AREA_INFO

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
            CONF_FRIENDLY_NAME,
            CONF_UNIT_OF_MEASUREMENT,
            CATEGORY_FIELD,
            TITLE_FIELD,
        }
    )

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
        area: str,
        record: RecordAndMetadata,
    ) -> None:
        """Initialize entity."""
        super().__init__(config_entry)
        self._attr_name = area
        self._attr_latitude: float = AREA_INFO[area]["lat"]
        self._attr_longitude: float = AREA_INFO[area]["lon"]
        self._attr_unit_of_measurement = UnitOfLength.KILOMETERS
        self._attr_distance = round(
            vincenty(
                (hass.config.latitude, hass.config.longitude),
                (self._attr_latitude, self._attr_longitude),
            )
            or 0,
            1,
        )
        self._record: RecordAndMetadata | None = None
        self._alert_attributes: dict[str, Any] = {}
        self._update_record(record)

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
    def _update_record(self, record: RecordAndMetadata) -> None:
        """Update the record and attributes."""
        self._record = record
        attributes: dict[str, Any] = {}
        attributes = {
            key: value
            for key, value in asdict(record.item).items()
            if key not in {AREA_FIELD, DATE_FIELD}
        }
        attributes[ATTR_DATE] = record.time
        attributes[ATTR_ICON] = category_to_icon(record.item.category)
        attributes[ATTR_EMOJI] = category_to_emoji(record.item.category)
        self._alert_attributes = attributes

    @callback
    def async_update(self, record: RecordAndMetadata) -> None:
        """Update the record and extra attributes when needed."""
        if record != self._record:
            self._update_record(record)
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
                self._location_events[area].async_remove_self()

        to_add = {
            area: OrefAlertLocationEvent(self._hass, self._config_entry, area, record)
            for area in set(self._coordinator.data.areas.keys()) - exists
            if (record := self._coordinator.data.areas.get(area))
            and record.record_type == RecordType.ALERT
            and area in AREA_INFO
        }
        self._location_events.update(to_add)
        self._async_add_entities(to_add.values())
