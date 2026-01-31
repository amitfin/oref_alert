"""Tests for the classifier module."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

import homeassistant.util.dt as dt_util

from custom_components.oref_alert import categories, classifier, records_schema
from custom_components.oref_alert.classifier import Classifier
from custom_components.oref_alert.const import AREA_FIELD, CATEGORY_FIELD
from custom_components.oref_alert.metadata import ALL_AREAS_ALIASES

if TYPE_CHECKING:
    import pytest
    from homeassistant.core import HomeAssistant

    from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator


def _make_classifier(
    hass: HomeAssistant, active_items: list[dict[str, str]]
) -> Classifier:
    coordinator = SimpleNamespace(data=SimpleNamespace(active_items=active_items))
    return Classifier(hass, cast("OrefAlertDataUpdateCoordinator", coordinator))


async def test_load_sets_schema_and_schedules(hass: HomeAssistant) -> None:
    """Test classifier schema load updates the schema and schedules a reload."""
    record_manager = _make_classifier(hass, [])

    now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=dt_util.UTC)
    unsub = Mock()

    with (
        patch("custom_components.oref_alert.classifier.dt_util.now", return_value=now),
        patch(
            "custom_components.oref_alert.classifier.event.async_track_point_in_time",
            return_value=unsub,
        ) as track_point,
    ):
        await record_manager.load()

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

    track_point.assert_called_once_with(
        hass, record_manager.load, now + timedelta(hours=6)
    )
    record_manager.stop()
    unsub.assert_called_once()


def test_stop_noop_without_schedule(hass: HomeAssistant) -> None:
    """Test stop is safe when no schedule exists."""
    record_manager = _make_classifier(hass, [])
    record_manager.stop()


def test_get_last_record_matches_area_and_skips_invalid(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test area matching and invalid record handling."""
    monkeypatch.setattr(classifier, "RECORDS_SCHEMA", records_schema.RECORDS_SCHEMA)

    invalid_record = {AREA_FIELD: "Area 1"}
    valid_record = {
        AREA_FIELD: "Area 1",
        CATEGORY_FIELD: categories.PRE_ALERT_CATEGORY,
    }
    record_manager = _make_classifier(hass, [invalid_record, valid_record])

    record_type, record = record_manager.latest_record_type("Area 1")

    assert str(record_type) == "pre_alert"
    assert record == valid_record


def test_get_last_record_accepts_alias(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test alias areas are accepted even without a direct match."""
    monkeypatch.setattr(classifier, "RECORDS_SCHEMA", records_schema.RECORDS_SCHEMA)

    alias = next(iter(ALL_AREAS_ALIASES))
    valid_record = {
        AREA_FIELD: alias,
        CATEGORY_FIELD: categories.END_ALERT_CATEGORY,
    }
    record_manager = _make_classifier(hass, [valid_record])

    record_type, record = record_manager.latest_record_type("Area 2")

    assert str(record_type) == "end"
    assert record == valid_record


def test_get_last_record_returns_none(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test no match returns (None, None)."""
    monkeypatch.setattr(classifier, "RECORDS_SCHEMA", records_schema.RECORDS_SCHEMA)

    record = {AREA_FIELD: "Area B", CATEGORY_FIELD: categories.PRE_ALERT_CATEGORY}
    record_manager = _make_classifier(hass, [record])

    record_type, record = record_manager.latest_record_type("Area A")

    assert record_type is None
    assert record is None


def test_record_type_returns_match(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test record_type returns a matching schema type."""
    monkeypatch.setattr(classifier, "RECORDS_SCHEMA", records_schema.RECORDS_SCHEMA)

    record_manager = _make_classifier(hass, [])
    record = {CATEGORY_FIELD: categories.END_ALERT_CATEGORY}

    record_type = record_manager.record_type(record)

    assert str(record_type) == "end"


def test_record_type_returns_none_on_invalid(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test record_type returns None for invalid records."""
    monkeypatch.setattr(classifier, "RECORDS_SCHEMA", records_schema.RECORDS_SCHEMA)

    record_manager = _make_classifier(hass, [])

    record_type = record_manager.record_type({})

    assert record_type is None
