"""The tests for the coordinator file."""
from datetime import timedelta
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.const import (
    DOMAIN,
    CONF_ALERT_MAX_AGE,
    CONF_POLL_INTERVAL,
    DEFAULT_ALERT_MAX_AGE,
)
from custom_components.oref_alert.coordinator import OrefAlertDataUpdateCoordinator

from .utils import load_json_fixture, mock_urls

DEFAULT_CONFIG_ENTRY = MockConfigEntry(
    domain=DOMAIN, options={CONF_ALERT_MAX_AGE: DEFAULT_ALERT_MAX_AGE}
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
                CONF_ALERT_MAX_AGE: DEFAULT_ALERT_MAX_AGE,
            },
        ),
    )
    coordinator.async_add_listener(update)
    for _ in range(10):
        freezer.tick(timedelta(seconds=50))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert updates == 5
    assert aioclient_mock.call_count == 10
    await coordinator.async_shutdown()


async def test_server_down_during_init(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test errors on HTTP requests during initialization."""
    mock_urls(aioclient_mock, None, None, exc=Exception("test"))
    coordinator = OrefAlertDataUpdateCoordinator(hass, DEFAULT_CONFIG_ENTRY)
    with pytest.raises(ConfigEntryNotReady):
        await coordinator.async_config_entry_first_refresh()
    assert "Update failed after 3 retries" in caplog.text


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
        MockConfigEntry(domain=DOMAIN, options={CONF_ALERT_MAX_AGE: 1}),
    )
    await coordinator.async_config_entry_first_refresh()
    inactive_alert, active_alert = load_json_fixture("multi_alerts_history.json")
    assert coordinator.data.alerts == [active_alert, inactive_alert]
    assert coordinator.data.active_alerts == [active_alert]