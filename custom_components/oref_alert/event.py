"""Support for representing oref alert as events."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util
from homeassistant.components.event import ATTR_EVENT_TYPE, EventEntity
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.util import slugify

from .classifier import RECORDS_SCHEMA
from .const import (
    ATTR_RECORD,
    CHANNEL_FIELD,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DATE_FIELD,
    OREF_ALERT_UNIQUE_ID,
    AlertSource,
)
from .entity import OrefAlertCoordinatorEntity
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import OrefAlertConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    _: HomeAssistant,
    config_entry: OrefAlertConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize config entry."""
    async_add_entities(
        [
            AlertEvent(name, areas[0], config_entry)
            for name, areas in [
                (None, config_entry.options[CONF_AREAS]),
                *list(config_entry.options.get(CONF_SENSORS, {}).items()),
            ]
            if len(areas) == 1 and areas[0] in AREAS
        ]
    )


class AlertEvent(OrefAlertCoordinatorEntity, EventEntity):
    """Representation of the alert event."""

    _attr_translation_key = "alert"

    def __init__(
        self,
        name: str | None,
        area: str,
        config_entry: OrefAlertConfigEntry,
    ) -> None:
        """Initialize object with defaults."""
        super().__init__(config_entry)
        self._attr_event_types = list(RECORDS_SCHEMA.keys())
        self._area = area
        self._active_duration: timedelta = timedelta(
            minutes=config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )
        self._event_triggered = dt_util.utcnow() - self._active_duration
        self._synthetic_timestamp: str | None = None
        if not name:
            self.use_device_name = True
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
        else:
            self._attr_name = name
            self._attr_unique_id = slugify(
                f"{OREF_ALERT_UNIQUE_ID}_{name.lower().replace(' ', '_')}"
            )
        self.entity_id = f"{Platform.EVENT}.{self._attr_unique_id}"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        event_type, record = (
            self._config_entry.runtime_data.classifier.latest_record_type(self._area)
        )
        if not event_type or not record:
            return

        # We always trigger for a different type of event
        if event_type == self.state_attributes.get(ATTR_EVENT_TYPE):
            # For non-synthetic events, we trigger only if enough time has passed
            if record[CHANNEL_FIELD] != AlertSource.SYNTHETIC:
                if dt_util.utcnow() - self._event_triggered < self._active_duration:
                    return
            # For synthetic events, we trigger only if the timestamp is different
            elif record[DATE_FIELD] == self._synthetic_timestamp:
                return

        if record[CHANNEL_FIELD] != AlertSource.SYNTHETIC:
            self._event_triggered = dt_util.utcnow()
        else:
            self._synthetic_timestamp = record[DATE_FIELD]

        self._trigger_event(event_type, {ATTR_RECORD: record})
        self.async_write_ha_state()
