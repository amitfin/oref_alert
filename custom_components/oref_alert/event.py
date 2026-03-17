"""Support for representing oref alert as events."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventEntity
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.util import slugify

from .const import (
    ATTR_RECORD,
    CONF_AREAS,
    CONF_SENSORS,
    OREF_ALERT_UNIQUE_ID,
    Record,
    RecordAndMetadata,
)
from .entity import OrefAlertCoordinatorEntity
from .metadata.areas import AREAS
from .records_schema import RECORDS_SCHEMA

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
        if not name:
            self.use_device_name = True
            self._attr_unique_id = OREF_ALERT_UNIQUE_ID
        else:
            self._attr_name = name
            self._attr_unique_id = slugify(
                f"{OREF_ALERT_UNIQUE_ID}_{name.lower().replace(' ', '_')}"
            )
        self.entity_id = f"{Platform.EVENT}.{self._attr_unique_id}"
        self._record: RecordAndMetadata | None = None

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) and (
            record := last_state.attributes.get(ATTR_RECORD)
        ):
            self._record = self._config_entry.runtime_data.classifier.add_metadata(
                Record(**record)
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (
            (record := self.coordinator.data.areas.get(self._area)) is not None
            and record.record_type is not None
            and self._record != record
        ):
            self._record = record
            self._trigger_event(record.record_type, {ATTR_RECORD: record.raw})
            self.async_write_ha_state()
