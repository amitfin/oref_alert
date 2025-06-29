"""Fire event for updates."""

from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.location import vincenty

from custom_components.oref_alert.categories import (
    category_to_emoji,
    category_to_icon,
)
from custom_components.oref_alert.metadata.area_info import AREA_INFO
from custom_components.oref_alert.metadata.areas import AREAS

from .const import (
    ATTR_AREA,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    CONF_ALERT_ACTIVE_DURATION,
    DATA_COORDINATOR,
    DOMAIN,
    AlertField,
)

if TYPE_CHECKING:
    from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator

SECONDS_IN_A_MINUTE = 60


class OrefAlertUpdateEventManager:
    """Manage updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        self._hass = hass
        self._previous_updates: list[tuple[float, dict[str, Any]]] = []
        self._expiration = (
            config_entry.options[CONF_ALERT_ACTIVE_DURATION] * SECONDS_IN_A_MINUTE
        )
        self._coordinator: OrefAlertDataUpdateCoordinator = config_entry.runtime_data[
            DATA_COORDINATOR
        ]
        self._coordinator.async_add_listener(self._async_update)
        self._async_update()

    @callback
    def _async_update(self) -> None:
        """Fire event for new updates."""
        self._remove_expired()
        expiration = dt_util.now().timestamp() + self._expiration
        for update in self._coordinator.data.updates:
            if self._is_previous_update(update):
                continue
            if (area := update[AlertField.AREA]) not in AREAS:
                continue
            area_info = AREA_INFO[area]
            self._hass.bus.async_fire(
                f"{DOMAIN}_update_event",
                {
                    ATTR_AREA: area,
                    ATTR_HOME_DISTANCE: round(
                        vincenty(
                            (self._hass.config.latitude, self._hass.config.longitude),
                            (area_info["lat"], area_info["lon"]),
                        )
                        or 0,
                        1,
                    ),
                    ATTR_LATITUDE: area_info["lat"],
                    ATTR_LONGITUDE: area_info["lon"],
                    AlertField.CATEGORY: update.get(AlertField.CATEGORY),
                    AlertField.TITLE: update.get(AlertField.TITLE),
                    ATTR_ICON: category_to_icon(update.get("category", 0)),
                    ATTR_EMOJI: category_to_emoji(update.get("category", 0)),
                },
            )
            self._previous_updates.append((expiration, update))

    def _remove_expired(self) -> None:
        """Remove expired updates."""
        now = dt_util.now().timestamp()
        self._previous_updates = [
            (expired, update)
            for expired, update in self._previous_updates
            if expired >= now
        ]

    def _is_previous_update(self, update: dict[str, Any]) -> bool:
        """Check if the update is in the previous list."""
        return any(update == entry[1] for entry in self._previous_updates)
