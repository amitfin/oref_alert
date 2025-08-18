"""DataUpdateCoordinator for oref_alert integration."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from functools import cmp_to_key
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.core import callback
from homeassistant.helpers import event as event_helper
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .categories import (
    category_is_alert,
    category_is_update,
    real_time_to_history_category,
)
from .const import (
    AREA_FIELD,
    CATEGORY_FIELD,
    CHANNEL_FIELD,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREA,
    CONF_DURATION,
    DATE_FIELD,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DOMAIN,
    IST,
    LOGGER,
    TITLE_FIELD,
    AlertSource,
    AlertType,
)
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry
    from .ttl_deque import TTLDeque

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
REQUEST_THROTTLING = 0.8
REAL_TIME_ALERT_LOGIC_WINDOW = 2


def _is_update(alert: AlertType) -> bool:
    """Check if the alert is an update."""
    return category_is_update(alert["category"])


def _is_alert(alert: AlertType) -> bool:
    """Check if the alert is an alert."""
    return category_is_alert(alert["category"]) and not _is_update(alert)


class OrefAlertCoordinatorData:
    """Class for holding coordinator data."""

    def __init__(self, items: list[AlertType], active_duration: int) -> None:
        """Initialize the data."""
        self.items: list[AlertType] = items
        self.alerts: list[AlertType] = list(
            filter(lambda alert: _is_alert(alert), items)
        )
        active_alerts: list[AlertType] = OrefAlertDataUpdateCoordinator.recent_alerts(
            items, active_duration
        )
        self.active_alerts: list[AlertType] = list(
            filter(lambda alert: _is_alert(alert), active_alerts)
        )
        self.updates: list[AlertType] = list(
            filter(lambda alert: _is_update(alert), active_alerts)
        )


def _sort_alerts(item1: AlertType, item2: AlertType) -> int:
    """Sort by descending-order "date" and then ascending-order "name"."""
    result = 0
    if item1[DATE_FIELD] < item2[DATE_FIELD]:
        result = 1
    elif item1[DATE_FIELD] > item2[DATE_FIELD]:
        result = -1
    elif item1[AREA_FIELD] > item2[AREA_FIELD]:
        result = 1
    elif item1[AREA_FIELD] < item2[AREA_FIELD]:
        result = -1
    return result


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator[OrefAlertCoordinatorData]):
    """Class to manage fetching Oref Alert data."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
        channels: list[TTLDeque],
    ) -> None:
        """Initialize global data updater."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
        )
        self._active_duration = config_entry.options.get(
            CONF_ALERT_ACTIVE_DURATION, DEFAULT_ALERT_ACTIVE_DURATION
        )
        self._all_alerts: bool = config_entry.options.get(
            CONF_ALL_ALERTS_ATTRIBUTES, False
        )
        self._http_client = async_get_clientsession(hass)
        self._http_cache: dict[str, tuple[Any, str, float]] = {}
        self._channels: list[TTLDeque] = channels
        self._channels_change: list[datetime | None] = []
        self._synthetic_alerts: list[tuple[float, AlertType]] = []

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
            for unrecognized_area in {alert[AREA_FIELD] for alert in alerts}.difference(
                {alert[AREA_FIELD] for alert in getattr(self.data, "items", [])}
            ).difference(AREAS):
                LOGGER.error("Alert has an unrecognized area: %s", unrecognized_area)
        else:
            alerts = self.data.items
        return OrefAlertCoordinatorData(alerts, self._active_duration)

    async def _async_fetch_url(self, url: str) -> tuple[Any, bool]:
        """Fetch data from Oref servers."""
        exc_info = Exception()
        now = dt_util.now().timestamp()
        cached_content, last_modified, last_request = self._http_cache.get(
            url, (None, "", 0)
        )
        if (now - last_request) < REQUEST_THROTTLING:
            return cached_content, False
        headers = (
            OREF_HEADERS
            if not last_modified
            else {"If-Modified-Since": last_modified, **OREF_HEADERS}
        )
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.get(url, headers=headers) as response:
                    if response.status == HTTPStatus.NOT_MODIFIED:
                        self._http_cache[url] = (cached_content, last_modified, now)
                        return cached_content, False
                    raw = await response.read()
                    text = raw.decode("utf-8-sig").replace("\x00", "").strip()
                    try:
                        content = None if not text else json.loads(text)
                    except:
                        LOGGER.debug(
                            "JSON parsing failed for '%s': '%s' hex: '%s'",
                            url,
                            text,
                            text.encode("utf-8").hex(),
                        )
                        raise
                    self._http_cache[url] = (
                        content,
                        response.headers.get("Last-Modified", ""),
                        now,
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
            self._http_cache[url] = (cached_content, last_modified, now)
            return cached_content, False
        LOGGER.error("Failed to fetch '%s'", url)
        raise exc_info

    def _current_to_history_format(
        self, current: dict[str, str], history: list[AlertType]
    ) -> list[AlertType]:
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
        for alert_area in current[AREA_FIELD]:
            area = self._fix_area_spelling(alert_area)
            for history_recent_alert in history_recent_alerts:
                if history_recent_alert[AREA_FIELD] == area:
                    # The alert is already in the history list. No need to add it twice.
                    break
            else:
                for previous_recent_alert in previous_recent_alerts:
                    if previous_recent_alert[AREA_FIELD] == area:
                        # The alert was already added, so take the original timestamp.
                        alerts.append(previous_recent_alert)
                        break
                else:
                    alerts.append(
                        {
                            DATE_FIELD: now,
                            TITLE_FIELD: current[TITLE_FIELD],
                            AREA_FIELD: area,
                            CATEGORY_FIELD: category,
                            CHANNEL_FIELD: AlertSource.WEBSITE,
                        }
                    )
        return alerts

    def _add_channels(self, alerts: list[AlertType]) -> None:
        """Add alerts from the different channels after de-dup."""
        dedup_window = REAL_TIME_ALERT_LOGIC_WINDOW * 60
        new_alerts: list[AlertType] = []
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
                        alert[AREA_FIELD] == exist_alert[AREA_FIELD]
                        and alert[CATEGORY_FIELD] == exist_alert[CATEGORY_FIELD]
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
    def _alert_timestamp(alert: AlertType) -> float:
        """Return alert's timestamp."""
        return (
            dt_util.parse_datetime(alert[DATE_FIELD], raise_on_error=True)
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

    def add_synthetic_alert(self, details: dict[str, Any]) -> None:
        """Add a synthetic alert for testing purposes."""
        now = dt_util.now(IST)
        for area in details[CONF_AREA]:
            self._synthetic_alerts.append(
                (
                    now.timestamp() + details[CONF_DURATION],
                    {
                        DATE_FIELD: now.strftime("%Y-%m-%d %H:%M:%S"),
                        TITLE_FIELD: details.get(
                            TITLE_FIELD, "התרעה סינטטית לצורכי בדיקות"
                        ),
                        AREA_FIELD: area,
                        CATEGORY_FIELD: details[CATEGORY_FIELD],
                        CHANNEL_FIELD: AlertSource.SYNTHETIC,
                    },
                )
            )

    def _get_synthetic_alerts(self) -> list[AlertType]:
        """Return the list of synthetic alerts."""
        now = dt_util.now().timestamp()
        self._synthetic_alerts = [
            (expired, alert)
            for expired, alert in self._synthetic_alerts
            if expired >= now
        ]
        return [alert for _, alert in self._synthetic_alerts]

    def is_synthetic_alert(self, alert: AlertType) -> bool:
        """Check if the alert is a synthetic alert."""
        return alert.get(CHANNEL_FIELD) == AlertSource.SYNTHETIC

    def _process_history_alerts(self, alerts: list[AlertType]) -> list[AlertType]:
        """Add channel field and fix spelling errors in area names."""
        for alert in alerts:
            alert[CHANNEL_FIELD] = AlertSource.HISTORY
            alert[AREA_FIELD] = self._fix_area_spelling(alert[AREA_FIELD])
        return alerts

    def _fix_area_spelling(self, area: str) -> str:
        """Fix spelling error in area name."""
        if area[0] == "'":
            area = f"{area[1:]}'"
        return area


class OrefAlertCoordinatorUpdater:
    """Refresh coordinator if there are active alerts / updates."""

    def __init__(
        self, hass: HomeAssistant, coordinator: OrefAlertDataUpdateCoordinator
    ) -> None:
        """Initialize the updater."""
        self._hass: HomeAssistant = hass
        self._coordinator: OrefAlertDataUpdateCoordinator = coordinator
        self._active: datetime = dt_util.now() - timedelta(days=1)
        self._update: datetime = dt_util.now()
        self._stop: bool = False
        self._unsub_update: Callable[[], None] | None = None

    def _sub(self) -> None:
        """Subscribe an update."""
        if not self._stop:
            self._unsub_update = event_helper.async_track_point_in_time(
                self._hass,
                self._async_update,
                dt_util.now() + timedelta(seconds=2),
            )

    @callback
    async def _async_update(self, *_: Any) -> None:
        """Refresh coordinator if needed."""
        self._unsub_update = None
        now = dt_util.now()
        update = False
        if self._coordinator.data.active_alerts or self._coordinator.data.updates:
            self._active = now
            update = True
        elif now - self._active < timedelta(
            minutes=20
        ) or now - self._update > timedelta(hours=1):
            update = True
        if update:
            self._update = now
            await self._coordinator.async_refresh()
        self._sub()

    def start(self) -> None:
        """Start the updater."""
        self._sub()

    def stop(self) -> None:
        """Stop the updater."""
        self._stop = True
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None
