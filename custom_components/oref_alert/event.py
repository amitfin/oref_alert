"""Support for representing oref alert as events."""

from __future__ import annotations

import types
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import homeassistant.util.dt as dt_util
from homeassistant.components.event import ATTR_EVENT_TYPE, EventEntity
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .const import (
    AREA_FIELD,
    ATTR_RECORD,
    CHANNEL_FIELD,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DATE_FIELD,
    OREF_ALERT_UNIQUE_ID,
    AlertSource,
    AlertType,
)
from .entity import OrefAlertCoordinatorEntity
from .metadata import ALL_AREAS_ALIASES
from .metadata.areas import AREAS

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from voluptuous import Schema

    from . import OrefAlertConfigEntry

PARALLEL_UPDATES = 0
GITHUB_ROOT = "https://raw.githubusercontent.com/amitfin/oref_alert/main/custom_components/oref_alert"
RECORDS_SCHEMA_FILE_NAME = "records_schema"
RECORDS_SCHEMA_URL = f"{GITHUB_ROOT}/{RECORDS_SCHEMA_FILE_NAME}.py"
RECORDS_SCHEMA: dict[str, Schema] = {}


class RecordsSchemaLoader:
    """Records schema loader."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the loader."""
        self._hass = hass
        self._http_client = async_get_clientsession(hass)
        self._unsub_next_load: Callable[[], None] | None = None

    def stop(self) -> None:
        """Cancel next load."""
        if self._unsub_next_load is not None:
            self._unsub_next_load()
            self._unsub_next_load = None

    @callback
    async def load(self, _: datetime | None = None) -> None:
        """Load the records schema."""
        async with self._http_client.get(RECORDS_SCHEMA_URL) as response:
            response.raise_for_status()
            code = await response.text()

        module = types.ModuleType(RECORDS_SCHEMA_FILE_NAME)
        exec(compile(code, RECORDS_SCHEMA_URL, "exec"), module.__dict__)  # noqa: S102

        global RECORDS_SCHEMA  # noqa: PLW0603
        RECORDS_SCHEMA = module.RECORDS_SCHEMA

        self._unsub_next_load = event.async_track_point_in_time(
            self._hass, self.load, dt_util.now() + timedelta(hours=6)
        )


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
        event_type, record = self._get_record()
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

    def _get_record(self) -> tuple[str, AlertType] | tuple[None, None]:
        """Get the latest record, if any."""
        for record in self.coordinator.data.active_items:
            if (
                area := record[AREA_FIELD]
            ) != self._area and area not in ALL_AREAS_ALIASES:
                continue

            for record_type, schema in RECORDS_SCHEMA.items():
                try:
                    schema(record)
                except:  # noqa: E722, S112
                    continue
                return record_type, record

        return None, None
