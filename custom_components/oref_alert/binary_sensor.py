"""Support for representing daily schedule as binary sensors."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from json import JSONDecodeError
from typing import Any
import zoneinfo

from collections.abc import Callable, Mapping

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.dt as dt_util

from .area_utils import expand_areas_and_groups
from .const import (
    CONF_AREAS,
    CONF_ALERT_MAX_AGE,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_POLL_INTERVAL,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_COUNTRY_ALERTS,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    DEFAULT_OFF_ICON,
    DEFAULT_ON_ICON,
    DEFAULT_POLL_INTERVAL,
    LOGGER,
    OREF_ALERT_UNIQUE_ID,
)

OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HISTORY_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
IST = zoneinfo.ZoneInfo("Asia/Jerusalem")
UPDATE_RETRIES = 3


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    async_add_entities([AlertSenosr(hass, config_entry)])


class AlertSenosr(BinarySensorEntity):
    """Representation of the alert sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Oref Alert"
    _attr_unique_id = OREF_ALERT_UNIQUE_ID
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

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize object with defaults."""
        self._config_entry = config_entry
        self._areas = expand_areas_and_groups(self._config_entry.options[CONF_AREAS])
        self._on_icon = self._config_entry.options.get(CONF_ON_ICON, DEFAULT_ON_ICON)
        self._off_icon = self._config_entry.options.get(CONF_OFF_ICON, DEFAULT_OFF_ICON)
        self._poll_interval = self._config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )
        self._http_client = async_get_clientsession(hass)
        self._alerts = []
        self._unsub_update: Callable[[], None] | None = None

    async def _async_fetch_url(self, url: str) -> Any:
        """Fetch data from Oref servers."""
        async with self._http_client.get(url, headers=OREF_HEADERS) as response:
            try:
                return await response.json(encoding="utf-8-sig")
            except JSONDecodeError:
                # Empty file is a valid return but not a valid JSON file
                return None

    async def _async_update(self) -> None:
        """Request the data and update the entity."""
        current, history = await asyncio.gather(
            *[self._async_fetch_url(url) for url in (OREF_ALERTS_URL, OREF_HISTORY_URL)]
        )
        self._alerts = self._current_to_history_format(current) if current else []
        self._alerts.extend(history or [])
        self._alerts.sort(reverse=True, key=lambda alert: alert["alertDate"])
        self.async_write_ha_state()

    def _current_to_history_format(
        self, current: dict[str, str]
    ) -> list[dict[str, str]]:
        """Convert current alerts payload to history format."""
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        return [
            {
                "alertDate": now,
                "title": current["title"],
                "data": data,
                "category": current["cat"],
            }
            for data in current["data"]
        ]

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
            CONF_AREAS: self._areas,
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
        return alert["data"] in self._areas

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        await self._async_update_and_schedule()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        self._clean_up_listener()

    def _clean_up_listener(self):
        """Remove the update timer."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

    async def _async_update_and_schedule(self, *_) -> None:
        """Update entity and schedule next update."""
        self._clean_up_listener()
        exc_info = None
        for _ in range(UPDATE_RETRIES):
            try:
                await self._async_update()
                break
            except Exception as ex:  # pylint: disable=broad-except
                # An update error shouldn't stop the polling
                exc_info = ex
        else:
            LOGGER.warning(
                "Update failed after %d retries", UPDATE_RETRIES, exc_info=exc_info
            )
        self._unsub_update = event_helper.async_track_point_in_time(
            self.hass,
            self._async_update_and_schedule,
            dt_util.now() + timedelta(seconds=self._poll_interval),
        )
