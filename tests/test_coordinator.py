"""The tests for the coordinator file."""

from datetime import timedelta

import homeassistant.util.dt as dt_util
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_POLL_INTERVAL,
    DEFAULT_ALERT_ACTIVE_DURATION,
    DOMAIN,
    IST,
)
from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator

from .utils import load_json_fixture, mock_urls

DEFAULT_CONFIG_ENTRY = MockConfigEntry(
    domain=DOMAIN, options={CONF_ALERT_ACTIVE_DURATION: DEFAULT_ALERT_ACTIVE_DURATION}
)


async def test_init(hass: HomeAssistant) -> None:
    """Test initializing the coordinator."""
    await OrefAlertDataUpdateCoordinator(
        hass, DEFAULT_CONFIG_ENTRY
    ).async_config_entry_first_refresh()
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

    coordinator = OrefAlertDataUpdateCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            options={
                CONF_POLL_INTERVAL: 100,
                CONF_ALERT_ACTIVE_DURATION: DEFAULT_ALERT_ACTIVE_DURATION,
            },
        ),
    )
    coordinator.async_add_listener(update)
    for _ in range(10):
        freezer.tick(timedelta(seconds=50))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert updates == 5
    assert aioclient_mock.call_count == 10
    await coordinator.async_shutdown()


async def test_server_down_during_init(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test errors on HTTP requests during initialization."""
    mock_urls(aioclient_mock, None, None, exc=Exception("dummy log for testing"))
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
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
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.data.alerts == load_json_fixture("combined_alerts.json")
    assert coordinator.data.active_alerts == load_json_fixture("combined_alerts.json")


async def test_active_alerts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test active alerts logic."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    coordinator = OrefAlertDataUpdateCoordinator(
        hass,
        MockConfigEntry(domain=DOMAIN, options={CONF_ALERT_ACTIVE_DURATION: 1}),
    )
    await coordinator.async_config_entry_first_refresh()
    inactive_alert, active_alert = load_json_fixture("multi_alerts_history.json")
    assert coordinator.data.alerts == [active_alert, inactive_alert]
    assert coordinator.data.active_alerts == [active_alert]


async def test_real_time_timestamp(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test real time timestamp."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    for _ in range(25):
        # Timestamp should stay the same for the first 2 minutes.
        assert coordinator.data.alerts[0]["alertDate"] == "2023-10-07 06:30:00"
        freezer.tick(timedelta(seconds=5))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
    assert coordinator.data.alerts[0]["alertDate"] == "2023-10-07 06:32:05"
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
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
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
        "single_alert_real_time_typo.json",
        "single_alert_history_typo.json",
    )
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
    await coordinator.async_config_entry_first_refresh()
    assert len(coordinator.data.alerts) == 1
    assert coordinator.data.alerts[0]["data"] == "ביר הדאג\u0027"


async def test_synthetic_alert(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test synthetic alert."""
    coordinator = OrefAlertDataUpdateCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            options={CONF_POLL_INTERVAL: 1, CONF_ALERT_ACTIVE_DURATION: 100},
        ),
    )
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_add_listener(lambda: None)
    assert len(coordinator.data.alerts) == 0
    synthetic_alert_time = dt_util.now(IST)
    coordinator.add_synthetic_alert("קריית שמונה", 40)
    freezer.tick(timedelta(seconds=39))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 1
    assert coordinator.data.alerts[0]["data"] == "קריית שמונה"
    assert coordinator.data.alerts[0]["alertDate"] == synthetic_alert_time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(coordinator.data.alerts) == 0
    await coordinator.async_shutdown()
