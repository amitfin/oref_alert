"""Fire event for updates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.location import vincenty

from .categories import (
    category_to_emoji,
    category_to_icon,
)
from .const import (
    ATTR_AREA,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    CONF_ALERT_ACTIVE_DURATION,
    DOMAIN,
    AlertField,
)
from .metadata.area_info import AREA_INFO
from .metadata.areas import AREAS
from .ttl_deque import TTLDeque

if TYPE_CHECKING:
    from . import OrefAlertConfigEntry
    from .coordinator import OrefAlertDataUpdateCoordinator


class OrefAlertUpdateEventManager:
    """Manage updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        self._hass = hass
        self._previous_updates: TTLDeque = TTLDeque(
            config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )
        self._coordinator: OrefAlertDataUpdateCoordinator = (
            config_entry.runtime_data.coordinator
        )
        self._coordinator.async_add_listener(self._async_update)
        self._async_update()

    @callback
    def _async_update(self) -> None:
        """Fire event for new updates."""
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
                    AlertField.CHANNEL: update.get(AlertField.CHANNEL),
                },
            )
            self._previous_updates.add(update)

    def _is_previous_update(self, update: dict[str, Any]) -> bool:
        """Check if the update is in the previous list."""
        for previous in self._previous_updates.items():
            for field in (AlertField.AREA, AlertField.CATEGORY, AlertField.TITLE):
                if update.get(field) != previous.get(field):
                    break
            else:
                return True
        return False
