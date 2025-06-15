"""Support for representing daily schedule as binary sensors."""

from __future__ import annotations

from abc import abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES

from .const import (
    ATTR_ALERT,
    ATTR_AREA,
    ATTR_DISPLAY,
    ATTR_TIME_TO_SHELTER,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DATA_COORDINATOR,
    END_TIME_ID_SUFFIX,
    END_TIME_NAME_SUFFIX,
    IST,
    TIME_TO_SHELTER_ID_SUFFIX,
    TIME_TO_SHELTER_NAME_SUFFIX,
    TITLE,
)
from .coordinator import OrefAlertCoordinatorData, OrefAlertDataUpdateCoordinator
from .metadata.area_to_migun_time import AREA_TO_MIGUN_TIME
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

SECONDS_IN_A_MINUTE = 60


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator = config_entry.runtime_data[DATA_COORDINATOR]
    entities = [
        (name, areas[0])
        for name, areas in [
            (TITLE, config_entry.options[CONF_AREAS]),
            *list(config_entry.options.get(CONF_SENSORS, {}).items()),
        ]
        if len(areas) == 1 and areas[0] in AREAS
    ]
    async_add_entities(
        [
            TimeToShelterSensor(name, area, coordinator, config_entry)
            for name, area in entities
        ]
        + [
            AlertEndTimeSensor(name, area, coordinator, config_entry)
            for name, area in entities
        ]
    )


class OrefAlertTimerSensor(
    CoordinatorEntity[OrefAlertDataUpdateCoordinator], SensorEntity
):
    """Representation of a timer sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(
        self,
        area: str,
        coordinator: OrefAlertDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(coordinator)
        self._data: OrefAlertCoordinatorData = coordinator.data
        self._config_entry = config_entry
        self._active_duration: int = config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        self._area: str = area
        self._alert: dict[str, Any] | None = None
        self._alert_timestamp: float | None = None
        self._unsub_update: Callable[[], None] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the data from the coordinator."""
        self._data = self.coordinator.data
        super()._handle_coordinator_update()

    def _get_alert(self) -> dict[str, Any] | None:
        """Return the latest active alert in the area."""
        if self._alert_timestamp is not None:
            if (
                dt_util.now().timestamp() - self._alert_timestamp
            ) < self._active_duration * 60:
                return self._alert
            self._alert = None
            self._alert_timestamp = None
        for alert in self._data.active_alerts:
            if alert["data"] == self._area or alert["data"] in ALL_AREAS_ALIASES:
                if not self.coordinator.is_synthetic_alert(alert):
                    self._alert = alert
                    self._alert_timestamp = (
                        dt_util.parse_datetime(alert["alertDate"], raise_on_error=True)
                        .replace(tzinfo=IST)
                        .timestamp()
                    )
                return alert
        return None

    def _get_alert_timestamp(self) -> float | None:
        """Return the timestamp of the latest active alert in the area."""
        return self._alert_timestamp if self._get_alert() else None

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._clean_up_listener()

    def _clean_up_listener(self) -> None:
        """Remove the update timer."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

    @callback
    async def _async_update(self, *_: Any) -> None:
        """Update the state."""
        self.async_write_ha_state()

    def _update_in_1_second(self) -> None:
        """Schedule next update in 1 second."""
        self._clean_up_listener()
        self._unsub_update = event_helper.async_track_point_in_time(
            self.hass,
            self._async_update,
            dt_util.now() + timedelta(seconds=1),
        )

    @abstractmethod
    def oref_value_seconds(self) -> int | None:
        """Abstract method for getting the state's value in seconds."""

    @property
    def native_value(self) -> int | None:
        """Return the value and schedule another update when needed."""
        if seconds := self.oref_value_seconds():
            self._update_in_1_second()
        return seconds

    def oref_display_value(self) -> str | None:
        """Return the state as mm:ss."""
        if (seconds := self.oref_value_seconds()) is None:
            return None
        sign = "-" if seconds < 0 else ""
        seconds = abs(seconds)
        return (
            f"{sign}{seconds // SECONDS_IN_A_MINUTE:02}:"
            f"{seconds % SECONDS_IN_A_MINUTE:02}"
        )


class TimeToShelterSensor(OrefAlertTimerSensor):
    """Representation of the time to shelter sensor."""

    _entity_component_unrecorded_attributes = frozenset(
        {
            ATTR_AREA,
            ATTR_TIME_TO_SHELTER,
            ATTR_ALERT,
            ATTR_DISPLAY,
        }
    )

    def __init__(
        self,
        name: str,
        area: str,
        coordinator: OrefAlertDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(area, coordinator, config_entry)
        self._migun_time: int = AREA_TO_MIGUN_TIME[area]
        self._attr_name = f"{name} {TIME_TO_SHELTER_NAME_SUFFIX}"
        self._attr_unique_id = (
            f"{name.lower().replace(' ', '_')}_{TIME_TO_SHELTER_ID_SUFFIX}"
        )

    def oref_value_seconds(self) -> int | None:
        """Return the remaining seconds to shelter."""
        if alert_timestamp := self._get_alert_timestamp():
            alert_age = dt_util.now().timestamp() - alert_timestamp
            time_to_shelter = int(self._migun_time - alert_age)
            # Count till "-60" (a minute past the time to shelter).
            if time_to_shelter > -1 * SECONDS_IN_A_MINUTE:
                return time_to_shelter
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            ATTR_AREA: self._area,
            ATTR_TIME_TO_SHELTER: self._migun_time,
            ATTR_ALERT: self._get_alert(),
            ATTR_DISPLAY: self.oref_display_value(),
        }


class AlertEndTimeSensor(OrefAlertTimerSensor):
    """Representation of the alert end time sensor."""

    _entity_component_unrecorded_attributes = frozenset(
        {
            ATTR_AREA,
            CONF_ALERT_ACTIVE_DURATION,
            ATTR_ALERT,
            ATTR_DISPLAY,
        }
    )

    def __init__(
        self,
        name: str,
        area: str,
        coordinator: OrefAlertDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(area, coordinator, config_entry)
        self._attr_name = f"{name} {END_TIME_NAME_SUFFIX}"
        self._attr_unique_id = f"{name.lower().replace(' ', '_')}_{END_TIME_ID_SUFFIX}"

    def oref_value_seconds(self) -> int | None:
        """Return the remaining seconds till the end of the alert."""
        if alert_timestamp := self._get_alert_timestamp():
            alert_age = dt_util.now().timestamp() - alert_timestamp
            return int(self._active_duration * 60 - alert_age)
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            ATTR_AREA: self._area,
            CONF_ALERT_ACTIVE_DURATION: self._active_duration,
            ATTR_ALERT: self._get_alert(),
            ATTR_DISPLAY: self.oref_display_value(),
        }
