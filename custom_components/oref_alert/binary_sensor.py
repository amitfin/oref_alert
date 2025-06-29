"""Support for representing daily schedule as binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.components import binary_sensor
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .area_utils import expand_areas_and_groups
from .const import (
    ALL_AREAS_ID_SUFFIX,
    ALL_AREAS_NAME_SUFFIX,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_COUNTRY_UPDATES,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    ATTR_SELECTED_AREAS_UPDATES,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREAS,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_SENSORS,
    DATA_COORDINATOR,
    DEFAULT_OFF_ICON,
    DEFAULT_ON_ICON,
    IST,
    OREF_ALERT_UNIQUE_ID,
    TITLE,
    AlertField,
)
from .coordinator import OrefAlertCoordinatorData, OrefAlertDataUpdateCoordinator

if TYPE_CHECKING:
    from collections.abc import Mapping

SECONDS_IN_A_MINUTE = 60


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator = config_entry.runtime_data[DATA_COORDINATOR]
    names = [None, *list(config_entry.options.get(CONF_SENSORS, {}).keys())]
    async_add_entities(
        [AlertSensor(name, config_entry, coordinator) for name in names]
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
            ATTR_COUNTRY_UPDATES,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
            ATTR_SELECTED_AREAS_ALERTS,
            ATTR_SELECTED_AREAS_UPDATES,
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
        self._common_attributes = {
            CONF_ALERT_ACTIVE_DURATION: self._config_entry.options[
                CONF_ALERT_ACTIVE_DURATION
            ],
        }
        self._add_all_alerts_attributes: bool = config_entry.options.get(
            CONF_ALL_ALERTS_ATTRIBUTES, False
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the data from the coordinator."""
        self._data = self.coordinator.data
        super()._handle_coordinator_update()

    @property
    def icon(self) -> str:
        """Return the sensor icon."""
        return self._on_icon if self.is_on else self._off_icon


class AlertAreaSensorBase(AlertSensorBase):
    """Representation of alert area sensor."""

    def __init__(
        self,
        areas: list[str],
        config_entry: ConfigEntry,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry, coordinator)
        self._areas = expand_areas_and_groups(areas)
        self._common_area_sensor_attributes = {
            CONF_AREAS: self._areas,
            **self._common_attributes,
        }

    def is_selected_area(self, alert: dict[str, str]) -> bool:
        """Check is the alert is among the selected areas."""
        return (
            alert[AlertField.AREA] in self._areas
            or alert[AlertField.AREA] in ALL_AREAS_ALIASES
        )


class AlertSensor(AlertAreaSensorBase):
    """Representation of the alert sensor."""

    def __init__(
        self,
        name: str | None,
        config_entry: ConfigEntry,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(
            config_entry.options[CONF_AREAS]
            if not name
            else config_entry.options[CONF_SENSORS][name],
            config_entry,
            coordinator,
        )
        self._active_seconds: int = (
            config_entry.options[CONF_ALERT_ACTIVE_DURATION] * SECONDS_IN_A_MINUTE
        )
        self._is_on_timestamp: float = 0
        if not name:
            self._attr_name = TITLE
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
        else:
            self._attr_name = name
            self._attr_unique_id = name.lower().replace(" ", "_")

    @property
    def is_on(self) -> bool:
        """Return True is sensor is on."""
        if (dt_util.now().timestamp() - self._is_on_timestamp) < self._active_seconds:
            # The state should stay "on" for the active duration.
            return True

        for alert in self._data.active_alerts:
            if self.is_selected_area(alert):
                if not self.coordinator.is_synthetic_alert(alert):
                    self._is_on_timestamp = (
                        dt_util.parse_datetime(
                            alert[AlertField.DATE], raise_on_error=True
                        )
                        .replace(tzinfo=IST)
                        .timestamp()
                    )
                return True
        return False

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            **self._common_area_sensor_attributes,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS: [
                alert
                for alert in self._data.active_alerts
                if self.is_selected_area(alert)
            ],
            **(
                {
                    ATTR_SELECTED_AREAS_ALERTS: [
                        alert
                        for alert in self._data.alerts
                        if self.is_selected_area(alert)
                    ],
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_SELECTED_AREAS_UPDATES: [
                alert for alert in self._data.updates if self.is_selected_area(alert)
            ],
            ATTR_COUNTRY_ACTIVE_ALERTS: self._data.active_alerts,
            **(
                {
                    ATTR_COUNTRY_ALERTS: self._data.alerts,
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_COUNTRY_UPDATES: self._data.updates,
        }


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
            **self._common_attributes,
            ATTR_COUNTRY_ACTIVE_ALERTS: self._data.active_alerts,
            **(
                {
                    ATTR_COUNTRY_ALERTS: self._data.alerts,
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_COUNTRY_UPDATES: self._data.updates,
        }
