"""Check if list of areas was changed."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import event
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable

CITIES_MIX_URL = "https://alerts-history.oref.org.il/Shared/Ajax/GetCitiesMix.aspx"
FILTER_SUFFIX1 = " - כל האזורים"
FILTER_SUFFIX2 = " כל - האזורים"
DEPRECATION_SUFFIX = " (אזור התרעה ישן)"


class AreasChecker:
    """Periodic check for changes in the list of areas."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize areas checker."""
        self._hass = hass
        self._http_client = async_get_clientsession(hass)
        self._unsub_next_check: Callable[[], None] | None = (
            event.async_track_point_in_time(
                hass, self._check, dt_util.now() + timedelta(minutes=1)
            )
        )

    def stop(self) -> None:
        """Cancel next check."""
        if self._unsub_next_check is not None:
            self._unsub_next_check()
            self._unsub_next_check = None

    @callback
    async def _check(self, _: datetime | None = None) -> None:
        """Check if  the list of areas was changed."""
        try:
            async with self._http_client.get(CITIES_MIX_URL) as response:
                data = await response.json()
            areas = {
                area["label_he"]
                for area in data
                if not area["label_he"].endswith(FILTER_SUFFIX1)
                and not area["label_he"].endswith(FILTER_SUFFIX2)
                and not area["label_he"].endswith(DEPRECATION_SUFFIX)
            }
            new = sorted(areas.difference(AREAS))
            old = sorted(AREAS.difference(areas))
            if old:
                LOGGER.warning(
                    "The following Oref Alert areas were removed: "
                    + ",".join([f'"{area}"' for area in old])
                )
            if new:
                LOGGER.warning(
                    "The following Oref Alert areas were added: "
                    + ",".join([f'"{area}"' for area in new])
                )
            if old or new:
                issue_id = "upgrade_required"
                ir.async_delete_issue(self._hass, DOMAIN, issue_id)
                ir.async_create_issue(
                    self._hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    learn_more_url="https://github.com/amitfin/oref_alert",
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="upgrade_required",
                )
        finally:
            self._unsub_next_check = event.async_track_point_in_time(
                self._hass, self._check, dt_util.now() + timedelta(hours=12)
            )
