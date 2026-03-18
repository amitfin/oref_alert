"""The tests for the records_schema file."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import voluptuous as vol

from custom_components.oref_alert.const import CATEGORY_FIELD, TITLE_FIELD
from custom_components.oref_alert.records_schema import RECORDS_SCHEMA, RecordType


def test_records_schema_file_is_frozen() -> None:
    """Keep records_schema.py byte-for-byte frozen for historical compatibility."""
    assert (
        hashlib.sha256(
            (
                Path(__file__).parent.parent
                / "custom_components/oref_alert/records_schema.py"
            ).read_bytes()
        ).hexdigest()
        == "1988ecb45d284d94901fbfe34032f775123ad31ec79dea53acac53baece57cec"
    ), (
        "records_schema.py is frozen and kept only for backward compatibility reasons. "
        "Do not change this file unless you are intentionally updating the frozen hash "
        "and its historical contract."
    )


def test_product_code_does_not_import_records_schema() -> None:
    """Keep records_schema.py unused by other product files."""
    product_dir = Path(__file__).parent.parent / "custom_components/oref_alert"
    violations = [
        str(file_path.relative_to(product_dir))
        for file_path in product_dir.rglob("*.py")
        if file_path.name != "records_schema.py"
        and "records_schema" in file_path.read_text(encoding="utf-8")
    ]

    assert not violations, (
        "records_schema.py is frozen and kept only for backward compatibility "
        "reasons. Product code must not reference it. Violations: "
        + ", ".join(sorted(set(violations)))
    )


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
