"""DataUpdateCoordinator for oref_alert integration."""
import asyncio
from datetime import timedelta
from functools import cmp_to_key
from json import JSONDecodeError
from typing import Any

from aiohttp.client_exceptions import ContentTypeError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import DOMAIN, IST, LOGGER
from .metadata.areas import AREAS

OREF_ALERTS_URL = "https://www.oref.org.il/WarningMessages/alert/alerts.json"
OREF_HISTORY_URL = "https://www.oref.org.il/WarningMessages/History/AlertsHistory.json"
OREF_HEADERS = {
    "Referer": "https://www.oref.org.il/",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}
REQUEST_RETRIES = 3


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


class OrefAlertDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Oref Alert data."""

    def __init__(self, hass: HomeAssistant, update_interval: int):
        """Initialize global data updater."""
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self._http_client = async_get_clientsession(hass)

    async def _async_update_data(self) -> None:
        """Request the data from Oref servers.."""
        current, history = await asyncio.gather(
            *[self._async_fetch_url(url) for url in (OREF_ALERTS_URL, OREF_HISTORY_URL)]
        )
        alerts = self._current_to_history_format(current) if current else []
        alerts.extend(history or [])
        alerts.sort(key=cmp_to_key(_sort_alerts))
        for unrecognized_area in {alert["data"] for alert in alerts}.difference(AREAS):
            LOGGER.error("Alert has an unrecognized area: %s", unrecognized_area)
        return alerts

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
        self, current: dict[str, str]
    ) -> list[dict[str, str]]:
        """Convert current alerts payload to history format."""
        now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        return [
            {
                "alertDate": now,
                "title": current["title"],
                "data": data,
                "category": int(current["cat"]),
            }
            for data in current["data"]
        ]
