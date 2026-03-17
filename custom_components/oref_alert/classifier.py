"""Support for representing oref alert as events."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

import homeassistant.util.dt as dt_util

from custom_components.oref_alert.const import (
    IST,
    Record,
    RecordAndMetadata,
)
from custom_components.oref_alert.records_schema import RECORDS_SCHEMA, RecordType

if TYPE_CHECKING:
    from collections.abc import Mapping

PARALLEL_UPDATES: Final = 0
RECORD_EXPIRATION_MINUTES: Final[dict[RecordType, int]] = {
    RecordType.PRE_ALERT: 20,
    RecordType.ALERT: 180,
}


class Classifier:
    """Classifier processor."""

    def add_metadata(
        self, record: Record, record_expire: datetime | None = None
    ) -> RecordAndMetadata:
        """Get record metadata."""
        raw_dict = asdict(record)

        record_time = dt_util.parse_datetime(
            record.alertDate, raise_on_error=True
        ).replace(tzinfo=IST)

        record_type = self._record_type(raw_dict)

        if (
            record_expire is None
            and record_type is not None
            and (expiration := RECORD_EXPIRATION_MINUTES.get(record_type)) is not None
        ):
            record_expire = record_time + timedelta(minutes=expiration)

        return RecordAndMetadata(
            raw=record,
            raw_dict=raw_dict,
            record_type=record_type,
            time=record_time,
            expire=record_expire,
        )

    def _record_type(self, record: Mapping[str, str | int]) -> RecordType | None:
        """Get record type."""
        for record_type, schema in RECORDS_SCHEMA.items():
            with suppress(Exception):
                schema(dict(record))
                return record_type
        return None
