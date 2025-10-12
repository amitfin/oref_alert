"""The tests for the records_schema file."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.oref_alert.const import CATEGORY_FIELD, TITLE_FIELD
from custom_components.oref_alert.records_schema import RECORDS_SCHEMA, RecordType


@pytest.mark.parametrize(
    ("record_type", "record"),
    [
        (RecordType.PRE_ALERT, {CATEGORY_FIELD: 14}),
        (RecordType.ALERT, {CATEGORY_FIELD: 1, TITLE_FIELD: "Test"}),
        (RecordType.END, {CATEGORY_FIELD: 13}),
    ],
    ids=("pre_alert", "alert", "end"),
)
async def test_valid(
    record_type: RecordType,
    record: dict[str, int | str],
) -> None:
    """Test valid records."""
    RECORDS_SCHEMA[record_type](record)


@pytest.mark.parametrize(
    ("record_type", "record"),
    [
        (RecordType.PRE_ALERT, {CATEGORY_FIELD: 1}),
        (RecordType.ALERT, {CATEGORY_FIELD: 14}),
        (RecordType.ALERT, {CATEGORY_FIELD: 13}),
        (RecordType.END, {CATEGORY_FIELD: 14}),
    ],
    ids=("pre_alert", "alert_with_pre", "alert_with_end", "end"),
)
async def test_invalid(
    record_type: RecordType,
    record: dict[str, int | str],
) -> None:
    """Test valid records."""
    with pytest.raises(vol.Invalid):
        RECORDS_SCHEMA[record_type](record)
