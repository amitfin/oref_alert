"""Fire event for updates."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    ATTR_DATE,
    ATTR_ICON,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util.location import vincenty

from custom_components.oref_alert.metadata.area_to_district import AREA_TO_DISTRICT

from .categories import (
    category_to_emoji,
    category_to_icon,
)
from .const import (
    ATTR_AREA,
    ATTR_DISTRICT,
    ATTR_EMOJI,
    ATTR_HOME_DISTANCE,
    ATTR_TYPE,
    CATEGORY_FIELD,
    CHANNEL_FIELD,
    DOMAIN,
    LOGGER,
    TITLE_FIELD,
    Record,
    RecordAndMetadata,
    RecordType,
)
from .metadata.area_info import AREA_INFO
from .ttl_deque import TTLDeque

if TYPE_CHECKING:
    from collections.abc import Callable

    from . import OrefAlertConfigEntry
    from .coordinator import OrefAlertDataUpdateCoordinator


class OrefAlertBusEventManager:
    """Manage bus events."""

    _STORAGE_VERSION = 1
    _STORAGE_KEY = f"{DOMAIN}_history"
    _STORAGE_RECORDS_KEY = "records"

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        self._hass = hass
        self._config_entry = config_entry
        self._previous_items: TTLDeque[Record] = TTLDeque()
        self.alert_history: TTLDeque[dict[str, Any]] = TTLDeque(ttl=60 * 24)
        self._history_records: TTLDeque[RecordAndMetadata] = TTLDeque(ttl=60 * 24)
        self._store = Store[dict[str, Any]](
            hass, self._STORAGE_VERSION, self._STORAGE_KEY
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

    async def async_restore(self) -> None:
        """Restore history records from persistent storage."""
        stored = await self._store.async_load()
        if not stored:
            return
        for raw_record in stored.get(self._STORAGE_RECORDS_KEY, []):
            try:
                record = Record(**raw_record)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Skipping invalid restored history record", exc_info=True)
                continue
            record_metadata = self._config_entry.runtime_data.coordinator.add_metadata(
                record
            )
            self._history_records.add(record_metadata, record_metadata.time)
            self._previous_items.add(record, record_metadata.time)
            if event := self._compose_event(record):
                self.alert_history.add(
                    {**event, ATTR_DATE: record_metadata.time.isoformat()},
                    record_metadata.time,
                )

    async def async_save(self) -> None:
        """Persist history records to storage."""
        await self._store.async_save(
            {
                self._STORAGE_RECORDS_KEY: [
                    record.raw_dict
                    for record in reversed(list(self._history_records.items()))
                ]
            }
        )

    def _compose_event(self, record: Record) -> dict[str, Any] | None:
        """Compose event from a record."""
        if not (area_info := AREA_INFO.get(record.data)):
            return None
        return {
            ATTR_AREA: record.data,
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
            CATEGORY_FIELD: record.category,
            TITLE_FIELD: record.title,
            ATTR_ICON: category_to_icon(record.category),
            ATTR_EMOJI: category_to_emoji(record.category),
            ATTR_DISTRICT: AREA_TO_DISTRICT.get(record.data),
            CHANNEL_FIELD: record.channel,
        }

    @callback
    def _async_update(self) -> None:
        """Fire event bus for new records."""
        for record in self._coordinator.get_record_and_metadata(
            None, None, 3, newer_first=False
        ):
            if record.raw in self._previous_items or not (
                event := self._compose_event(record.raw)
            ):
                continue
            self._hass.bus.async_fire(
                f"{DOMAIN}_event"
                if record.record_type == RecordType.ALERT
                else f"{DOMAIN}_update_event",
                event,
            )
            self._hass.bus.async_fire(
                f"{DOMAIN}_record",
                {
                    **event,
                    ATTR_TYPE: record.record_type.value if record.record_type else None,
                },
            )
            if record.record_type == RecordType.ALERT:
                self.alert_history.add(
                    {**event, ATTR_DATE: record.time.isoformat()}, record.time
                )
                self._history_records.add(record, record.time)
            self._previous_items.add(record.raw, record.time)
