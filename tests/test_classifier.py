"""Tests for the classifier module."""

from __future__ import annotations

from datetime import timedelta

from custom_components.oref_alert.classifier import Classifier
from custom_components.oref_alert.const import Record
from custom_components.oref_alert.records_schema import RecordType


def test_add_metadata_alert_expiration_uses_180_minutes() -> None:
    """Test alert records expire after 180 minutes."""
    classifier_test = Classifier()
    metadata = classifier_test.add_metadata(
        Record(
            data="בארי",
            category=1,
            channel="website-history",
            alertDate="2025-01-01 12:00:00",
            title="",
        )
    )

    assert metadata.record_type == RecordType.ALERT
    assert metadata.expire == metadata.time + timedelta(minutes=180)


def test_record_type_returns_none_when_category_is_missing() -> None:
    """Test malformed records without a category stay unclassified."""
    classifier_test = Classifier()

    assert classifier_test._record_type({"title": "missing category"}) is None  # noqa: SLF001
