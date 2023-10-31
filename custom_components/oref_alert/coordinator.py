"""DataUpdateCoordinator for oref_alert integration."""
import asyncio
from dataclasses import dataclass
from datetime import timedelta
from functools import cmp_to_key
from json import JSONDecodeError
from typing import Any

from aiohttp.client_exceptions import ContentTypeError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import (
    CONF_ALERT_MAX_AGE,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    IST,
    LOGGER,
)
from .metadata.areas import AREAS

OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HISTORY_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
REQUEST_RETRIES = 3
REAL_TIME_ALERT_LOGIC_WINDOW = 2


@dataclass
class OrefAlertCoordinatorData:
    """Class for holding coordinator data."""

    alerts: list[Any]
    active_alerts: list[Any]


def _sort_alerts(item1: dict[str, Any], item2: dict[str, Any]) -> int:
    """Sort by descending-order "date" and then ascending-order "name"."""
    if item1["alertDate"] < item2["alertDate"]:
        return 1
    if item1["alertDate"] > item2["alertDate"]:
        return -1
    if item1["data"] > item2["data"]:
        return 1
    if item1["data"] < item2["data"]:
        return -1
    return 0


def _compare_fields(alert: dict[str, Any], area: str, catgoery: int) -> bool:
    """Compare an alert with area and category (time is ignored)."""
    return alert["data"] == area and alert["category"] == catgoery


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Oref Alert data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """Initialize global data updater."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=config_entry.options.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                )
            ),
        )
        self._config_entry = config_entry
        self._http_client = async_get_clientsession(hass)

    async def _async_update_data(self) -> OrefAlertCoordinatorData:
        """Request the data from Oref servers.."""
        current, history = await asyncio.gather(
            *[self._async_fetch_url(url) for url in (OREF_ALERTS_URL, OREF_HISTORY_URL)]
        )
        history = history or []
        alerts = self._current_to_history_format(current, history) if current else []
        alerts.extend(history)
        alerts.sort(key=cmp_to_key(_sort_alerts))
        for unrecognized_area in {alert["data"] for alert in alerts}.difference(AREAS):
            LOGGER.error("Alert has an unrecognized area: %s", unrecognized_area)
        return OrefAlertCoordinatorData(alerts, self._active_alerts(alerts))

    async def _async_fetch_url(self, url: str) -> Any:
        """Fetch data from Oref servers."""
        exc_info = None
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.get(url, headers=OREF_HEADERS) as response:
                    try:
                        return await response.json(encoding="utf-8-sig")
                    except (JSONDecodeError, ContentTypeError):
                        # Empty file is a valid return but not a valid JSON file
                        return None
            except Exception as ex:  # pylint: disable=broad-except
                exc_info = ex
        LOGGER.warning(
            "Update failed after %d retries", REQUEST_RETRIES, exc_info=exc_info
        )
        raise exc_info

    def _current_to_history_format(
        self, current: dict[str, Any], history: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Convert current alerts payload to history format."""
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        category = int(current["cat"])
        history_last_minute_alerts = self._recent_alerts(
            history, REAL_TIME_ALERT_LOGIC_WINDOW
        )
        previous_last_minute_alerts = (
            self._recent_alerts(self.data.active_alerts, REAL_TIME_ALERT_LOGIC_WINDOW)
            if self.data
            else []
        )
        alerts = []
        for area in current["data"]:
            for history_recent_alert in history_last_minute_alerts:
                if _compare_fields(history_recent_alert, area, category):
                    # The alert is already in the history list. No need to add it twice.
                    break
            else:
                for previous_recent_alert in previous_last_minute_alerts:
                    if _compare_fields(previous_recent_alert, area, category):
                        # The alert was already added, so take the original timestamp.
                        alerts.append(previous_recent_alert)
                        break
                else:
                    alerts.append(
                        {
                            "alertDate": now,
                            "title": current["title"],
                            "data": area,
                            "category": category,
                        }
                    )
        return alerts

    def _active_alerts(self, alerts: list[Any]) -> list[Any]:
        """Return the list of active alerts."""
        return self._recent_alerts(
            alerts, self._config_entry.options[CONF_ALERT_MAX_AGE]
        )

    def _recent_alerts(self, alerts: list[Any], max_age: int) -> list[Any]:
        """Return the list of recent alerts."""
        earliest_alert = dt_util.now().timestamp() - max_age * 60
        return [
            alert
            for alert in alerts
            if dt_util.parse_datetime(alert["alertDate"])
            .replace(tzinfo=IST)
            .timestamp()
            > earliest_alert
        ]
