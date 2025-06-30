"""DataUpdateCoordinator for oref_alert integration."""

import asyncio
import json
from datetime import datetime, timedelta
from functools import cmp_to_key
from http import HTTPStatus
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.oref_alert.categories import (
    category_is_alert,
    category_is_update,
    real_time_to_history_category,
)
from custom_components.oref_alert.ttl_deque import TTLDeque

from .const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREA,
    CONF_DURATION,
    CONF_POLL_INTERVAL,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    IST,
    LOGGER,
    AlertField,
    AlertSource,
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


def _is_update(alert: dict[str, Any]) -> bool:
    """Check if the alert is an update."""
    return category_is_update(alert["category"])


def _is_alert(alert: dict[str, Any]) -> bool:
    """Check if the alert is an alert."""
    return category_is_alert(alert["category"]) and not _is_update(alert)


class OrefAlertCoordinatorData:
    """Class for holding coordinator data."""

    def __init__(self, items: list[Any], active_duration: int) -> None:
        """Initialize the data."""
        self.items = items
        self.alerts = list(filter(lambda alert: _is_alert(alert), items))
        active_alerts = OrefAlertDataUpdateCoordinator.recent_alerts(
            items, active_duration
        )
        self.active_alerts = list(filter(lambda alert: _is_alert(alert), active_alerts))
        self.updates = list(filter(lambda alert: _is_update(alert), active_alerts))


def _sort_alerts(item1: dict[str, Any], item2: dict[str, Any]) -> int:
    """Sort by descending-order "date" and then ascending-order "name"."""
    result = 0
    if item1[AlertField.DATE] < item2[AlertField.DATE]:
        result = 1
    elif item1[AlertField.DATE] > item2[AlertField.DATE]:
        result = -1
    elif item1[AlertField.AREA] > item2[AlertField.AREA]:
        result = 1
    elif item1[AlertField.AREA] < item2[AlertField.AREA]:
        result = -1
    return result


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertCoordinatorData]):
    """Class to manage fetching Oref Alert data."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, channels: list[TTLDeque]
    ) -> None:
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
        self._all_alerts: bool = config_entry.options.get(
            CONF_ALL_ALERTS_ATTRIBUTES, False
        )
        self._http_client = async_get_clientsession(hass)
        self._http_cache = {}
        self._channels: list[TTLDeque] = channels
        self._channels_change: list[datetime | None] = []
        self._synthetic_alerts: list[tuple[float, dict[str, Any]]] = []

    async def _async_update_data(self) -> OrefAlertCoordinatorData:
        """Request the data from Oref servers.."""
        channels_change = [alerts.changed() for alerts in self._channels]
        (current, current_modified), (history, history_modified) = await asyncio.gather(
            *[
                self._async_fetch_url(url)
                for url in ((OREF_ALERTS_URL), (OREF_HISTORY_URL))
            ]
        )
        if (
            current_modified
            or history_modified
            or not self.data
            or (any(channels_change) and channels_change != self._channels_change)
            or self._synthetic_alerts
        ):
            history = history or []
            if not self._all_alerts:
                history = OrefAlertDataUpdateCoordinator.recent_alerts(
                    history, self._active_duration
                )
            history = self._process_history_alerts(history)
            alerts = (
                self._current_to_history_format(current, history) if current else []
            )
            alerts.extend(history)
            alerts.sort(key=cmp_to_key(_sort_alerts))
            self._add_channels(alerts)
            self._channels_change = channels_change
            alerts.extend(self._get_synthetic_alerts())
            alerts.sort(key=cmp_to_key(_sort_alerts))
            for unrecognized_area in {
                alert[AlertField.AREA] for alert in alerts
            }.difference(
                {alert[AlertField.AREA] for alert in getattr(self.data, "items", [])}
            ).difference(AREAS):
                LOGGER.error("Alert has an unrecognized area: %s", unrecognized_area)
        else:
            alerts = self.data.items
        return OrefAlertCoordinatorData(alerts, self._active_duration)

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
                    raw = await response.read()
                    text = raw.decode("utf-8-sig").strip()
                    content = None if not text else json.loads(text)
                    self._http_cache[url] = (
                        content,
                        response.headers.get("Last-Modified"),
                    )
                    return content, not (content is None and cached_content is None)
            except Exception as ex:  # noqa: BLE001
                exc_info = ex
        if url in self._http_cache:
            # Return the cached content if available to prevent entities unavailability.
            LOGGER.info(
                "Failed to fetch '%s'. Using the cached content.",
                url,
                exc_info=exc_info,
            )
            return cached_content, False
        LOGGER.error("Failed to fetch '%s'", url)
        raise exc_info

    def _current_to_history_format(
        self, current: dict[str, Any], history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert current alerts payload to history format."""
        if (category := real_time_to_history_category(int(current["cat"]))) is None:
            # Unknown category. Wait for the history to include it.
            return []
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        history_recent_alerts = self.recent_alerts(
            history, REAL_TIME_ALERT_LOGIC_WINDOW
        )
        previous_recent_alerts = (
            self.recent_alerts(self.data.items, REAL_TIME_ALERT_LOGIC_WINDOW)
            if self.data
            else []
        )
        alerts = []
        for alert_area in current[AlertField.AREA]:
            area = self._fix_area_spelling(alert_area)
            for history_recent_alert in history_recent_alerts:
                if history_recent_alert[AlertField.AREA] == area:
                    # The alert is already in the history list. No need to add it twice.
                    break
            else:
                for previous_recent_alert in previous_recent_alerts:
                    if previous_recent_alert[AlertField.AREA] == area:
                        # The alert was already added, so take the original timestamp.
                        alerts.append(previous_recent_alert)
                        break
                else:
                    alerts.append(
                        {
                            AlertField.DATE: now,
                            AlertField.TITLE: current[AlertField.TITLE],
                            AlertField.AREA: area,
                            AlertField.CATEGORY: category,
                            AlertField.CHANNEL: AlertSource.WEBSITE,
                        }
                    )
        return alerts

    def _add_channels(self, alerts: list[dict[str, Any]]) -> None:
        """Add alerts from the different channels after de-dup."""
        dedup_window = REAL_TIME_ALERT_LOGIC_WINDOW * 60
        new_alerts = []
        for channel in self._channels:
            if channel.changed() is None:
                continue

            if new_alerts:  # From the previous iteration of this loop.
                alerts.sort(key=cmp_to_key(_sort_alerts))

            # Channel data only exists for active duration, so this is the de-dup window
            exist_alerts = (
                self.recent_alerts(alerts, self._active_duration)
                if self._all_alerts
                else alerts  # It already includes only active alerts.
            )

            new_alerts = []
            for alert in channel.items():
                alert_timestamp = self._alert_timestamp(alert)
                to_add = True
                for exist_alert in exist_alerts:
                    if (
                        alert[AlertField.AREA] == exist_alert[AlertField.AREA]
                        and alert[AlertField.CATEGORY]
                        == exist_alert[AlertField.CATEGORY]
                    ):
                        # We only de-dup alerts with the same area and category.
                        exist_timestamp = self._alert_timestamp(exist_alert)
                        if abs(alert_timestamp - exist_timestamp) < dedup_window:
                            # There is a similar alert within the window.
                            to_add = False
                            break
                        if alert_timestamp - exist_timestamp > dedup_window:
                            # exist_timestamp is decreasing so the delta is increasing
                            break
                if to_add:
                    new_alerts.append(alert)
            if new_alerts:
                alerts.extend(new_alerts)

    @staticmethod
    def _alert_timestamp(alert: dict) -> float:
        """Return alert's timestamp."""
        return (
            dt_util.parse_datetime(alert[AlertField.DATE], raise_on_error=True)
            .replace(tzinfo=IST)
            .timestamp()
        )

    @classmethod
    def recent_alerts(cls, alerts: list[Any], active_duration: int) -> list[Any]:
        """Return the list of recent alerts, assuming the input is sorted."""
        earliest_alert = dt_util.now().timestamp() - active_duration * 60
        recent_alerts = []
        for alert in alerts:
            if cls._alert_timestamp(alert) < earliest_alert:
                break
            recent_alerts.append(alert)
        return recent_alerts

    def add_synthetic_alert(self, details: dict) -> None:
        """Add a synthetic alert for testing purposes."""
        now = dt_util.now(IST)
        for area in details[CONF_AREA]:
            self._synthetic_alerts.append(
                (
                    now.timestamp() + details[CONF_DURATION],
                    {
                        AlertField.DATE: now.strftime("%Y-%m-%d %H:%M:%S"),
                        AlertField.TITLE: details.get(
                            AlertField.TITLE, "התרעה סינטטית לצורכי בדיקות"
                        ),
                        AlertField.AREA: area,
                        AlertField.CATEGORY: details[AlertField.CATEGORY],
                        AlertField.CHANNEL: AlertSource.SYNTHETIC,
                    },
                )
            )

    def _get_synthetic_alerts(self) -> list[dict[str, Any]]:
        """Return the list of synthetic alerts."""
        now = dt_util.now().timestamp()
        self._synthetic_alerts = [
            (expired, alert)
            for expired, alert in self._synthetic_alerts
            if expired >= now
        ]
        return [alert for _, alert in self._synthetic_alerts]

    def is_synthetic_alert(self, alert: dict[str, Any]) -> bool:
        """Check if the alert is a synthetic alert."""
        return alert.get(AlertField.CHANNEL) == AlertSource.SYNTHETIC

    def _process_history_alerts(self, alerts: list[Any]) -> list[dict[str, Any]]:
        """Add channel field and fix spelling errors in area names."""
        for alert in alerts:
            alert[AlertField.CHANNEL] = AlertSource.HISTORY
            alert[AlertField.AREA] = self._fix_area_spelling(alert[AlertField.AREA])
        return alerts

    def _fix_area_spelling(self, area: str) -> str:
        """Fix spelling error in area name."""
        if area[0] == "'":
            area = f"{area[1:]}'"
        return area
