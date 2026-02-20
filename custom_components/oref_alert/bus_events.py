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
    ATTR_AREA,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    ATTR_TYPE,
    CATEGORY_FIELD,
    CHANNEL_FIELD,
    DOMAIN,
    TITLE_FIELD,
    RecordAndMetadata,
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
        self._previous_items: TTLDeque[RecordAndMetadata] = TTLDeque()
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
        for record in set(self._coordinator.data.areas.values()):
            if self._is_old(record):
                continue
            if (area := record.item.data) not in AREAS:
                continue
            area_info = AREA_INFO[area]
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
                CATEGORY_FIELD: record.item.category,
                TITLE_FIELD: record.item.title,
                ATTR_ICON: category_to_icon(record.item.category),
                ATTR_EMOJI: category_to_emoji(record.item.category),
                CHANNEL_FIELD: record.item.channel,
            }
            self._hass.bus.async_fire(
                f"{DOMAIN}_event"
                if record.record_type == RecordType.ALERT
                else f"{DOMAIN}_update_event",
                event,
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_record", {**event, ATTR_TYPE: record.record_type}
            )
            self._previous_items.add(record)

    def _is_old(self, record: RecordAndMetadata) -> bool:
        """Check if the item is in the previous list."""
        for previous in self._previous_items.items():
            if (
                record.item.data == previous.item.data
                and record.item.category == previous.item.category
                and record.record_type == previous.record_type
            ):
                return True
        return False
