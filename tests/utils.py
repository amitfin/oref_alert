"""Test utils."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import load_fixture
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.areas_checker import CITIES_MIX_URL
from custom_components.oref_alert.coordinator import OREF_ALERTS_URL, OREF_HISTORY_URL

if TYPE_CHECKING:
    from custom_components.oref_alert import OrefAlertConfigEntry


async def refresh_coordinator(hass: HomeAssistant, config_id: str) -> None:
    """Refresh coordinator data."""
    config: OrefAlertConfigEntry | None = hass.config_entries.async_get_entry(config_id)
    assert config is not None
    await config.runtime_data.coordinator.async_refresh()


def mock_urls(
    aioclient_mock: AiohttpClientMocker,
    real_time_fixture: str | None,
    history_fixture: str | None,
    **kwargs: Any,
) -> None:
    """Mock the URLs."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        OREF_ALERTS_URL,
        text=load_fixture(real_time_fixture) if real_time_fixture else "",
        **kwargs,
    )
    aioclient_mock.get(
        OREF_HISTORY_URL,
        text=load_fixture(history_fixture) if history_fixture else "",
        **kwargs,
    )
    aioclient_mock.get(
        CITIES_MIX_URL,
        text=load_fixture("GetCitiesMix.json"),
        **kwargs,
    )


def fixture_path(file_name: str) -> Path:
    """Return absolute path of a fixture file."""
    return Path(__file__).resolve().parent / "fixtures" / file_name


def load_json_fixture(file_name: str, channel: str | None = None) -> Any:
    """Return a json object from a local fixture file."""
    with fixture_path(file_name).open(
        encoding="utf-8",
    ) as file:
        content = json.load(file)
    if channel:
        for alert in content:
            alert["channel"] = channel
    return content
