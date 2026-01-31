"""Fire event for updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import (
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.location import vincenty

from custom_components.oref_alert.records_schema import RecordType

from .categories import (
    category_to_emoji,
    category_to_icon,
)
from .const import (
    AREA_FIELD,
    ATTR_AREA,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    ATTR_TYPE,
    CATEGORY_FIELD,
    CHANNEL_FIELD,
    CONF_ALERT_ACTIVE_DURATION,
    DOMAIN,
    TITLE_FIELD,
    AlertType,
)
from .metadata.area_info import AREA_INFO
from .metadata.areas import AREAS
from .ttl_deque import TTLDeque

if TYPE_CHECKING:
    from collections.abc import Callable

    from . import OrefAlertConfigEntry
    from .coordinator import OrefAlertDataUpdateCoordinator


class OrefAlertBusEventManager:
    """Manage bus events."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        self._hass = hass
        self._config_entry = config_entry
        self._previous_items: TTLDeque = TTLDeque(
            config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )
        self._unsub_update: Callable[[], None] | None = None

    def start(self) -> None:
        """Subscribe to coordinator updates."""
        self._coordinator: OrefAlertDataUpdateCoordinator = (
            self._config_entry.runtime_data.coordinator
        )
        self._unsub_update = self._coordinator.async_add_listener(self._async_update)

    def stop(self) -> None:
        """Remove listener."""
        if self._unsub_update is not None:
            self._unsub_update()
            self._unsub_update = None

    @callback
    def _async_update(self) -> None:
        """Fire event bus for new records."""
        for item in self._coordinator.data.active_items:
            if self._is_old(item):
                continue
            if (area := item[AREA_FIELD]) not in AREAS:
                continue
            area_info = AREA_INFO[area]
            item_type = self._config_entry.runtime_data.classifier.record_type(item)
            event = {
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
                CATEGORY_FIELD: item.get(CATEGORY_FIELD),
                TITLE_FIELD: item.get(TITLE_FIELD),
                ATTR_ICON: category_to_icon(item.get("category", 0)),
                ATTR_EMOJI: category_to_emoji(item.get("category", 0)),
                CHANNEL_FIELD: item.get(CHANNEL_FIELD),
            }
            self._hass.bus.async_fire(
                f"{DOMAIN}_event"
                if item_type == RecordType.ALERT
                else f"{DOMAIN}_update_event",
                event,
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_record", {**event, ATTR_TYPE: item_type}
            )
            self._previous_items.add(item)

    def _is_old(self, item: AlertType) -> bool:
        """Check if the item is in the previous list."""
        for previous in self._previous_items.items():
            for field in (AREA_FIELD, CATEGORY_FIELD):
                if item.get(field) != previous.get(field):
                    break
            else:
                if self._config_entry.runtime_data.classifier.record_type(
                    item
                ) == self._config_entry.runtime_data.classifier.record_type(previous):
                    return True
        return False
