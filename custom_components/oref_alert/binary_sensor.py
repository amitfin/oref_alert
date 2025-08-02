"""Support for representing oref alert as binary sensors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.components import binary_sensor
from homeassistant.const import Platform
from homeassistant.util import slugify

from .entity import OrefAlertCoordinatorEntity
from .metadata import ALL_AREAS_ALIASES

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry

from .area_utils import expand_areas_and_groups
from .const import (
    ALL_AREAS_ID_SUFFIX,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_COUNTRY_UPDATES,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    ATTR_SELECTED_AREAS_UPDATES,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREAS,
    CONF_SENSORS,
    IST,
    OREF_ALERT_UNIQUE_ID,
    AlertField,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

PARALLEL_UPDATES = 0

SECONDS_IN_A_MINUTE = 60


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: OrefAlertConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    names = [None, *list(config_entry.options.get(CONF_SENSORS, {}).keys())]
    async_add_entities(
        [AlertSensor(name, config_entry) for name in names]
        + [AlertSensorAllAreas(config_entry)]
    )


class AlertSensorBase(OrefAlertCoordinatorEntity, binary_sensor.BinarySensorEntity):
    """Representation of the alert sensor base."""

    _attr_device_class = binary_sensor.BinarySensorDeviceClass.SAFETY
    _attr_translation_key = "home_alert"
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
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._common_attributes = {
            CONF_ALERT_ACTIVE_DURATION: self._config_entry.options[
                CONF_ALERT_ACTIVE_DURATION
            ],
        }
        self._add_all_alerts_attributes: bool = config_entry.options.get(
            CONF_ALL_ALERTS_ATTRIBUTES, False
        )


class AlertAreaSensorBase(AlertSensorBase):
    """Representation of alert area sensor."""

    def __init__(
        self,
        areas: list[str],
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
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
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(
            config_entry.options[CONF_AREAS]
            if not name
            else config_entry.options[CONF_SENSORS][name],
            config_entry,
        )
        self._active_seconds: int = (
            config_entry.options[CONF_ALERT_ACTIVE_DURATION] * SECONDS_IN_A_MINUTE
        )
        self._is_on_timestamp: float = 0
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
        """Return True is sensor is on."""
        if (dt_util.now().timestamp() - self._is_on_timestamp) < self._active_seconds:
            # The state should stay "on" for the active duration.
            return True

        for alert in self.coordinator.data.active_alerts:
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
                for alert in self.coordinator.data.active_alerts
                if self.is_selected_area(alert)
            ],
            **(
                {
                    ATTR_SELECTED_AREAS_ALERTS: [
                        alert
                        for alert in self.coordinator.data.alerts
                        if self.is_selected_area(alert)
                    ],
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_SELECTED_AREAS_UPDATES: [
                alert
                for alert in self.coordinator.data.updates
                if self.is_selected_area(alert)
            ],
            ATTR_COUNTRY_ACTIVE_ALERTS: self.coordinator.data.active_alerts,
            **(
                {
                    ATTR_COUNTRY_ALERTS: self.coordinator.data.alerts,
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_COUNTRY_UPDATES: self.coordinator.data.updates,
        }

    def get_sensor_key(self) -> str:
        """Get the key of the extra sensor."""
        return self._sensor_key


class AlertSensorAllAreas(AlertSensorBase):
    """Representation of the alert sensor for all areas."""

    _attr_translation_key = "all_areas"

    def __init__(
        self,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._attr_unique_id = f"{OREF_ALERT_UNIQUE_ID}_{ALL_AREAS_ID_SUFFIX}"
        self.entity_id = f"{Platform.BINARY_SENSOR}.{self._attr_unique_id}"

    @property
    def is_on(self) -> bool:
        """Return True is sensor is on."""
        return len(self.coordinator.data.active_alerts) > 0

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            **self._common_attributes,
            ATTR_COUNTRY_ACTIVE_ALERTS: self.coordinator.data.active_alerts,
            **(
                {
                    ATTR_COUNTRY_ALERTS: self.coordinator.data.alerts,
                }
                if self._add_all_alerts_attributes
                else {}
            ),
            ATTR_COUNTRY_UPDATES: self.coordinator.data.updates,
        }
