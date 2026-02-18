"""Support for representing oref alert as events."""

from __future__ import annotations

import types
from contextlib import suppress
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import homeassistant.util.dt as dt_util
from homeassistant.core import callback
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.oref_alert.const import AREA_FIELD, DATE_FIELD, IST, AlertType
from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES
from custom_components.oref_alert.records_schema import RecordType

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from voluptuous import Schema

    from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator

PARALLEL_UPDATES: Final = 0
GITHUB_ROOT: Final = "https://raw.githubusercontent.com/amitfin/oref_alert/main/custom_components/oref_alert"
RECORDS_SCHEMA_FILE_NAME: Final = "records_schema"
RECORDS_SCHEMA_URL: Final = f"{GITHUB_ROOT}/{RECORDS_SCHEMA_FILE_NAME}.py"
RECORDS_SCHEMA: dict[str, Schema] = {}
RECORD_EXPIRATION_MINUTES: Final[dict[str, int]] = {
    RecordType.PRE_ALERT: 20,
    RecordType.ALERT: 720,
}


class Classifier:
    """Classifier processor."""

    def __init__(
        self, hass: HomeAssistant, coordinator: OrefAlertDataUpdateCoordinator
    ) -> None:
        """Initialize the processor."""
        self._hass = hass
        self._coordinator: OrefAlertDataUpdateCoordinator = coordinator
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
        try:
            async with self._http_client.get(RECORDS_SCHEMA_URL) as response:
                response.raise_for_status()
                code = await response.text()

            module = types.ModuleType(RECORDS_SCHEMA_FILE_NAME)
            exec(  # noqa: S102
                compile(code, RECORDS_SCHEMA_URL, "exec"),
                module.__dict__,
            )

            global RECORDS_SCHEMA  # noqa: PLW0603
            RECORDS_SCHEMA = module.RECORDS_SCHEMA
        finally:
            self._unsub_next_load = event.async_track_point_in_time(
                self._hass, self.load, dt_util.now() + timedelta(hours=6)
            )

    def record_type(self, record: AlertType) -> str | None:
        """Get record type."""
        for record_type, schema in RECORDS_SCHEMA.items():
            with suppress(Exception):
                schema(record)
                return record_type
        return None

    def record_expired(self, record: AlertType, record_type: str | None = None) -> bool:
        """Check if the record is expired."""
        if not record_type:
            record_type = self.record_type(record)

        if (
            not record_type
            or (expiration := RECORD_EXPIRATION_MINUTES.get(record_type)) is None
        ):
            return False

        return (
            dt_util.now()
            - dt_util.parse_datetime(record[DATE_FIELD], raise_on_error=True).replace(
                tzinfo=IST
            )
        ) > timedelta(minutes=expiration)

    def latest_record_type(
        self, area: str
    ) -> tuple[str, AlertType, bool] | tuple[None, None, bool]:
        """Get the latest record type."""
        for record in self._coordinator.data.active_items:
            if (
                (record_area := record[AREA_FIELD]) == area
                or record_area in ALL_AREAS_ALIASES
            ) and (record_type := self.record_type(record)) is not None:
                return record_type, record, self.record_expired(record, record_type)
        return None, None, True
