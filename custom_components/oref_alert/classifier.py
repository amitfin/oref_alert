"""Support for representing oref alert as events."""

from __future__ import annotations

import types
from contextlib import suppress
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import homeassistant.util.dt as dt_util
from homeassistant.core import callback
from homeassistant.helpers import event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.oref_alert.const import (
    IST,
    Record,
    RecordAndMetadata,
)
from custom_components.oref_alert.records_schema import RecordType

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from voluptuous import Schema

PARALLEL_UPDATES: Final = 0
GITHUB_ROOT: Final = "https://raw.githubusercontent.com/amitfin/oref_alert/main/custom_components/oref_alert"
RECORDS_SCHEMA_FILE_NAME: Final = "records_schema"
RECORDS_SCHEMA_URL: Final = f"{GITHUB_ROOT}/{RECORDS_SCHEMA_FILE_NAME}.py"
RECORDS_SCHEMA: dict[RecordType, Schema] = {}
RECORD_EXPIRATION_MINUTES: Final[dict[RecordType, int]] = {
    RecordType.PRE_ALERT: 20,
    RecordType.ALERT: 720,
    RecordType.END: 10,
}


class Classifier:
    """Classifier processor."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the processor."""
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

    def add_metadata(
        self, record: Record, record_expire: datetime | None = None
    ) -> RecordAndMetadata:
        """Get record metadata."""
        record_time = dt_util.parse_datetime(
            record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST)

        record_type = self._record_type(record)

        if (
            record_expire is None
            and record_type is not None
            and (expiration := RECORD_EXPIRATION_MINUTES.get(record_type)) is not None
        ):
            record_expire = record_time + timedelta(minutes=expiration)

        return RecordAndMetadata(
            raw=record,
            record_type=record_type,
            time=record_time,
            expire=record_expire,
        )

    def _record_type(self, record: Record) -> RecordType | None:
        """Get record type."""
        fields = asdict(record)
        for record_type, schema in RECORDS_SCHEMA.items():
            with suppress(Exception):
                schema(fields)
                return record_type
        return None
