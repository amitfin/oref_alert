"""Support for representing oref alert as sensors."""

from __future__ import annotations

from abc import abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import Platform, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.util import slugify

from .const import (
    AREA_FIELD,
    ATTR_ALERT,
    ATTR_AREA,
    ATTR_DISPLAY,
    ATTR_TIME_TO_SHELTER,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DATE_FIELD,
    END_TIME_ID_SUFFIX,
    IST,
    OREF_ALERT_UNIQUE_ID,
    TIME_TO_SHELTER_ID_SUFFIX,
    AlertType,
)
from .entity import OrefAlertCoordinatorEntity
from .metadata import ALL_AREAS_ALIASES
from .metadata.area_to_migun_time import AREA_TO_MIGUN_TIME
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry

PARALLEL_UPDATES = 0

SECONDS_IN_A_MINUTE = 60


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: OrefAlertConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    entities = [
        (name, areas[0])
        for name, areas in [
            ("", config_entry.options[CONF_AREAS]),
            *list(config_entry.options.get(CONF_SENSORS, {}).items()),
        ]
        if len(areas) == 1 and areas[0] in AREAS
    ]
    async_add_entities(
        [TimeToShelterSensor(name, area, config_entry) for name, area in entities]
        + [AlertEndTimeSensor(name, area, config_entry) for name, area in entities]
    )


class OrefAlertTimerSensor(OrefAlertCoordinatorEntity, SensorEntity):
    """Representation of a timer sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_translation_key = "timer"

    def __init__(
        self,
        area: str,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._active_duration: int = config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        self._area: str = area
        self._alert: AlertType | None = None
        self._alert_timestamp: float | None = None
        self._unsub_update: Callable[[], None] | None = None

    def _get_alert(self) -> AlertType | None:
        """Return the latest active alert in the area."""
        if self._alert_timestamp is not None:
            if (
                dt_util.now().timestamp() - self._alert_timestamp
            ) < self._active_duration * 60:
                return self._alert
            self._alert = None
            self._alert_timestamp = None
        for alert in self.coordinator.data.active_alerts:
            if (
                alert[AREA_FIELD] == self._area
                or alert[AREA_FIELD] in ALL_AREAS_ALIASES
            ):
                if not self.coordinator.is_synthetic_alert(alert):
                    self._alert = alert
                    self._alert_timestamp = (
                        dt_util.parse_datetime(alert[DATE_FIELD], raise_on_error=True)
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
        if (seconds := self.oref_value_seconds()) is not None:
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
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(area, config_entry)
        self._migun_time: int = AREA_TO_MIGUN_TIME[area]
        if not name:
            self._attr_translation_key = "default_time_to_shelter"
            self._attr_unique_id = f"{OREF_ALERT_UNIQUE_ID}_{TIME_TO_SHELTER_ID_SUFFIX}"
        else:
            self._attr_translation_key = "named_time_to_shelter"
            self._attr_translation_placeholders = {"name": name}
            self._attr_unique_id = slugify(
                OREF_ALERT_UNIQUE_ID
                + f"_{name.lower().replace(' ', '_')}_"
                + TIME_TO_SHELTER_ID_SUFFIX
            )
        self.entity_id = f"{Platform.SENSOR}.{self._attr_unique_id}"

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
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(area, config_entry)
        if not name:
            self._attr_translation_key = "default_end_time"
            self._attr_unique_id = f"{OREF_ALERT_UNIQUE_ID}_{END_TIME_ID_SUFFIX}"
        else:
            self._attr_translation_key = "named_end_time"
            self._attr_translation_placeholders = {"name": name}
            self._attr_unique_id = slugify(
                OREF_ALERT_UNIQUE_ID
                + f"_{name.lower().replace(' ', '_')}_"
                + END_TIME_ID_SUFFIX
            )
        self.entity_id = f"{Platform.SENSOR}.{self._attr_unique_id}"

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
