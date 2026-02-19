"""Support for representing oref alert as sensors."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any, Final

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.const import STATE_OK, Platform, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.util import slugify

from custom_components.oref_alert.records_schema import RecordType

from .const import (
    ATTR_ALERT,
    ATTR_AREA,
    ATTR_DISPLAY,
    ATTR_RECORD,
    ATTR_TIME_TO_SHELTER,
    CONF_AREAS,
    CONF_SENSORS,
    OREF_ALERT_UNIQUE_ID,
    TIME_TO_SHELTER_ID_SUFFIX,
)
from .entity import OrefAlertCoordinatorEntity
from .metadata.area_to_migun_time import AREA_TO_MIGUN_TIME
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry

PARALLEL_UPDATES: Final = 0
SECONDS_IN_A_MINUTE: Final = 60


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
        + [OrefAlertStatusSensor(name, area, config_entry) for name, area in entities]
    )


class TimeToShelterSensor(OrefAlertCoordinatorEntity, SensorEntity):
    """Representation of a timer sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_translation_key = "timer"

    _unrecorded_attributes = frozenset(
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
        super().__init__(config_entry)
        self._area: str = area
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
        self._unsub_update: Callable[[], None] | None = None

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

    def oref_value_seconds(self) -> int | None:
        """Return the remaining seconds to shelter."""
        if (
            alert := self.coordinator.data.areas.get(self._area)
        ) and alert.record_type == RecordType.ALERT:
            alert_age = (dt_util.now() - alert.time).total_seconds()
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
            ATTR_ALERT: self.coordinator.get_record(self._area, {RecordType.ALERT}),
            ATTR_DISPLAY: self.oref_display_value(),
        }


class OrefAlertStatusSensor(OrefAlertCoordinatorEntity, SensorEntity):
    """Representation of a status sensor."""

    _unrecorded_attributes = frozenset({ATTR_AREA, ATTR_RECORD})
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "status"

    def __init__(
        self,
        name: str,
        area: str,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._area: str = area
        self._attr_options = [STATE_OK, RecordType.PRE_ALERT, RecordType.ALERT]
        if not name:
            self.use_device_name = True
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
        else:
            self._attr_name = name
            self._attr_unique_id = slugify(
                f"{OREF_ALERT_UNIQUE_ID}_{name.lower().replace(' ', '_')}"
            )
        self.entity_id = f"{Platform.SENSOR}.{self._attr_unique_id}"

    @property
    def native_value(self) -> str:
        """Return the state value."""
        if (
            record := self.coordinator.data.areas.get(self._area)
        ) is not None and record.record_type in (
            RecordType.PRE_ALERT,
            RecordType.ALERT,
        ):
            return str(record.record_type)

        return STATE_OK

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            ATTR_AREA: self._area,
            ATTR_RECORD: self.coordinator.get_record(self._area, None),
        }
