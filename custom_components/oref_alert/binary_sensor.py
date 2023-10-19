"""Support for representing daily schedule as binary sensors."""
from __future__ import annotations

from datetime import timedelta
from typing import Any
import zoneinfo

from collections.abc import Mapping
import aiohttp

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .const import (
    CONF_AREAS,
    CONF_ALERT_MAX_AGE,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    DEFAULT_OFF_ICON,
    DEFAULT_ON_ICON,
)

SCAN_INTERVAL = timedelta(seconds=2)

OREF_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
IST = zoneinfo.ZoneInfo("Asia/Jerusalem")


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    async_add_entities([AlertSenosr(config_entry)])


class AlertSenosr(BinarySensorEntity):
    """Representation of the alert sensor."""

    _attr_has_entity_name = True
    _attr_name = "Oref Alert"
    _attr_unique_id = "oref_alert"
    _entity_component_unrecorded_attributes = frozenset(
        {
            ATTR_COUNTRY_ACTIVE_ALERTS,
            ATTR_COUNTRY_ALERTS,
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
            ATTR_SELECTED_AREAS_ALERTS,
            CONF_AREAS,
            CONF_ALERT_MAX_AGE,
        }
    )

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize object with defaults."""
        self._config_entry = config_entry
        self._on_icon = self._config_entry.options.get(CONF_ON_ICON, DEFAULT_ON_ICON)
        self._off_icon = self._config_entry.options.get(CONF_OFF_ICON, DEFAULT_OFF_ICON)
        self._http_client = aiohttp.ClientSession(raise_for_status=True)
        self._alerts = []

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        await self._http_client.close()

    @property
    def is_on(self) -> bool:
        """Return True is sensor is on."""
        for alert in self._alerts:
            if self.is_selected_area(alert) and self.is_active(alert):
                return True
        return False

    @property
    def icon(self):
        """Return the sensor icon."""
        return self._on_icon if self.is_on else self._off_icon

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return additional attributes."""
        selected_areas_alerts = [
            alert for alert in self._alerts if self.is_selected_area(alert)
        ]
        return {
            CONF_AREAS: self._config_entry.options[CONF_AREAS],
            CONF_ALERT_MAX_AGE: self._config_entry.options[CONF_ALERT_MAX_AGE],
            ATTR_SELECTED_AREAS_ACTIVE_ALERTS: [
                alert for alert in selected_areas_alerts if self.is_active(alert)
            ],
            ATTR_SELECTED_AREAS_ALERTS: selected_areas_alerts,
            ATTR_COUNTRY_ACTIVE_ALERTS: [
                alert for alert in self._alerts if self.is_active(alert)
            ],
            ATTR_COUNTRY_ALERTS: self._alerts,
        }

    def is_active(self, alert: dict[str, str]) -> bool:
        """Check the age of the alert."""
        return dt_util.parse_datetime(alert["alertDate"]).replace(
            tzinfo=IST
        ).timestamp() > dt_util.now().timestamp() - (
            self._config_entry.options[CONF_ALERT_MAX_AGE] * 60
        )

    def is_selected_area(self, alert: dict[str, str]) -> bool:
        """Check is the alert is among the selected areas."""
        return alert["data"] in self._config_entry.options[CONF_AREAS]

    async def async_update(self) -> None:
        """Update entity."""
        async with self._http_client.get(OREF_URL, headers=OREF_HEADERS) as response:
            if response.content_length > 5:
                self._alerts = await response.json()
            else:
                self._alerts = []
