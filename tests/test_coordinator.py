"""The tests for the coordinator file."""

import json
from collections import deque
from dataclasses import asdict
from datetime import timedelta
from http import HTTPStatus
from types import MappingProxyType, SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert import classifier, records_schema
from custom_components.oref_alert.categories import (
    END_ALERT_CATEGORY,
    PRE_ALERT_CATEGORY,
)
from custom_components.oref_alert.classifier import Classifier
from custom_components.oref_alert.const import (
    AREA_FIELD,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DOMAIN,
    IST,
    MANUAL_EVENT_END_TITLE,
    TITLE_FIELD,
    Record,
    RecordAndMetadata,
)
from custom_components.oref_alert.coordinator import (
    OREF_ALERTS_URL,
    OREF_HISTORY2_URL,
    OREF_HISTORY_URL,
    OrefAlertCoordinatorData,
    OrefAlertCoordinatorUpdater,
    OrefAlertDataUpdateCoordinator,
)
from custom_components.oref_alert.records_schema import RecordType

from .utils import load_json_fixture, mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

classifier.RECORDS_SCHEMA = records_schema.RECORDS_SCHEMA


def create_coordinator(
    hass: HomeAssistant,
    options: dict | None = None,
    channels: list[deque[RecordAndMetadata]] | None = None,
) -> OrefAlertDataUpdateCoordinator:
    """Create a test coordinator."""
    config = MockConfigEntry(
        domain=DOMAIN,
        options=options or {},
    )
    config.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = OrefAlertDataUpdateCoordinator(hass, config, channels or [])
    coordinator.config_entry = config
    config.runtime_data = SimpleNamespace(classifier=Classifier(hass))
    return coordinator


async def test_init(hass: HomeAssistant) -> None:
    """Test initializing the coordinator."""
    await create_coordinator(hass).async_config_entry_first_refresh()
    # No pending refresh since there are no listeners


async def test_save_and_restore_areas(hass: HomeAssistant) -> None:
    """Test persisting raw records and restoring metadata."""
    coordinator = create_coordinator(hass)
    stored: dict[str, dict[str, dict[str, str | int]]] = {}

    def store_data(data: dict[str, dict[str, dict[str, str | int]]]) -> None:
        stored.update(data)

    coordinator._store.async_save = AsyncMock(  # noqa: SLF001
        side_effect=store_data
    )
    coordinator._store.async_load = AsyncMock(return_value=stored)  # noqa: SLF001
    coordinator._no_update = False  # noqa: SLF001
    record = Record(
        alertDate=dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        "אילת": coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            record
        )
    }
    await coordinator.async_save()

    coordinator._areas = {}  # noqa: SLF001
    await coordinator.async_restore()

    restored = coordinator._areas.get("אילת")  # noqa: SLF001
    assert restored is not None
    assert restored.raw.data == "אילת"
    assert restored.raw.category == 1
    assert restored.raw.title == "ירי רקטות וטילים"


async def test_save_persists_only_records_newer_than_cutoff(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Test save filters out records older than the 1-day cutoff."""
    coordinator = create_coordinator(hass)
    stored: dict[str, dict[str, dict[str, str | int]]] = {}

    def store_data(data: dict[str, dict[str, dict[str, str | int]]]) -> None:
        stored.update(data)

    coordinator._store.async_save = AsyncMock(  # noqa: SLF001
        side_effect=store_data
    )
    coordinator._no_update = False  # noqa: SLF001
    freezer.move_to("2026-01-02 12:00:00+00:00")
    fresh_record = Record(
        alertDate=(dt_util.now(IST) - timedelta(hours=12)).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    old_record = Record(
        alertDate=(dt_util.now(IST) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        title="ירי רקטות וטילים",
        data="קריית שמונה",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        "אילת": coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            fresh_record
        ),
        "קריית שמונה": coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            old_record
        ),
    }
    await coordinator.async_save()

    assert "אילת" in stored[CONF_AREAS]
    assert "קריית שמונה" not in stored[CONF_AREAS]


async def test_restore_skips_expired_records(hass: HomeAssistant) -> None:
    """Test old records filtered at save time are not restored."""
    coordinator = create_coordinator(hass)
    stored: dict[str, dict[str, dict[str, str | int]]] = {}

    def store_data(data: dict[str, dict[str, dict[str, str | int]]]) -> None:
        stored.update(data)

    coordinator._store.async_save = AsyncMock(  # noqa: SLF001
        side_effect=store_data
    )
    coordinator._store.async_load = AsyncMock(return_value=stored)  # noqa: SLF001
    coordinator._no_update = False  # noqa: SLF001
    old_record = Record(
        alertDate="2020-01-01 12:00:00",
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        "אילת": coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            old_record
        )
    }
    await coordinator.async_save()

    coordinator._areas = {}  # noqa: SLF001
    await coordinator.async_restore()
    assert "אילת" not in coordinator._areas  # noqa: SLF001


async def test_restore_ignores_invalid_stored_record(hass: HomeAssistant) -> None:
    """Test invalid restored records are ignored without raising."""
    coordinator = create_coordinator(hass)
    coordinator._store.async_load = AsyncMock(  # noqa: SLF001
        return_value={
            CONF_AREAS: {
                "אילת": {
                    "alertDate": "bad-date",
                    "title": "ירי רקטות וטילים",
                    "data": "אילת",
                    "category": 1,
                    "channel": "website-history",
                },
                "קריית שמונה": {
                    "alertDate": "2025-01-01 12:00:00",
                    "title": "ירי רקטות וטילים",
                    "data": "קריית שמונה",
                    "category": 1,
                    "channel": "website-history",
                },
            }
        }
    )

    await coordinator.async_restore()

    assert "אילת" not in coordinator._areas  # noqa: SLF001
    assert "קריית שמונה" in coordinator._areas  # noqa: SLF001


async def test_get_record_and_metadata_sorting_filters_and_window(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test get_record_and_metadata sorting and filtering semantics."""
    freezer.move_to("2026-01-02 12:00:00+00:00")
    coordinator = create_coordinator(hass)
    classify = coordinator._config_entry.runtime_data.classifier.add_metadata  # noqa: SLF001

    # Same timestamp for two records to validate tie ordering by area.
    same_time = "2026-01-02 13:58:00"
    area_b = classify(
        Record(
            alertDate=same_time,
            title="ירי רקטות וטילים",
            data="בארי",
            category=1,
            channel="website-history",
        )
    )
    area_a = classify(
        Record(
            alertDate=same_time,
            title="ירי רקטות וטילים",
            data="אילות",
            category=1,
            channel="website-history",
        )
    )
    old_update = classify(
        Record(
            alertDate="2026-01-02 13:53:00",
            title="ניתן לצאת מהמרחב המוגן",
            data="נחל עוז",
            category=13,
            channel="website-history",
        )
    )

    coordinator.data = OrefAlertCoordinatorData(
        MappingProxyType(
            {
                area_b.raw.data: area_b,
                area_a.raw.data: area_a,
                old_update.raw.data: old_update,
            }
        )
    )

    oldest_first = coordinator.get_record_and_metadata(
        areas=None,
        record_types=None,
        window=None,
        newer_first=False,
    )
    assert [record.raw.data for record in oldest_first] == ["נחל עוז", "אילות", "בארי"]

    newest_first = coordinator.get_record_and_metadata(
        areas=None,
        record_types=None,
        window=None,
        newer_first=True,
    )
    assert [record.raw.data for record in newest_first] == ["אילות", "בארי", "נחל עוז"]

    alert_only = coordinator.get_record_and_metadata(
        areas=None,
        record_types=[RecordType.ALERT],
        window=None,
        newer_first=True,
    )
    assert [record.raw.data for record in alert_only] == ["אילות", "בארי"]

    area_filtered = coordinator.get_record_and_metadata(
        areas=["בארי"],
        record_types=None,
        window=None,
        newer_first=False,
    )
    assert [record.raw.data for record in area_filtered] == ["בארי"]

    window_filtered = coordinator.get_record_and_metadata(
        areas=None,
        record_types=None,
        window=5,
        newer_first=False,
    )
    assert [record.raw.data for record in window_filtered] == ["אילות", "בארי"]


async def test_updates(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test updates."""
    updates = 0

    def update() -> None:
        nonlocal updates
        updates += 1

    coordinator = create_coordinator(hass)
    coordinator.async_add_listener(update)
    for _ in range(5):
        freezer.tick()
        async_fire_time_changed(hass)
        await coordinator.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)
    assert updates == 5
    assert aioclient_mock.call_count == 15
    await coordinator.async_shutdown()


async def test_alerts_processing(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test alerts processing logic."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.get_records(None, None, None) == load_json_fixture(
        "combined_alerts.json"
    )


async def test_cached_content_on_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test getting cached content on fetch error."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )
    alerts = load_json_fixture("combined_alerts.json")
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.get_records(None, None, None) == alerts

    freezer.tick()  # Skip the throttling threshold
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_urls(aioclient_mock, None, None, exc=Exception("dummy log for testing"))
    await coordinator.async_refresh()
    assert "dummy log for testing" in caplog.text
    assert coordinator.get_records(None, None, None) == alerts


async def test_request_throttling(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test HTTP request throttling logic."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = create_coordinator(hass)
    assert aioclient_mock.call_count == 0
    await coordinator.async_config_entry_first_refresh()
    assert aioclient_mock.call_count == 3
    aioclient_mock.mock_calls.clear()
    assert len(coordinator.get_records(None, None, None)) == 1

    for i in range(10):
        await coordinator.async_refresh()
        assert aioclient_mock.call_count == 3 * (i // 2)
        assert len(coordinator.get_records(None, None, None)) == 1
        freezer.tick(0.7)
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)


async def test_real_time_timestamp(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test real time timestamp."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    for _ in range(7):
        # Timestamp should stay the same for the first 3 minutes.
        assert (
            coordinator.get_records(None, None, None)[0]["alertDate"]
            == "2023-10-07 06:30:00"
        )
        freezer.tick(30)
        await coordinator.async_refresh()
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert (
        coordinator.get_records(None, None, None)[0]["alertDate"]
        == "2023-10-07 06:33:30"
    )
    await coordinator.async_shutdown()


async def test_real_time_in_history(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test de-dup of real time and history."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "single_alert_real_time.json", "history_same_as_real_time.json"
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.get_records(None, None, None)) == 1


async def test_not_modified_real_time_does_not_override_history_update(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test stale real-time payload does not override newer history updates."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.get_records(None, None, None)[0]["category"] == 1

    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, status=HTTPStatus.NOT_MODIFIED)
    aioclient_mock.get(
        OREF_HISTORY_URL,
        text=json.dumps(
            [
                {
                    "alertDate": "2023-10-07 06:30:30",
                    "title": "ניתן לצאת מהמרחב המוגן",
                    "data": "תל אביב - מרכז העיר",
                    "category": 13,
                }
            ]
        ),
    )
    aioclient_mock.get(OREF_HISTORY2_URL, status=HTTPStatus.NOT_MODIFIED)
    freezer.tick(61)
    await coordinator.async_refresh()
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert coordinator.get_records(None, None, None)[0]["category"] == 13
    assert (
        coordinator.get_records(None, None, None)[0]["alertDate"]
        == "2023-10-07 06:30:30"
    )


def test_process_history_alerts_skips_duplicate_area(hass: HomeAssistant) -> None:
    """Test duplicate areas in history payload are skipped."""
    coordinator = create_coordinator(hass)
    records = [
        {
            "data": "בארי",
            "category": 1,
            "alertDate": "2025-01-01 12:00:00",
            "title": "ירי רקטות וטילים",
        },
        {
            "data": "בארי",
            "category": 1,
            "alertDate": "2025-01-01 11:59:00",
            "title": "ירי רקטות וטילים",
        },
    ]

    processed = list(
        coordinator._process_history_alerts(  # noqa: SLF001
            records,
            coordinator._history_to_record,  # noqa: SLF001
        )
    )
    assert len(processed) == 1


def test_history2_to_record_uses_category_desc_as_title() -> None:
    """Test history2 payload conversion uses category_desc for title."""
    record = OrefAlertDataUpdateCoordinator._history2_to_record(  # noqa: SLF001
        {
            "data": "האון",
            "date": "28.02.2026",
            "time": "19:00:07",
            "alertDate": "2026-02-28T19:00:00",
            "category": 13,
            "category_desc": "ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו",
            "matrix_id": 10,
            "rid": 262817,
        },
    )

    assert record.alertDate == "2026-02-28 19:00:00"
    assert record.title == "ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו"
    assert record.data == "האון"
    assert record.category == 13
    assert record.channel == "website-history"


async def test_area_name_typo(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test name typo in real time and history."""
    freezer.move_to("2024-04-14 02:00:00+03:00")
    mock_urls(
        aioclient_mock,
        "alert_real_time_typo.json",
        "alert_history_typo.json",
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.get_records(None, None, None)) == 1
    assert coordinator.get_records(None, None, None)[0]["data"] == "ביר הדאג\u0027"


@pytest.mark.allowed_logs(["Failed to fetch", "Unexpected error fetching oref_alert"])
async def test_json_parsing_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test logging for JSON parsing error."""
    mock_urls(aioclient_mock, "single_alert_real_time_invalid.txt", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.get_records(None, None, None) == []
    assert (
        "JSON parsing failed for "
        "'https://www.oref.org.il/warningMessages/alert/Alerts.json': "
        "'invalid' hex: '696e76616c6964'"
    ) in caplog.text


async def test_synthetic_alert(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test synthetic alert."""
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert len(coordinator.get_records(None, None, None)) == 0
    synthetic_alert_time = dt_util.now(IST)
    areas = ["אילת", "קריית שמונה"]
    coordinator.add_synthetic_alert(
        {
            CONF_AREA: areas,
            CONF_DURATION: 40,
            "category": 4,
            "title": "test",
        }
    )
    freezer.tick(39)
    async_fire_time_changed(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    records = coordinator.get_records(None, None, None)
    assert len(records) == 2
    for index, area in enumerate(areas):
        assert records[index]["data"] == area
        assert records[index]["alertDate"] == synthetic_alert_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        assert records[index]["category"] == 4
        assert records[index]["title"] == "test"
    freezer.tick(2)
    async_fire_time_changed(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.get_records(None, None, None)) == 0
    await coordinator.async_shutdown()


def test_manual_event_end_skips_non_alert_records(hass: HomeAssistant) -> None:
    """Test manual_event_end updates only ALERT records."""
    coordinator = create_coordinator(hass)
    now = dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    pre_alert = Record(
        alertDate=now,
        title="pre alert",
        data="בארי",
        category=PRE_ALERT_CATEGORY,
        channel="website-history",
    )
    alert = Record(
        alertDate=now,
        title="alert",
        data="אילת",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        pre_alert.data: coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            pre_alert
        ),
        alert.data: coordinator._config_entry.runtime_data.classifier.add_metadata(  # noqa: SLF001
            alert
        ),
    }

    coordinator.add_manual_event_end([pre_alert.data, alert.data])

    assert coordinator._areas[pre_alert.data].record_type == RecordType.PRE_ALERT  # noqa: SLF001
    assert coordinator._areas[pre_alert.data].raw.title == pre_alert.title  # noqa: SLF001
    assert coordinator._areas[alert.data].record_type == RecordType.END  # noqa: SLF001
    assert coordinator._areas[alert.data].raw.category == END_ALERT_CATEGORY  # noqa: SLF001
    assert coordinator._areas[alert.data].raw.title == MANUAL_EVENT_END_TITLE  # noqa: SLF001


async def test_http_no_modified(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test HTTP not modified logic."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "single_alert_real_time.json", "single_alert_history.json"
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert len(coordinator.get_records(None, None, None)) == 2

    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, status=HTTPStatus.NOT_MODIFIED)
    aioclient_mock.get(OREF_HISTORY_URL, status=HTTPStatus.NOT_MODIFIED)
    aioclient_mock.get(OREF_HISTORY2_URL, status=HTTPStatus.NOT_MODIFIED)
    freezer.tick()
    await coordinator.async_refresh()
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.get_records(None, None, None)) == 2

    await coordinator.async_shutdown()


async def test_non_alert_category(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test alert category filtering."""
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, None, "alert_categories.json")
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert coordinator.get_records(None, None, None) == load_json_fixture(
        "alert_categories_expected.json", "website-history"
    )
    await coordinator.async_shutdown()


async def test_unknown_real_time_category(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test unknown real time category."""
    mock_urls(aioclient_mock, "unknown_real_time_category.json", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert coordinator.get_records(None, None, None) == []
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("title", "expected_category"),
    [
        ("ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו", END_ALERT_CATEGORY),
        ("בדקות הקרובות צפויות להתקבל התרעות באזורך", PRE_ALERT_CATEGORY),
    ],
    ids=("end_alert", "pre_alert"),
)
def test_current_to_history_format_real_time_message_category(
    hass: HomeAssistant,
    title: str,
    expected_category: int,
) -> None:
    """Test cat=10 real-time message conversion to history update categories."""
    coordinator = create_coordinator(hass)

    records = list(
        coordinator._current_to_history_format(  # noqa: SLF001
            {
                "cat": "10",
                TITLE_FIELD: title,
                AREA_FIELD: ["אילת"],
            }
        )
    )

    assert len(records) == 1
    assert records[0].raw.title == title
    assert records[0].raw.data == "אילת"
    assert records[0].raw.category == expected_category


async def test_disable_all_alerts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test disabling all alerts."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    coordinator = create_coordinator(hass)
    coordinator.async_add_listener(lambda: None)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.get_records(None, None, None)) == 1
    freezer.tick(601)
    async_fire_time_changed(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.get_records(None, None, None)) == 1
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("alert", "expected"),
    [
        (
            {
                "alertDate": "2023-10-07 06:30:00",
                "title": "ירי רקטות וטילים",
                "data": "קריית אונו",
                "category": 1,
            },
            3,
        ),
        (
            {
                "alertDate": "2023-10-07 06:31:00",
                "title": "ירי רקטות וטילים",
                "data": "נחל עוז",
                "category": 2,
            },
            2,
        ),
    ],
    ids=("new", "override"),
)
async def test_channels(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    alert: dict[str, Any],
    expected: int,
) -> None:
    """Test merging channel alerts."""
    freezer.move_to("2023-10-07 06:31:00+03:00")
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    channel: deque[RecordAndMetadata] = deque()
    record = Record(
        alertDate=alert["alertDate"],
        title=alert["title"],
        data=alert["data"],
        category=alert["category"],
        channel="website-history",
    )
    channel.append(
        RecordAndMetadata(
            raw=record,
            raw_dict=asdict(record),
            time=dt_util.parse_datetime(
                alert["alertDate"], raise_on_error=True
            ).replace(tzinfo=IST),
            record_type=RecordType.ALERT,
            expire=None,
        )
    )
    coordinator = create_coordinator(hass, channels=[channel, channel])
    coordinator.async_add_listener(lambda: None)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.get_records(None, None, None)) == expected
    assert coordinator.data.areas[alert["data"]].raw.category == alert["category"]
    await coordinator.async_shutdown()


async def test_channels_are_drained_once(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test channel records are consumed exactly once."""
    mock_urls(aioclient_mock, None, None)
    channel: deque[RecordAndMetadata] = deque()
    record = Record(
        alertDate="2023-10-07 06:30:00",
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    channel.append(
        RecordAndMetadata(
            raw=record,
            raw_dict=asdict(record),
            time=dt_util.parse_datetime(record.alertDate, raise_on_error=True).replace(
                tzinfo=IST
            ),
            record_type=RecordType.ALERT,
            expire=None,
        )
    )
    coordinator = create_coordinator(hass, channels=[channel])
    await coordinator.async_config_entry_first_refresh()
    assert "אילת" in coordinator.data.areas
    assert len(channel) == 0

    coordinator._areas.clear()  # noqa: SLF001
    await coordinator.async_refresh()
    assert coordinator.get_records(None, None, None) == []


@pytest.mark.parametrize(
    ("current_category", "expected_record_type"),
    [
        pytest.param(1, RecordType.ALERT, id="after-alert"),
        pytest.param(END_ALERT_CATEGORY, RecordType.PRE_ALERT, id="after-end"),
    ],
)
async def test_pre_alert_transition_rules(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    current_category: int,
    expected_record_type: RecordType,
) -> None:
    """Test PRE_ALERT transition behavior after alert and end states."""
    freezer.move_to("2025-01-01 10:10:00+03:00")
    mock_urls(aioclient_mock, None, None)
    coordinator = create_coordinator(hass, channels=[deque()])
    classifier = coordinator._config_entry.runtime_data.classifier  # noqa: SLF001
    area = "בארי"
    coordinator._areas = {  # noqa: SLF001
        area: classifier.add_metadata(
            Record(
                alertDate="2025-01-01 10:00:00",
                title="current",
                data=area,
                category=current_category,
                channel="website-history",
            )
        )
    }
    coordinator._channels[0].append(  # noqa: SLF001
        classifier.add_metadata(
            Record(
                alertDate="2025-01-01 10:05:00",
                title="pre alert",
                data=area,
                category=PRE_ALERT_CATEGORY,
                channel="website-history",
            )
        )
    )

    await coordinator.async_refresh()

    assert coordinator.data.areas[area].record_type == expected_record_type


async def test_updater_active(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the updater is refreshing the coordinator."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()
    updater = OrefAlertCoordinatorUpdater(hass, coordinator)
    updater.start()
    assert aioclient_mock.call_count == 3

    for i in range(2, 10):
        freezer.tick(timedelta(minutes=20))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == i * 3

    updater.stop()
    await coordinator.async_shutdown()


async def test_updater_previous_active(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the updater is refreshing after active."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()
    updater = OrefAlertCoordinatorUpdater(hass, coordinator)
    updater.start()

    mock_urls(aioclient_mock, None, None)
    freezer.tick(timedelta(minutes=21))  # Set the active timestamp.
    async_fire_time_changed(hass)
    coordinator.add_synthetic_alert(
        {
            CONF_AREA: ["תל אביב - מרכז העיר"],
            CONF_DURATION: 1000,
            "category": 13,
            "title": "test",
        }
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    # 9:53 leaves 4 additional rounds of updates till 10:00.
    freezer.tick(timedelta(minutes=9, seconds=53))
    for i in range(2, 10):
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == min(i * 3, 15)
        freezer.tick(timedelta(seconds=2))

    updater.stop()
    await coordinator.async_shutdown()


async def test_updater_every_20_seconds(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the updater is refreshing the coordinator at least once every 20 seconds."""
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()
    updater = OrefAlertCoordinatorUpdater(hass, coordinator)
    updater.start()
    assert aioclient_mock.call_count == 3

    for _ in range(3):
        freezer.tick(timedelta(seconds=6))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == 3

    freezer.tick(3)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == 6

    updater.stop()
    await coordinator.async_shutdown()
