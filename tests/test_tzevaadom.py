"""Tests for tzevaadom file."""

from __future__ import annotations

import asyncio
import json
from asyncio import Event
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiohttp import WSMessage, WSMsgType
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ATTR_SELECTED_AREAS_UPDATES,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
)
from custom_components.oref_alert.tzevaadom import TzevaAdomNotifications
from tests.utils import load_json_fixture

if TYPE_CHECKING:
    from collections.abc import Generator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS = {CONF_AREAS: ["גבעת שמואל"], CONF_ALERT_ACTIVE_DURATION: 10}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


@contextmanager
def mock_ws(messages: list[WSMessage]) -> Generator[AsyncMock]:
    """Mock WebSocket connection for testing."""
    ws_closed = Event()
    ws = AsyncMock()
    ws.receive = AsyncMock(side_effect=messages)
    ws.close = AsyncMock(side_effect=lambda: ws_closed.set())
    ws.wait_closed = lambda: ws_closed.wait()

    with (
        patch("aiohttp.ClientSession.ws_connect") as connect,
        patch("secrets.SystemRandom.uniform", return_value=0),
    ):
        connect.side_effect = [AsyncMock(__aenter__=AsyncMock(return_value=ws))]
        yield ws


async def setup_test(
    hass: HomeAssistant,
) -> ConfigEntry:
    """Set up steps for a test case."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry


async def cleanup_test(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Clean up steps for a test case."""
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_lifecycle(hass: HomeAssistant) -> None:
    """Test ws lifecycle."""
    with mock_ws([]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        await cleanup_test(hass, config_entry)
    ws.close.assert_called_once()


@pytest.mark.parametrize(
    ("alert", "overrides", "expected_state", "expected_updates"),
    [
        (True, {}, STATE_ON, []),
        (True, {"isDrill": True}, STATE_OFF, []),
        (True, {"cities": ["dummy"]}, STATE_OFF, []),
        (
            False,
            {},
            STATE_OFF,
            [
                {
                    "alertDate": "2025-06-30 15:00:00",
                    "title": "בדקות הקרובות צפויות להתקבל התרעות באזורך",
                    "data": "גבעת שמואל",
                    "category": 14,
                    "channel": "tzevaadom",
                }
            ],
        ),
        (False, {"citiesIds": None}, STATE_OFF, []),
    ],
    ids=("plain", "drill", "invalid area", "update", "no cities"),
)
async def test_message(  # noqa: PLR0913
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    alert: bool,  # noqa: FBT001
    overrides: dict,
    expected_state: str,
    expected_updates: list[dict],
) -> None:
    """Test tzevaadom message."""
    freezer.move_to("2025-06-30T15:00:00+0300")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    message = load_json_fixture(
        f"single_{'alert' if alert else 'update'}_tzevaadom.json"
    )
    message["data"].update(overrides)
    data = json.dumps(message).encode("utf-8")
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        state = hass.states.get(ENTITY_ID)
        assert state is not None
        assert state.state == expected_state
        assert state.attributes[ATTR_SELECTED_AREAS_UPDATES] == expected_updates
        await cleanup_test(hass, config_entry)
    assert f"WS message: {message}" in caplog.text


@pytest.mark.parametrize(
    ("area", "valid"),
    [
        ("פתח תקווה", True),
        ("1פתח תקווה", True),
        ("אשדוד -יא,יב,טו,יז,מרינה,סיטי", True),  # noqa: RUF001
        ("אשדוד -יא,יב,טו,יז,מרינה,סיט", True),  # noqa: RUF001
    ],
    ids=("valid", "invalid", "valid2", "truncated and fixed"),
)
async def test_area_name_validity(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    area: str,
    valid: bool,  # noqa: FBT001
) -> None:
    """Test valid and invalid area names."""
    data = json.dumps(
        {**load_json_fixture("single_alert_tzevaadom.json"), "cities": [area]}
    ).encode("utf-8")
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        await cleanup_test(hass, config_entry)
    assert (f"Unknown area '{area}' in Tzeva Adom alert, skipping." in caplog.text) == (
        not valid
    )


@pytest.mark.parametrize(
    ("message_type", "log_message", "data"),
    [
        (WSMsgType.BINARY, "WS system message (BINARY), ignoring.", None),
        (WSMsgType.PING, "WS system message (PING), ignoring.", None),
        (WSMsgType.PONG, "WS system message (PONG), ignoring.", None),
        (WSMsgType.ERROR, "WS system message (ERROR), ignoring.", None),
        (WSMsgType.CLOSING, " ", None),
        (WSMsgType.TEXT, "Error processing WS message", None),
        (WSMsgType.TEXT, "Tzevaadom unknown message type: test", '{"type": "test"}'),
    ],
    ids=(
        "binary",
        "ping",
        "pong",
        "error",
        "closing",
        "invalid",
        "unknown internal type",
    ),
)
async def test_other_messages(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    message_type: WSMsgType,
    log_message: str,
    data: str | None,
) -> None:
    """Test tzevaadom message types."""
    with mock_ws([WSMessage(type=message_type, data=data or "{}", extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        await cleanup_test(hass, config_entry)
    assert log_message in caplog.text


async def test_duplicate(hass: HomeAssistant) -> None:
    """Test 2 messages with the same ID."""
    alert = load_json_fixture("single_alert_tzevaadom.json")
    data = json.dumps(alert).encode("utf-8")
    tzevaadom = TzevaAdomNotifications(
        hass, MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    )
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)] * 3) as ws:
        await tzevaadom.start()
        await ws.wait_closed()
        assert len(tzevaadom.alerts.items()) == 1
        await tzevaadom.stop()


async def test_ws_receive_canceled(hass: HomeAssistant) -> None:
    """Test that we cancel receive() on shutdown."""
    receive = asyncio.Future()
    with mock_ws([]) as ws:
        ws.receive = Mock(return_value=receive)
        ws.close = AsyncMock(side_effect=lambda: receive.set_result("test"))
        config_entry = await setup_test(hass)
        await cleanup_test(hass, config_entry)
    assert (await receive) == "test"
