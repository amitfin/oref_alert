"""Tests for tzevaadom file."""

from __future__ import annotations

import json
from asyncio import Event
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import WSMessage, WSMsgType
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
)
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
    ("overrides", "expected_state"),
    [
        ({}, STATE_ON),
        ({"isDrill": True}, STATE_OFF),
        ({"cities": ["dummy"]}, STATE_OFF),
    ],
    ids=("plain", "drill", "invalid area"),
)
async def test_message(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    overrides: dict,
    expected_state: str,
) -> None:
    """Test tzevaadom message."""
    freezer.move_to("2025-06-30T15:00:00+0300")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    alert = load_json_fixture("single_alert_tzevaadom.json")
    alert["data"].update(overrides)
    data = json.dumps(alert).encode("utf-8")
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        state = hass.states.get(ENTITY_ID)
        assert state is not None
        assert state.state == expected_state
        await cleanup_test(hass, config_entry)
    assert f"WS message: {alert}" in caplog.text


@pytest.mark.parametrize(
    ("message_type", "log_message"),
    [
        (WSMsgType.BINARY, "WS system message (BINARY), ignoring."),
        (WSMsgType.PING, "WS system message (PING), ignoring."),
        (WSMsgType.PONG, "WS system message (PONG), ignoring."),
        (WSMsgType.ERROR, "Unexpected WS message (ERROR): {}"),
        (WSMsgType.TEXT, "Error processing WS message"),
    ],
    ids=("binary", "ping", "pong", "error", "invalid"),
)
async def test_other_messages(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    message_type: WSMsgType,
    log_message: str,
) -> None:
    """Test tzevaadom non-text message types."""
    with mock_ws([WSMessage(type=message_type, data="{}", extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.wait_closed()
        await cleanup_test(hass, config_entry)
    assert log_message in caplog.text
