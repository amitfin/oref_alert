"""Test utils."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import load_fixture

from custom_components.oref_alert import records_schema
from custom_components.oref_alert.areas_checker import CITIES_MIX_URL
from custom_components.oref_alert.coordinator import OREF_ALERTS_URL, OREF_HISTORY_URL
from custom_components.oref_alert.event import RECORDS_SCHEMA_URL
from custom_components.oref_alert.pushy import API_ENDPOINT as PUSHY_API_ENDPOINT

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

    from custom_components.oref_alert import OrefAlertConfigEntry

PUSHY_DEFAULT_CREDENTIALS = {"token": "user", "auth": "password"}


async def refresh_coordinator(hass: HomeAssistant, config_id: str) -> None:
    """Refresh coordinator data."""
    config: OrefAlertConfigEntry | None = hass.config_entries.async_get_entry(config_id)
    assert config is not None
    await config.runtime_data.coordinator.async_refresh()


def _mock_website_urls(
    aioclient_mock: AiohttpClientMocker,
    real_time_fixture: str | None,
    history_fixture: str | None,
    **kwargs: Any,
) -> None:
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


def _mock_pushy_urls(
    aioclient_mock: AiohttpClientMocker,
    valid_credentials: bool = False,  # noqa: FBT001, FBT002
) -> None:
    """Mock the Pushy URLs."""
    aioclient_mock.post(
        f"{PUSHY_API_ENDPOINT}/register",
        json=PUSHY_DEFAULT_CREDENTIALS if valid_credentials else {},
    )
    for uri in ("auth", "subscribe", "unsubscribe"):
        aioclient_mock.post(
            f"{PUSHY_API_ENDPOINT}/devices/{uri}", json={"success": True}
        )


def _mock_records_schema_url(
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Mock the Records Schema URL."""
    with Path(records_schema.__file__).open() as file:
        aioclient_mock.get(RECORDS_SCHEMA_URL, text=file.read())


def mock_urls(
    aioclient_mock: AiohttpClientMocker,
    real_time_fixture: str | None,
    history_fixture: str | None,
    **kwargs: Any,
) -> None:
    """Mock the URLs."""
    aioclient_mock.clear_requests()
    _mock_website_urls(aioclient_mock, real_time_fixture, history_fixture, **kwargs)
    _mock_pushy_urls(aioclient_mock)
    _mock_records_schema_url(aioclient_mock)


def mock_pushy_urls(
    aioclient_mock: AiohttpClientMocker,
    callback: Callable[[], None] | None = None,
    valid_credentials: bool = True,  # noqa: FBT001, FBT002
) -> None:
    """Mock the URLs."""
    aioclient_mock.clear_requests()
    if callback:
        callback()
    _mock_pushy_urls(aioclient_mock, valid_credentials=valid_credentials)
    _mock_website_urls(aioclient_mock, None, None)
    _mock_records_schema_url(aioclient_mock)


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
