"""Support for oref alerts geo location events."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
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

from .categories import (
    category_to_emoji,
    category_to_icon,
)
from .const import (
    ATTR_AREA,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    DOMAIN,
    IST,
    LOCATION_ID_SUFFIX,
    OREF_ALERT_UNIQUE_ID,
    AlertField,
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
            AlertField.CATEGORY,
            AlertField.TITLE,
        }
    )

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
        area: str,
        attributes: dict,
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
        self._alert_attributes = attributes

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

    def async_update(self, attributes: dict) -> bool:
        """Update the extra attributes when needed."""
        if not attributes or attributes == self._alert_attributes:
            return False
        significant_update = False
        for attribute in [AlertField.TITLE, AlertField.CATEGORY]:
            if attributes.get(attribute) != self._alert_attributes.get(attribute):
                significant_update = True
        self._alert_attributes = attributes
        self.async_write_ha_state()
        return significant_update


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

    def _alert_attributes(self, area: str) -> dict:
        """Return alert's attributes."""
        attributes = {}
        for alert in self._coordinator.data.active_alerts:
            if alert[AlertField.AREA] == area:
                attributes = {
                    key: value
                    for key, value in alert.items()
                    if key not in {AlertField.AREA, AlertField.DATE}
                }
                attributes[ATTR_DATE] = dt_util.parse_datetime(
                    alert[AlertField.DATE], raise_on_error=True
                ).replace(tzinfo=IST)
                attributes[ATTR_ICON] = category_to_icon(
                    attributes[AlertField.CATEGORY]
                )
                attributes[ATTR_EMOJI] = category_to_emoji(
                    attributes[AlertField.CATEGORY]
                )
                break
        return attributes

    @callback
    async def _cleanup_entities(self) -> None:
        """Remove entities."""
        await asyncio.sleep(10)  # Wait for a stable state.
        active = {
            alert[AlertField.AREA] for alert in self._coordinator.data.active_alerts
        }
        areas_to_delete = set(self._location_events.keys()) - active
        for area in areas_to_delete:
            if (entity := self._location_events.pop(area, None)) is not None:
                entity.async_remove_self()

    def fire_events(self, events: dict[str, OrefAlertLocationEvent]) -> None:
        """Fire events for new locations."""
        for area, event in events.items():
            attributes = event.extra_state_attributes
            self._hass.bus.async_fire(
                f"{DOMAIN}_event",
                {
                    ATTR_AREA: area,
                    ATTR_HOME_DISTANCE: event.distance,
                    ATTR_LATITUDE: event.latitude,
                    ATTR_LONGITUDE: event.longitude,
                    AlertField.CATEGORY: attributes.get(AlertField.CATEGORY),
                    AlertField.TITLE: attributes.get(AlertField.TITLE),
                    ATTR_ICON: attributes.get(ATTR_ICON),
                    ATTR_EMOJI: attributes.get(ATTR_EMOJI),
                    AlertField.CHANNEL: attributes.get(AlertField.CHANNEL),
                },
            )

    @callback
    def _async_update(self) -> None:
        """Add and/or remove entities according to the new active alerts list."""
        active = {
            alert[AlertField.AREA] for alert in self._coordinator.data.active_alerts
        }
        exists = set(self._location_events.keys())

        updated = {
            area: self._location_events[area]
            for area in exists.intersection(active)
            if self._location_events[area].async_update(self._alert_attributes(area))
        }

        to_add = {
            area: OrefAlertLocationEvent(
                self._hass, self._config_entry, area, self._alert_attributes(area)
            )
            for area in active - exists
            if area in AREA_INFO
        }
        self._location_events.update(to_add)
        self._async_add_entities(to_add.values())

        self.fire_events({**updated, **to_add})

        if len(exists - active):
            self._hass.async_create_task(self._cleanup_entities())
