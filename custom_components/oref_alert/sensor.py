"""Support for representing daily schedule as binary sensors."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from collections.abc import Callable, Mapping

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    DATA_COORDINATOR,
    IST,
    TITLE,
    ATTR_ALERT,
    CONF_AREAS,
    CONF_SENSORS,
    ATTR_AREA,
    ATTR_TIME_TO_SHELTER,
    TIME_TO_SHELTER_ID_SUFFIX,
    TIME_TO_SHELTER_NAME_SUFFIX,
)
from .coordinator import OrefAlertCoordinatorData, OrefAlertDataUpdateCoordinator
from .metadata.areas import AREAS
from .metadata.area_to_migun_time import AREA_TO_MIGUN_TIME


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        [
            TimeToShelterSensor(name, areas[0], coordinator)
            for name, areas in [(TITLE, config_entry.options[CONF_AREAS])]
            + list(config_entry.options.get(CONF_SENSORS, {}).items())
            if len(areas) == 1 and areas[0] in AREAS
        ]
    )


class TimeToShelterSensor(
    CoordinatorEntity[OrefAlertDataUpdateCoordinator], SensorEntity
):
    """Representation of the time to shelter sensor."""

    _attr_has_entity_name = True
    _entity_component_unrecorded_attributes = frozenset(
        {
            ATTR_AREA,
            ATTR_TIME_TO_SHELTER,
            ATTR_ALERT,
        }
    )
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-sand"

    def __init__(
        self,
        name: str,
        area: str,
        coordinator: OrefAlertDataUpdateCoordinator,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(coordinator)
        self._data: OrefAlertCoordinatorData = coordinator.data
        self._area: str = area
        self._migun_time: int = AREA_TO_MIGUN_TIME[area]
        self._attr_name = f"{name} {TIME_TO_SHELTER_NAME_SUFFIX}"
        self._attr_unique_id = (
            f"{name.lower().replace(' ', '_')}_" f"{TIME_TO_SHELTER_ID_SUFFIX}"
        )
        self._unsub_update: Callable[[], None] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the data from the coordinator."""
        self._data = self.coordinator.data
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> int | None:
        """Return the remaning seconds to shelter."""
        if alert := self._get_alert():
            alert_timestamp = (
                dt_util.parse_datetime(alert["alertDate"])
                .replace(tzinfo=IST)
                .timestamp()
            )
            alert_age = dt_util.now().timestamp() - alert_timestamp
            time_to_shelter = int(self._migun_time - alert_age)
            # Count till "-60" (a minute past the time to shelter).
            if time_to_shelter > -60:
                self._update_in_1_second()
                return time_to_shelter
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        return {
            ATTR_AREA: self._area,
            ATTR_TIME_TO_SHELTER: self._migun_time,
            ATTR_ALERT: self._get_alert(),
        }

    def _get_alert(self) -> dict[str, Any] | None:
        """Return the latest active alert in the area."""
        for alert in self._data.active_alerts:
            if alert["data"] == self._area:
                return alert
        return None

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._clean_up_listener()

    def _clean_up_listener(self):
        """Remove the update timer."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

    @callback
    async def _async_update(self, *_) -> None:
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
