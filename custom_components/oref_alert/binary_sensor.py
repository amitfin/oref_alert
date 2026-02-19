"""Support for representing oref alert as binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components import binary_sensor
from homeassistant.const import Platform
from homeassistant.util import slugify

from custom_components.oref_alert.records_schema import RecordType

from .entity import OrefAlertCoordinatorEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry

from .area_utils import expand_areas_and_groups
from .const import (
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_UPDATES,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_UPDATES,
    CONF_AREAS,
    CONF_SENSORS,
    OREF_ALERT_UNIQUE_ID,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: OrefAlertConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    names = [None, *list(config_entry.options.get(CONF_SENSORS, {}).keys())]
    async_add_entities(AlertSensor(name, config_entry) for name in names)


class AlertSensor(OrefAlertCoordinatorEntity, binary_sensor.BinarySensorEntity):
    """Representation of the alert binary sensor."""

    _attr_device_class = binary_sensor.BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "home_alert"
    _unrecorded_attributes = frozenset(
        {
            ATTR_COUNTRY_ACTIVE_ALERTS,
            ATTR_COUNTRY_UPDATES,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
            ATTR_SELECTED_AREAS_UPDATES,
            CONF_AREAS,
        }
    )

    def __init__(
        self,
        name: str | None,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._areas = expand_areas_and_groups(
            config_entry.options[CONF_AREAS]
            if not name
            else config_entry.options[CONF_SENSORS][name]
        )
        self._sensor_key: str = name or ""
        if not name:
            self.use_device_name = True
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
        else:
            self._attr_name = name
            self._attr_unique_id = slugify(
                f"{OREF_ALERT_UNIQUE_ID}_{name.lower().replace(' ', '_')}"
            )
        self.entity_id = f"{Platform.BINARY_SENSOR}.{self._attr_unique_id}"

    def _default_to_device_class_name(self) -> bool:
        """Do not use device class name for binary sensors."""
        return False

    @property
    def is_on(self) -> bool:
        """Return True if sensor is on."""
        return any(
            True
            for area in self._areas
            if (record := self.coordinator.data.areas.get(area))
            and record.record_type == RecordType.ALERT
        )

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            CONF_AREAS: self._areas,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS: self.coordinator.get_records(
                self._areas, {RecordType.ALERT}
            ),
            ATTR_SELECTED_AREAS_UPDATES: self.coordinator.get_records(
                self._areas, {RecordType.PRE_ALERT, RecordType.END}
            ),
            ATTR_COUNTRY_ACTIVE_ALERTS: self.coordinator.get_records(
                None, {RecordType.ALERT}
            ),
            ATTR_COUNTRY_UPDATES: self.coordinator.get_records(
                None, {RecordType.PRE_ALERT, RecordType.END}
            ),
        }

    def get_sensor_key(self) -> str:
        """Get the key of the extra sensor."""
        return self._sensor_key
