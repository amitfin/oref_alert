"""Support for representing daily schedule as binary sensors."""
from __future__ import annotations

from typing import Any

from collections.abc import Mapping

from homeassistant.components import binary_sensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .area_utils import expand_areas_and_groups
from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    TITLE,
    CONF_AREAS,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_SENSORS,
    ALL_AREAS_ID_SUFFIX,
    ALL_AREAS_NAME_SUFFIX,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    DEFAULT_OFF_ICON,
    DEFAULT_ON_ICON,
    OREF_ALERT_UNIQUE_ID,
)
from .coordinator import OrefAlertCoordinatorData, OrefAlertDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        [
            AlertSensor(name, config_entry, coordinator)
            for name in [None] + list(config_entry.options.get(CONF_SENSORS, {}).keys())
        ]
        + [AlertSensorAllAreas(config_entry, coordinator)]
    )


class AlertSensorBase(
    CoordinatorEntity[OrefAlertDataUpdateCoordinator], binary_sensor.BinarySensorEntity
):
    """Representation of the alert sensor base."""

    _attr_has_entity_name = True
    _attr_device_class = binary_sensor.BinarySensorDeviceClass.SAFETY
    _entity_component_unrecorded_attributes = frozenset(
        {
            ATTR_COUNTRY_ACTIVE_ALERTS,
            ATTR_COUNTRY_ALERTS,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
            ATTR_SELECTED_AREAS_ALERTS,
            CONF_AREAS,
            CONF_ALERT_ACTIVE_DURATION,
        }
    )

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._on_icon = self._config_entry.options.get(CONF_ON_ICON, DEFAULT_ON_ICON)
        self._off_icon = self._config_entry.options.get(CONF_OFF_ICON, DEFAULT_OFF_ICON)
        self._data: OrefAlertCoordinatorData = coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the data from the coordinator."""
        self._data = self.coordinator.data
        super()._handle_coordinator_update()

    @property
    def icon(self):
        """Return the sensor icon."""
        return self._on_icon if self.is_on else self._off_icon


class AlertSensor(AlertSensorBase):
    """Representation of the alert sensor."""

    def __init__(
        self,
        name: str | None,
        config_entry: ConfigEntry,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry, coordinator)
        if not name:
            self._attr_name = TITLE
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
            self._areas = expand_areas_and_groups(
                self._config_entry.options[CONF_AREAS]
            )
        else:
            self._attr_name = name
            self._attr_unique_id = name.lower().replace(" ", "_")
            self._areas = expand_areas_and_groups(
                self._config_entry.options[CONF_SENSORS][name]
            )

    @property
    def is_on(self) -> bool:
        """Return True is sensor is on."""
        for alert in self._data.active_alerts:
            if self.is_selected_area(alert):
                return True
        return False

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            CONF_AREAS: self._areas,
            CONF_ALERT_ACTIVE_DURATION: self._config_entry.options[CONF_ALERT_ACTIVE_DURATION],
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS: [
                alert
                for alert in self._data.active_alerts
                if self.is_selected_area(alert)
            ],
            ATTR_SELECTED_AREAS_ALERTS: [
                alert for alert in self._data.alerts if self.is_selected_area(alert)
            ],
            ATTR_COUNTRY_ACTIVE_ALERTS: self._data.active_alerts,
            ATTR_COUNTRY_ALERTS: self._data.alerts,
        }

    def is_selected_area(self, alert: dict[str, str]) -> bool:
        """Check is the alert is among the selected areas."""
        return alert["data"] in self._areas


class AlertSensorAllAreas(AlertSensorBase):
    """Representation of the alert sensor for all areas."""

    def __init__(
        self,
        config_entry: ConfigEntry,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry, coordinator)
        self._attr_name = f"{TITLE} {ALL_AREAS_NAME_SUFFIX}"
        self._attr_unique_id = f"{OREF_ALERT_UNIQUE_ID}_{ALL_AREAS_ID_SUFFIX}"

    @property
    def is_on(self) -> bool:
        """Return True is sensor is on."""
        return len(self._data.active_alerts) > 0

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            CONF_ALERT_ACTIVE_DURATION: self._config_entry.options[CONF_ALERT_ACTIVE_DURATION],
            ATTR_COUNTRY_ACTIVE_ALERTS: self._data.active_alerts,
            ATTR_COUNTRY_ALERTS: self._data.alerts,
        }
