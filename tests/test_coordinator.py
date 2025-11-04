"""The tests for the coordinator file."""

from datetime import timedelta
from http import HTTPStatus
from typing import Any

import homeassistant.util.dt as dt_util
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALL_ALERTS_ATTRIBUTES,
    CONF_AREA,
    CONF_DURATION,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DOMAIN,
    IST,
)
from custom_components.oref_alert.coordinator import (
    OREF_ALERTS_URL,
    OREF_HISTORY_URL,
    OrefAlertCoordinatorData,
    OrefAlertCoordinatorUpdater,
    OrefAlertDataUpdateCoordinator,
)
from custom_components.oref_alert.ttl_deque import TTLDeque

from .utils import load_json_fixture, mock_urls


@pytest.mark.parametrize(
    ("items", "alerts", "active_alerts", "update"),
    [
        ([], [], [], []),
        (
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [],
        ),
        (
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 13,
                }
            ],
            [],
            [],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 13,
                }
            ],
        ),
        (
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                },
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 13,
                },
            ],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [
                {
                    "alertDate": "2025-04-26 03:30:00",
                    "title": "",
                    "data": "area1",
                    "category": 13,
                },
            ],
        ),
        (
            [
                {
                    "alertDate": "2025-04-26 03:19:59",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                },
                {
                    "alertDate": "2025-04-26 03:19:59",
                    "title": "",
                    "data": "area1",
                    "category": 13,
                },
            ],
            [
                {
                    "alertDate": "2025-04-26 03:19:59",
                    "title": "",
                    "data": "area1",
                    "category": 1,
                }
            ],
            [],
            [],
        ),
    ],
    ids=(
        "empty",
        "simple",
        "update",
        "active update",
        "post active",
    ),
)
def test_coordinator_data(
    freezer: FrozenDateTimeFactory,
    items: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    active_alerts: list[dict[str, Any]],
    update: list[dict[str, Any]],
) -> None:
    """Test the coordinator data class."""
    freezer.move_to("2025-04-26 03:30:00+03:00")
    coordinator_data = OrefAlertCoordinatorData(items, 10)  # pyright: ignore[reportArgumentType]
    assert coordinator_data.items == items
    assert coordinator_data.alerts == alerts
    assert coordinator_data.active_alerts == active_alerts
    assert coordinator_data.updates == update


def create_coordinator(
    hass: HomeAssistant,
    options: dict | None = None,
    channels: list[TTLDeque] | None = None,
) -> OrefAlertDataUpdateCoordinator:
    """Create a test coordinator."""
    config = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_ALERT_ACTIVE_DURATION: DEFAULT_ALERT_ACTIVE_DURATION,
            CONF_ALL_ALERTS_ATTRIBUTES: True,
            **(options if options else {}),
        },
    )
    config.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    coordinator = OrefAlertDataUpdateCoordinator(hass, config, channels or [])
    coordinator.config_entry = config
    return coordinator


async def test_init(hass: HomeAssistant) -> None:
    """Test initializing the coordinator."""
    await create_coordinator(hass).async_config_entry_first_refresh()
    # No pending refresh since there are no listeners


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
    assert aioclient_mock.call_count == 10
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "allowed_logs",
    [["Failed to fetch", "Unexpected error fetching oref_alert"]],
    indirect=True,
)
async def test_server_down_during_init(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test errors on HTTP requests during initialization."""
    mock_urls(aioclient_mock, None, None, exc=Exception("dummy log for testing"))
    coordinator = create_coordinator(hass)
    with pytest.raises(ConfigEntryNotReady):
        await coordinator.async_config_entry_first_refresh()
    assert "dummy log for testing" in caplog.text


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
    assert coordinator.data.alerts == load_json_fixture("combined_alerts.json")
    assert coordinator.data.active_alerts == load_json_fixture("combined_alerts.json")


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
    assert coordinator.data.alerts == alerts
    assert coordinator.data.active_alerts == alerts

    freezer.tick()  # Skip the throttling threshold
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_urls(aioclient_mock, None, None, exc=Exception("dummy log for testing"))
    await coordinator.async_refresh()
    assert "dummy log for testing" in caplog.text
    assert coordinator.data.alerts == alerts
    assert coordinator.data.active_alerts == alerts


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
    assert aioclient_mock.call_count == 2
    aioclient_mock.mock_calls.clear()
    assert len(coordinator.data.alerts) == 1

    for i in range(10):
        await coordinator.async_refresh()
        assert aioclient_mock.call_count == 2 * (i // 2)
        assert len(coordinator.data.alerts) == 1
        freezer.tick(0.7)
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)


async def test_active_alerts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test active alerts logic."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    coordinator = create_coordinator(hass, {CONF_ALERT_ACTIVE_DURATION: 1})
    await coordinator.async_config_entry_first_refresh()
    inactive_alert, active_alert = load_json_fixture(
        "multi_alerts_history.json", "website-history"
    )
    assert coordinator.data.alerts == [active_alert, inactive_alert]
    assert coordinator.data.active_alerts == [active_alert]


@pytest.mark.parametrize(
    "alert_file",
    ["single_alert_real_time.json", "single_update_real_time.json"],
    ids=("alert", "update"),
)
async def test_real_time_timestamp(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    alert_file: str,
) -> None:
    """Test real time timestamp."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, alert_file, None)
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    for _ in range(9):
        # Timestamp should stay the same for the first 2 minutes.
        assert coordinator.data.items[0]["alertDate"] == "2023-10-07 06:30:00"
        freezer.tick(15)
        await coordinator.async_refresh()
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.items[0]["alertDate"] == "2023-10-07 06:32:15"
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
    assert len(coordinator.data.alerts) == 1


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
    assert len(coordinator.data.alerts) == 1
    assert coordinator.data.alerts[0]["data"] == "ביר הדאג\u0027"


@pytest.mark.parametrize(
    "allowed_logs",
    [["Failed to fetch", "Unexpected error fetching oref_alert"]],
    indirect=True,
)
async def test_json_parsing_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test logging for JSON parsing error."""
    mock_urls(aioclient_mock, "single_alert_real_time_invalid.txt", None)
    coordinator = create_coordinator(hass)
    with pytest.raises(ConfigEntryNotReady):
        await coordinator.async_config_entry_first_refresh()
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
    coordinator = create_coordinator(hass, {CONF_ALERT_ACTIVE_DURATION: 100})
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert len(coordinator.data.alerts) == 0
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
    assert len(coordinator.data.alerts) == 2
    for index, area in enumerate(areas):
        assert coordinator.data.alerts[index]["data"] == area
        assert coordinator.data.alerts[index][
            "alertDate"
        ] == synthetic_alert_time.strftime("%Y-%m-%d %H:%M:%S")
        assert coordinator.data.alerts[index]["category"] == 4
        assert coordinator.data.alerts[index]["title"] == "test"
    freezer.tick(2)
    async_fire_time_changed(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 0
    await coordinator.async_shutdown()


async def test_is_synthetic_alert(
    hass: HomeAssistant,
) -> None:
    """Test is_synthetic_alert method."""
    coordinator = create_coordinator(hass)
    coordinator.add_synthetic_alert(
        {
            CONF_AREA: ["אליפז ומכרות תמנע"],
            CONF_DURATION: 10,
            "category": 2,
            "title": "test",
        }
    )
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.is_synthetic_alert(coordinator.data.alerts[0])
    await coordinator.async_shutdown()


async def test_http_cache(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test HTTP caching."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "single_alert_real_time.json", "single_alert_history.json"
    )
    coordinator = create_coordinator(hass)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert len(coordinator.data.alerts) == 2

    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, status=HTTPStatus.NOT_MODIFIED)
    aioclient_mock.get(OREF_HISTORY_URL, status=HTTPStatus.NOT_MODIFIED)
    freezer.tick()
    await coordinator.async_refresh()
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 2

    aioclient_mock.clear_requests()
    aioclient_mock.get(OREF_ALERTS_URL, text="")
    aioclient_mock.get(OREF_HISTORY_URL, status=HTTPStatus.NOT_MODIFIED)
    freezer.tick()
    await coordinator.async_refresh()
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 1

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
    expected_alerts = load_json_fixture(
        "alert_categories_expected.json", "website-history"
    )
    assert coordinator.data.alerts == expected_alerts
    assert coordinator.data.active_alerts == expected_alerts
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
    assert coordinator.data.items == []
    await coordinator.async_shutdown()


async def test_disable_all_alerts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test disabling all alerts."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    coordinator = create_coordinator(hass, {CONF_ALL_ALERTS_ATTRIBUTES: False})
    coordinator.async_add_listener(lambda: None)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.data.alerts) == 1
    freezer.tick(601)
    async_fire_time_changed(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 0
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("alerts", "expected"),
    [
        (
            [
                {
                    "alertDate": "2023-10-07 06:30:00",
                    "title": "ירי רקטות וטילים",
                    "data": "קריית אונו",
                    "category": 1,
                }
            ],
            3,
        ),
        (
            [
                {
                    "alertDate": "2023-10-07 06:30:00",
                    "title": "ירי רקטות וטילים",
                    "data": "בארי",
                    "category": 1,
                }
            ],
            2,
        ),
        (
            [
                {
                    "alertDate": "2023-10-07 06:31:00",
                    "title": "ירי רקטות וטילים",
                    "data": "נחל עוז",
                    "category": 1,
                }
            ],
            3,
        ),
    ],
    ids=("new", "de-dup", "stop searching"),
)
async def test_channels(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    alerts: list[dict],
    expected: int,
) -> None:
    """Test merging channel alerts."""
    freezer.move_to("2023-10-07 06:31:00+03:00")
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    channel = TTLDeque(10)
    for alert in alerts:
        channel.add(alert)
    coordinator = create_coordinator(hass, channels=[channel, channel])
    coordinator.async_add_listener(lambda: None)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.data.alerts) == expected
    await coordinator.async_shutdown()


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
    assert aioclient_mock.call_count == 2

    for i in range(2, 10):
        freezer.tick(timedelta(minutes=20))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == i * 2

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
    freezer.tick(timedelta(minutes=11))  # Set the active timestamp.
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    # 19:53 leaves 4 additional rounds of updates till 20:00.
    freezer.tick(timedelta(minutes=19, seconds=53))
    for i in range(2, 10):
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == min(i * 2, 10)
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
    assert aioclient_mock.call_count == 2

    for _ in range(3):
        freezer.tick(timedelta(seconds=6))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        assert aioclient_mock.call_count == 2

    freezer.tick(3)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert aioclient_mock.call_count == 4

    updater.stop()
    await coordinator.async_shutdown()
