"""Tests for the classifier module."""

from __future__ import annotations

from contextlib import suppress
from datetime import timedelta
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import homeassistant.util.dt as dt_util

from custom_components.oref_alert import categories, classifier, records_schema
from custom_components.oref_alert.classifier import Classifier
from custom_components.oref_alert.const import (
    CATEGORY_FIELD,
    Record,
)
from custom_components.oref_alert.records_schema import RecordType

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant


async def test_load_sets_schema_and_schedules(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test classifier_test schema load updates the schema and schedules a reload."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    classifier_test = Classifier(hass)
    unsub = Mock()

    with patch(
        "custom_components.oref_alert.classifier.event.async_track_point_in_time",
        return_value=unsub,
    ) as track_point:
        await classifier_test.load()

    assert {str(key) for key in classifier.RECORDS_SCHEMA} == {
        "pre_alert",
        "alert",
        "end",
    }

    def _schema_accepts(record: dict[str, int]) -> bool:
        for schema in classifier.RECORDS_SCHEMA.values():
            with suppress(Exception):
                schema(record)
                return True
        return False

    assert _schema_accepts({CATEGORY_FIELD: categories.PRE_ALERT_CATEGORY})
    assert _schema_accepts({CATEGORY_FIELD: categories.END_ALERT_CATEGORY})
    assert _schema_accepts({CATEGORY_FIELD: 1})

    track_point.assert_called_once()
    assert track_point.call_args.args[1] == classifier_test.load
    assert track_point.call_args.args[2] - dt_util.now() == timedelta(hours=6)
    classifier_test.stop()
    unsub.assert_called_once()


def test_stop_noop_without_schedule(hass: HomeAssistant) -> None:
    """Test stop is safe when no schedule exists."""
    classifier_test = Classifier(hass)
    classifier_test.stop()


def test_add_metadata_unknown_record_type(hass: HomeAssistant) -> None:
    """Test metadata classification fallback to None for unknown categories."""
    classifier_test = Classifier(hass)
    with patch.dict(classifier.RECORDS_SCHEMA, {}, clear=True):
        metadata = classifier_test.add_metadata(
            Record(
                data="בארי",
                category=999,
                channel="website-history",
                alertDate="2025-01-01 12:00:00",
                title="",
            )
        )
    assert metadata.record_type is None


def test_add_metadata_alert_expiration_uses_180_minutes(hass: HomeAssistant) -> None:
    """Test alert records expire after 180 minutes."""
    classifier_test = Classifier(hass)
    with patch.dict(classifier.RECORDS_SCHEMA, records_schema.RECORDS_SCHEMA):
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
