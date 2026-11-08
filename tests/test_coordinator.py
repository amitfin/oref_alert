"""The tests for the coordinator file."""

import json
from collections import deque
from dataclasses import asdict
from datetime import timedelta
from http import HTTPStatus
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import homeassistant.util.dt as dt_util
import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.categories import (
    END_ALERT_CATEGORY,
    PRE_ALERT_CATEGORY,
)
from custom_components.oref_alert.const import (
    AREA_FIELD,
    ATTR_AREA,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DOMAIN,
    EXPIRED_EVENT_END_TITLE,
    IST,
    MANUAL_EVENT_END_TITLE,
    TITLE_FIELD,
    Record,
    RecordAndMetadata,
    RecordType,
)
from custom_components.oref_alert.coordinator import (
    OrefAlertCoordinatorData,
    OrefAlertDataUpdateCoordinator,
)
from custom_components.oref_alert.metadata import (
    OREF_ALERTS_URL,
    OREF_HISTORY2_URL,
    OREF_HISTORY_URL,
    SOME_PARTS_OF_THE_COUNTRY,
)
from custom_components.oref_alert.metadata.areas import AREAS

from .utils import load_json_fixture, mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant.test_util.aiohttp import (
        AiohttpClientMocker,
    )


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
    return coordinator


async def test_init(hass: HomeAssistant) -> None:
    """Test initializing the coordinator."""
    coordinator = create_coordinator(hass)
    assert coordinator.update_interval == timedelta(seconds=20)
    await coordinator.async_config_entry_first_refresh()
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
    coordinator._last_update = dt_util.now()  # noqa: SLF001
    record = Record(
        alertDate=dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        "אילת": coordinator.add_metadata(record)
    }
    await coordinator.async_save()

    coordinator._areas = {}  # noqa: SLF001
    await coordinator.async_restore()

    restored = coordinator._areas.get("אילת")  # noqa: SLF001
    assert restored is not None
    assert restored.raw.data == "אילת"
    assert restored.raw.category == 1
    assert restored.raw.title == "ירי רקטות וטילים"


async def test_get_last_update(hass: HomeAssistant) -> None:
    """Test returning backend update token."""
    coordinator = create_coordinator(hass)
    now = dt_util.now(IST)
    coordinator._last_update = now  # noqa: SLF001

    assert coordinator.get_last_update() == now.isoformat()


async def test_process_history_alerts_skips_duplicate_areas(
    hass: HomeAssistant,
) -> None:
    """Test history processing ignores duplicate area entries after the first one."""
    coordinator = create_coordinator(hass)

    records = [
        {
            AREA_FIELD: "אילת",
            TITLE_FIELD: "ירי רקטות וטילים",
            "alertDate": dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "category": 1,
        },
        {
            AREA_FIELD: "אילת",
            TITLE_FIELD: "ירי רקטות וטילים נוסף",
            "alertDate": dt_util.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "category": 1,
        },
    ]

    processed = list(
        coordinator._process_history_alerts(records, coordinator._history_to_record)  # noqa: SLF001
    )

    assert len(processed) == 1


async def test_all_areas_alias_builds_area_specific_published_data(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all-areas alerts publish concrete area data per expanded area."""
    freezer.move_to("2025-06-13 03:00:00+03:00")
    mock_urls(aioclient_mock, None, None)
    alert = load_json_fixture("single_all_areas_alert_history.json", "website-history")[
        0
    ]
    channel: deque[RecordAndMetadata] = deque()
    record = Record(
        alertDate=alert["alertDate"],
        title=alert["title"],
        data=alert["data"],
        category=alert["category"],
        channel=alert["channel"],
    )
    coordinator = create_coordinator(hass, channels=[channel])
    channel.append(coordinator.add_metadata(record))

    await coordinator.async_config_entry_first_refresh()

    assert coordinator.data.areas["קריית שמונה"].raw.data == "כל הארץ"
    assert coordinator.data.areas["קריית שמונה"].published_data
    assert (
        coordinator.data.areas["קריית שמונה"].published_data[ATTR_AREA] == "קריית שמונה"
    )
    assert coordinator.get_areas_status()[("קריית שמונה")][ATTR_AREA] == "קריית שמונה"


async def test_special_backend_area_is_ignored(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test the backend's partial-country label is skipped entirely."""
    mock_urls(aioclient_mock, None, None)
    channel: deque[RecordAndMetadata] = deque()
    coordinator = create_coordinator(hass, channels=[channel])
    channel.append(
        coordinator.add_metadata(
            Record(
                alertDate="2025-06-13 03:00:00",
                title="ירי רקטות וטילים",
                data=SOME_PARTS_OF_THE_COUNTRY,
                category=1,
                channel="website-history",
            )
        )
    )

    await coordinator.async_refresh()

    assert SOME_PARTS_OF_THE_COUNTRY not in coordinator.data.areas
    assert coordinator.get_records(None, None, None) == []


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
    coordinator._last_update = dt_util.now()  # noqa: SLF001
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
        "אילת": coordinator.add_metadata(fresh_record),
        "קריית שמונה": coordinator.add_metadata(old_record),
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
    coordinator._last_update = dt_util.now()  # noqa: SLF001
    old_record = Record(
        alertDate="2020-01-01 12:00:00",
        title="ירי רקטות וטילים",
        data="אילת",
        category=1,
        channel="website-history",
    )
    coordinator._areas = {  # noqa: SLF001
        "אילת": coordinator.add_metadata(old_record)
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


async def test_get_records_sorting_filters_and_window(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test get_records sorting and filtering semantics."""
    freezer.move_to("2026-01-02 12:00:00+00:00")
    coordinator = create_coordinator(hass)
    classify = coordinator.add_metadata

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

    newest_first = coordinator.get_records(
        areas=None,
        record_types=None,
        window=None,
    )
    assert [record["data"] for record in newest_first] == ["אילות", "בארי", "נחל עוז"]

    alert_only = coordinator.get_records(
        areas=None,
        record_types=[RecordType.ALERT],
        window=None,
    )
    assert [record["data"] for record in alert_only] == ["אילות", "בארי"]

    area_filtered = coordinator.get_records(
        areas=["בארי"],
        record_types=None,
        window=None,
    )
    assert [record["data"] for record in area_filtered] == ["בארי"]

    window_filtered = coordinator.get_records(
        areas=None,
        record_types=None,
        window=5,
    )
    assert [record["data"] for record in window_filtered] == ["אילות", "בארי"]


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


@pytest.mark.parametrize(
    "payload",
    [
        ["unexpected"],
        {"error": "unexpected"},
        {"alarmsGroupedByDate": [{"key": "19.10.2026"}]},
    ],
)
async def test_history2_unexpected_reply(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    payload: Any,
) -> None:
    """Test an unexpected history2 reply is ignored."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_HISTORY2_URL, json=payload)
    coordinator = create_coordinator(hass)

    assert await coordinator._async_fetch_history2() == []  # noqa: SLF001
    assert aioclient_mock.call_count == 1


async def test_history2_payload_updates_areas(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a history2 reply is processed by the coordinator refresh."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, text="")
    aioclient_mock.get(OREF_HISTORY_URL, text="")
    aioclient_mock.get(
        OREF_HISTORY2_URL,
        json={
            "alarmsGroupedByDate": [
                {
                    "key": "19.10.2026",
                    "value": [
                        {
                            "data": "בארי",
                            "date": "19.10.2026",
                            "time": "20:31:16",
                            "dateTime": "2026-10-19T20:31:00",
                            "category": 13,
                            "category_Desc": "האירוע הסתיים",
                        },
                        {
                            "data": "בארי",
                            "date": "19.10.2026",
                            "time": "20:30:42",
                            "dateTime": "2026-10-19T20:30:00",
                            "category": 10,
                            "category_Desc": "חדירת מחבלים",
                        },
                    ],
                }
            ]
        },
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()

    records = coordinator.get_records(None, None, None)
    assert len(records) == 1
    assert records[0]["data"] == "בארי"
    assert records[0]["category"] == 13
    assert records[0]["alertDate"] == "2026-10-19 20:31:16"
    assert records[0]["channel"] == "website-history"


async def test_history2_same_minute_order(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test records of the same minute are ordered by their exact time."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    alert = {
        "data": "בארי",
        "date": "19.10.2026",
        "time": "20:31:05",
        "dateTime": "2026-10-19T20:31:00",
        "category": 1,
        "category_Desc": "ירי רקטות וטילים",
    }
    end = {
        "data": "בארי",
        "date": "19.10.2026",
        "time": "20:31:50",
        "dateTime": "2026-10-19T20:31:00",
        "category": 13,
        "category_Desc": "האירוע הסתיים",
    }
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, text="")
    aioclient_mock.get(OREF_HISTORY_URL, text="")
    aioclient_mock.get(
        OrefAlertDataUpdateCoordinator._history2_page_url(end),  # noqa: SLF001
        json={"alarmsGroupedByDate": []},
    )
    aioclient_mock.get(
        OREF_HISTORY2_URL,
        json={"alarmsGroupedByDate": [{"key": "19.10.2026", "value": [alert, end]}]},
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()

    record = coordinator.get_record("בארי")
    assert record is not None
    assert record["category"] == 13
    assert record["alertDate"] == "2026-10-19 20:31:50"


async def test_history_cutoff(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all history is read initially, and only recent records afterwards."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    history = [
        {
            "alertDate": "2026-10-19 20:31:00",
            "title": "ירי רקטות וטילים",
            "data": "בארי",
            "category": 1,
        },
        {
            "alertDate": "2026-10-19 20:00:00",
            "title": "ירי רקטות וטילים",
            "data": "נחל עוז",
            "category": 1,
        },
        {
            "alertDate": "2026-10-19 19:00:00",
            "title": "האירוע הסתיים",
            "data": "אילת",
            "category": 13,
        },
    ]
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, text="")
    aioclient_mock.get(OREF_HISTORY2_URL, text="")
    aioclient_mock.get(OREF_HISTORY_URL, json=history)
    coordinator = create_coordinator(hass)
    await coordinator.async_refresh()
    assert sorted(coordinator.data.areas) == ["אילת", "בארי", "נחל עוז"]

    # Post initial fetch, records after the first old one are skipped.
    freezer.tick(timedelta(seconds=10))
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, text="")
    aioclient_mock.get(OREF_HISTORY2_URL, text="")
    aioclient_mock.get(
        OREF_HISTORY_URL, json=[*history[:2], {**history[2], "data": "האון"}]
    )
    await coordinator.async_refresh()
    assert "האון" not in coordinator.data.areas


PAGE_SIZE = 200


def _history2_page(time: str, size: int = PAGE_SIZE) -> dict[str, Any]:
    """Return a history2 page of records for different areas."""
    records: list[dict[str, Any]] = [
        {
            "data": area,
            "date": "19.10.2026",
            "time": time,
            "dateTime": f"2026-10-19T{time[:5]}:00",
            "category": 1,
            "category_Desc": "ירי רקטות וטילים",
        }
        for area in sorted(AREAS)[:size]
    ]
    return {
        "alarmsGroupedByDate": [{"key": "19.10.2026", "value": records}]
        if records
        else []
    }


def _history2_page_url(page: dict[str, Any]) -> str:
    """Return the URL of the page that follows the given page."""
    return OrefAlertDataUpdateCoordinator._history2_page_url(  # noqa: SLF001
        page["alarmsGroupedByDate"][-1]["value"][-1]
    )


async def test_history2_paging(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test history2 pages are fetched until an empty page."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    first, second = _history2_page("20:31:10"), _history2_page("20:30:10", 3)
    aioclient_mock.clear_requests()
    aioclient_mock.get(_history2_page_url(second), json=_history2_page("", 0))
    aioclient_mock.get(_history2_page_url(first), json=second)
    aioclient_mock.get(OREF_HISTORY2_URL, json=first)
    coordinator = create_coordinator(hass)

    records = await coordinator._async_fetch_history2()  # noqa: SLF001

    assert len(records) == PAGE_SIZE + 3
    assert aioclient_mock.call_count == 3
    assert "lastCityName=" in str(aioclient_mock.mock_calls[1][1])
    assert list(coordinator._http_replies) == [OREF_HISTORY2_URL]  # noqa: SLF001


async def test_history2_date_groups(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test records of all date groups are returned, newest first."""
    freezer.move_to("2026-10-20 00:02:00+03:00")
    after_midnight = {
        "data": "בארי",
        "date": "20.10.2026",
        "time": "00:01:10",
        "dateTime": "2026-10-20T00:01:00",
        "category": 1,
        "category_Desc": "ירי רקטות וטילים",
    }
    before_midnight = {
        "data": "נחל עוז",
        "date": "19.10.2026",
        "time": "23:59:10",
        "dateTime": "2026-10-19T23:59:00",
        "category": 1,
        "category_Desc": "ירי רקטות וטילים",
    }
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        OrefAlertDataUpdateCoordinator._history2_page_url(before_midnight),  # noqa: SLF001
        json={"alarmsGroupedByDate": []},
    )
    aioclient_mock.get(
        OREF_HISTORY2_URL,
        json={
            "alarmsGroupedByDate": [
                {"key": "20.10.2026", "value": [after_midnight]},
                {"key": "19.10.2026", "value": [before_midnight]},
            ]
        },
    )
    coordinator = create_coordinator(hass)

    assert await coordinator._async_fetch_history2() == [  # noqa: SLF001
        after_midnight,
        before_midnight,
    ]
    assert aioclient_mock.call_count == 2


async def test_load_history(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the records of the last day are loaded, and listeners are updated."""
    freezer.move_to("2026-10-19 22:30:00+03:00")
    alert = {
        "data": "בארי",
        "date": "19.10.2026",
        "time": "21:00:10",
        "dateTime": "2026-10-19T21:00:00",
        "category": 1,
        "category_Desc": "ירי רקטות וטילים",
    }
    end = {
        "data": "נחל עוז",
        "date": "19.10.2026",
        "time": "08:00:10",
        "dateTime": "2026-10-19T08:00:00",
        "category": 13,
        "category_Desc": "האירוע הסתיים",
    }
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        OrefAlertDataUpdateCoordinator._history2_page_url(end),  # noqa: SLF001
        json={"alarmsGroupedByDate": []},
    )
    aioclient_mock.get(
        OREF_HISTORY2_URL,
        json={"alarmsGroupedByDate": [{"key": "19.10.2026", "value": [alert, end]}]},
    )
    coordinator = create_coordinator(hass)
    # A refresh has just fetched the first page.
    coordinator._http_replies[OREF_HISTORY2_URL] = ("", dt_util.now().timestamp())  # noqa: SLF001

    with patch.object(coordinator, "async_update_listeners") as update_listeners:
        await coordinator.async_load_history()
        assert update_listeners.call_count == 1
        assert aioclient_mock.call_count == 2
        assert {
            area: record.raw.category for area, record in coordinator.data.areas.items()
        } == {"בארי": 1, "נחל עוז": 13}

        # The same records again don't update anything.
        freezer.tick(1)
        await coordinator.async_load_history()
        assert update_listeners.call_count == 1
        assert aioclient_mock.call_count == 4


async def test_history2_paging_stops_at_old_records(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test paging stops at records older than the recent records window."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_HISTORY2_URL, json=_history2_page("20:26:10"))
    coordinator = create_coordinator(hass)

    assert len(await coordinator._async_fetch_history2()) == PAGE_SIZE  # noqa: SLF001
    assert aioclient_mock.call_count == 1


async def test_history2_paging_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a failed page stops the paging."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    first = _history2_page("20:31:10")
    aioclient_mock.clear_requests()
    aioclient_mock.get(_history2_page_url(first), text="Access Denied")
    aioclient_mock.get(OREF_HISTORY2_URL, json=first)
    coordinator = create_coordinator(hass)

    assert len(await coordinator._async_fetch_history2()) == PAGE_SIZE  # noqa: SLF001
    assert list(coordinator._http_replies) == [OREF_HISTORY2_URL]  # noqa: SLF001


async def test_history2_paging_max_pages(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test paging stops at the maximal number of pages."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    first = _history2_page("20:31:10")
    aioclient_mock.clear_requests()
    aioclient_mock.get(_history2_page_url(first), json=_history2_page("20:30:10"))
    aioclient_mock.get(OREF_HISTORY2_URL, json=first)
    coordinator = create_coordinator(hass)

    with patch("custom_components.oref_alert.coordinator.HISTORY2_MAX_PAGES", 2):
        records = await coordinator._async_fetch_history2()  # noqa: SLF001

    assert len(records) == 2 * PAGE_SIZE
    assert aioclient_mock.call_count == 2


async def test_history2_paging_stuck(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test paging stops when the next page doesn't move forward."""
    freezer.move_to("2026-10-19 20:32:00+03:00")
    first = _history2_page("20:31:10")
    aioclient_mock.clear_requests()
    aioclient_mock.get(_history2_page_url(first), json=first)
    aioclient_mock.get(OREF_HISTORY2_URL, json=first)
    coordinator = create_coordinator(hass)

    await coordinator._async_fetch_history2()  # noqa: SLF001

    assert aioclient_mock.call_count == 2


def test_history2_to_record_uses_category_desc_as_title() -> None:
    """Test history2 payload conversion uses category_Desc for title."""
    record = OrefAlertDataUpdateCoordinator._history2_to_record(  # noqa: SLF001
        {
            "data": "האון",
            "date": "28.02.2026",
            "time": "19:00:07",
            "dateTime": "2026-02-28T19:00:00",
            "category": 13,
            "category_Desc": "ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו",
            "matrixId": 10,
            "rid": 262817,
        },
    )

    assert record.alertDate == "2026-02-28 19:00:07"
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
    """Test synthetic alert transitions to END after expiring."""
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
    records = coordinator.get_records(None, None, None)
    assert len(records) == 2
    for index, area in enumerate(areas):
        assert records[index]["data"] == area
        assert records[index]["category"] == END_ALERT_CATEGORY
        assert records[index]["title"] == EXPIRED_EVENT_END_TITLE
        assert records[index]["channel"] == "synthetic"
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
        pre_alert.data: coordinator.add_metadata(pre_alert),
        alert.data: coordinator.add_metadata(alert),
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
    "title",
    [
        "ניתן לצאת מהמרחב המוגן אך יש להישאר בקרבתו",
        "בדקות הקרובות צפויות להתקבל התרעות באזורך",
    ],
    ids=("end_alert", "pre_alert"),
)
def test_current_to_history_format_real_time_message_category(
    hass: HomeAssistant,
    title: str,
) -> None:
    """Test cat=10 real-time message is ignored."""
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

    assert records == []


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

    updates = 0

    def update() -> None:
        nonlocal updates
        updates += 1

    coordinator = create_coordinator(hass, channels=[channel, channel])
    coordinator.async_add_listener(update)
    await coordinator.async_config_entry_first_refresh()
    assert updates == 1
    assert len(coordinator.get_records(None, None, None)) == 1

    await hass.async_block_till_done()
    assert updates == 2
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
    area = "בארי"
    coordinator._areas = {  # noqa: SLF001
        area: coordinator.add_metadata(
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
        coordinator.add_metadata(
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
