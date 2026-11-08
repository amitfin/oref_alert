"""Fire event for updates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import homeassistant.util.dt as dt_util
from homeassistant.const import ATTR_DATE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    ATTR_AREA,
    ATTR_TYPE,
    DOMAIN,
    LOGGER,
    OREF_ALERT_RECORD_EVENT,
    Record,
    RecordAndMetadata,
    RecordType,
)
from .coordinator import DEDUP_WINDOW_SECONDS
from .ttl_deque import TTLDeque

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from . import OrefAlertConfigEntry
    from .coordinator import OrefAlertDataUpdateCoordinator

# Records older than that are not fired as events.
EVENT_WINDOW: Final = timedelta(minutes=3)


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
        self._previous_items: TTLDeque[tuple[str, Record]] = TTLDeque()
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
            for area, area_record in sorted(
                self._coordinator.area_records(record_metadata)
            ):
                self._history_records.add(area_record, area_record.time)
                self._previous_items.add((area, area_record.raw), area_record.time)
                if event := self._compose_event(area_record):
                    self.alert_history.add(
                        self._alert_history_item(event, area_record), area_record.time
                    )

    async def async_save(self) -> None:
        """Persist history records to storage."""
        await self._store.async_save(
            {
                self._STORAGE_RECORDS_KEY: list(
                    {
                        record.raw: record.raw_dict
                        for record in reversed(list(self._history_records.items()))
                    }.values()
                )
            }
        )

    def _compose_event(self, record: RecordAndMetadata) -> dict[str, Any] | None:
        """Compose event from a record."""
        if not (published := record.published_data):
            return None
        return {
            key: value
            for key, value in published.items()
            if key not in {ATTR_DATE, ATTR_TYPE}
        }

    @staticmethod
    def _alert_history_item(
        event: dict[str, Any], record: RecordAndMetadata
    ) -> dict[str, Any]:
        """Return the alert history item of an event."""
        return {**event, ATTR_DATE: record.time.isoformat()}

    @callback
    def _async_update(self) -> None:
        """
        Fire event bus for new records.

        trigger.py's batching relies on every OREF_ALERT_RECORD_EVENT for one
        coordinator refresh being fired synchronously, within this single
        callback with no `await` in between. Keep this method fully
        synchronous, or the triggers will start firing multiple times per
        refresh instead of once.
        """
        earliest = dt_util.now() - EVENT_WINDOW
        for area, record in sorted(
            self._coordinator.data.areas.items(),
            key=lambda item: (item[1].time, item[0]),
        ):
            if (
                record.time < earliest
                or (area, record.raw) in self._previous_items
                or not (event := self._compose_event(record))
            ):
                continue
            self._hass.bus.async_fire(
                f"{DOMAIN}_event"
                if record.record_type == RecordType.ALERT
                else f"{DOMAIN}_update_event",
                event,
            )
            self._hass.bus.async_fire(
                OREF_ALERT_RECORD_EVENT,
                {
                    **event,
                    ATTR_TYPE: record.record_type.value if record.record_type else None,
                },
            )
            if record.record_type == RecordType.ALERT:
                self.alert_history.add(
                    self._alert_history_item(event, record), record.time
                )
                self._history_records.add(record, record.time)
            self._previous_items.add((area, record.raw), record.time)

    @callback
    def backfill(self, records: Iterable[RecordAndMetadata]) -> None:
        """Add older alerts (e.g. of the last day) to the history, without events."""
        # Newer records are handled by _async_update.
        earliest = dt_util.now() - EVENT_WINDOW
        dedup_window = timedelta(seconds=DEDUP_WINDOW_SECONDS)
        known: defaultdict[tuple[str, int], list[datetime]] = defaultdict(list)
        for record in self._history_records.items():
            if record.published_data:
                key = (record.published_data[ATTR_AREA], record.raw.category)
                known[key].append(record.time)
        history: list[tuple[RecordAndMetadata, datetime]] = []
        alerts: list[tuple[dict[str, Any], datetime]] = []
        for record in records:
            if record.record_type != RecordType.ALERT or record.time >= earliest:
                continue
            for area, area_record in self._coordinator.area_records(record):
                key = (area, area_record.raw.category)
                # The same alert might have been recorded by another channel.
                if not (event := self._compose_event(area_record)) or any(
                    abs(area_record.time - time) <= dedup_window for time in known[key]
                ):
                    continue
                known[key].append(area_record.time)
                history.append((area_record, area_record.time))
                alerts.append(
                    (self._alert_history_item(event, area_record), area_record.time)
                )
        self._history_records.add_many(history)
        self.alert_history.add_many(alerts)
