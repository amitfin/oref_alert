"""DataUpdateCoordinator for oref_alert integration."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from functools import cmp_to_key
from http import HTTPStatus
from json import JSONDecodeError
from typing import Any

import homeassistant.util.dt as dt_util
from aiohttp.client_exceptions import ContentTypeError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_CATEGORY,
    ATTR_TITLE,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREA,
    CONF_DURATION,
    CONF_POLL_INTERVAL,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    IST,
    LOGGER,
)
from .metadata.areas import AREAS

OREF_ALERTS_URL = "https://www.oref.org.il/warningMessages/alert/Alerts.json"
OREF_HISTORY_URL = (
    "https://www.oref.org.il/warningMessages/alert/History/AlertsHistory.json"
)

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
    result = 0
    if item1["alertDate"] < item2["alertDate"]:
        result = 1
    elif item1["alertDate"] > item2["alertDate"]:
        result = -1
    elif item1["data"] > item2["data"]:
        result = 1
    elif item1["data"] < item2["data"]:
        result = -1
    return result


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertCoordinatorData]):
    """Class to manage fetching Oref Alert data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
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
        self._active_duration = config_entry.options.get(
            CONF_ALERT_ACTIVE_DURATION, DEFAULT_ALERT_ACTIVE_DURATION
        )
        self._http_client = async_get_clientsession(hass)
        self._http_cache = {}
        self._synthetic_alerts: dict[int, dict[str, Any]] = {}

    async def _async_update_data(self) -> OrefAlertCoordinatorData:
        """Request the data from Oref servers.."""
        (current, current_modified), (history, history_modified) = await asyncio.gather(
            *[self._async_fetch_url(url) for url in (OREF_ALERTS_URL, OREF_HISTORY_URL)]
        )
        if (
            current_modified
            or history_modified
            or not self.data
            or self._synthetic_alerts
        ):
            history = self._fix_areas_spelling(history) if history else []
            alerts = (
                self._current_to_history_format(current, history) if current else []
            )
            alerts.extend(history)
            alerts.extend(self._get_synthetic_alerts())
            alerts.sort(key=cmp_to_key(_sort_alerts))
            for unrecognized_area in {alert["data"] for alert in alerts}.difference(
                {alert["data"] for alert in getattr(self.data, "alerts", [])}
            ).difference(AREAS):
                LOGGER.error("Alert has an unrecognized area: %s", unrecognized_area)
        else:
            alerts = self.data.alerts
        return OrefAlertCoordinatorData(alerts, self._active_alerts(alerts))

    async def _async_fetch_url(self, url: str) -> tuple[Any, bool]:
        """Fetch data from Oref servers."""
        exc_info = Exception()
        cached_content, last_modified = self._http_cache.get(url, (None, None))
        headers = (
            OREF_HEADERS
            if not last_modified
            else {"If-Modified-Since": last_modified, **OREF_HEADERS}
        )
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.get(url, headers=headers) as response:
                    if response.status == HTTPStatus.NOT_MODIFIED:
                        return cached_content, False
                    try:
                        content = await response.json(encoding="utf-8-sig")
                    except (JSONDecodeError, ContentTypeError):
                        # Empty file is a valid return but not a valid JSON file
                        content = None
                    self._http_cache[url] = (
                        content,
                        response.headers.get("Last-Modified"),
                    )
                    return content, not (content is None and cached_content is None)
            except Exception as ex:  # noqa: BLE001
                exc_info = ex
        raise exc_info

    def _current_to_history_format(
        self, current: dict[str, Any], history: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        """Convert current alerts payload to history format."""
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        history_last_minute_alerts = self._recent_alerts(
            history, REAL_TIME_ALERT_LOGIC_WINDOW
        )
        previous_last_minute_alerts = (
            self._recent_alerts(self.data.active_alerts, REAL_TIME_ALERT_LOGIC_WINDOW)
            if self.data
            else []
        )
        alerts = []
        for alert_area in current["data"]:
            area = self._fix_area_spelling(alert_area)
            for history_recent_alert in history_last_minute_alerts:
                if history_recent_alert["data"] == area:
                    # The alert is already in the history list. No need to add it twice.
                    break
            else:
                for previous_recent_alert in previous_last_minute_alerts:
                    if previous_recent_alert["data"] == area:
                        # The alert was already added, so take the original timestamp.
                        alerts.append(previous_recent_alert)
                        break
                else:
                    alerts.append(
                        {
                            "alertDate": now,
                            ATTR_TITLE: current[ATTR_TITLE],
                            "data": area,
                            ATTR_CATEGORY: int(current["cat"]),
                        }
                    )
        return alerts

    def _active_alerts(self, alerts: list[Any]) -> list[Any]:
        """Return the list of active alerts."""
        return self._recent_alerts(alerts, self._active_duration)

    def _recent_alerts(self, alerts: list[Any], active_duration: int) -> list[Any]:
        """Return the list of recent alerts, assuming the input is sorted."""
        earliest_alert = dt_util.now().timestamp() - active_duration * 60
        recent_alerts = []
        for alert in alerts:
            if (
                alert_date := dt_util.parse_datetime(alert["alertDate"])
            ) is not None and alert_date.replace(
                tzinfo=IST
            ).timestamp() < earliest_alert:
                break
            recent_alerts.append(alert)
        return recent_alerts

    def add_synthetic_alert(self, details: dict) -> None:
        """Add a synthetic alert for testing purposes."""
        now = dt_util.now(IST)
        self._synthetic_alerts[int(now.timestamp()) + details[CONF_DURATION]] = {
            "alertDate": now.strftime("%Y-%m-%d %H:%M:%S"),
            ATTR_TITLE: details.get(ATTR_TITLE, "התרעה סינטטית לצורכי בדיקות"),
            "data": details[CONF_AREA],
            ATTR_CATEGORY: details[ATTR_CATEGORY],
        }

    def _get_synthetic_alerts(self) -> list[dict[str, Any]]:
        """Return the list of synthetic alerts."""
        now = dt_util.now().timestamp()
        for expired in [
            timestamp for timestamp in self._synthetic_alerts if timestamp < now
        ]:
            del self._synthetic_alerts[expired]
        return list(self._synthetic_alerts.values())

    def _fix_areas_spelling(self, alerts: list[Any]) -> list[Any]:
        """Fix spelling errors in area names."""
        for alert in alerts:
            alert["data"] = self._fix_area_spelling(alert["data"])
        return alerts

    def _fix_area_spelling(self, area: str) -> str:
        """Fix spelling error in area name."""
        if area[0] == "'":
            area = f"{area[1:]}'"
        return area
