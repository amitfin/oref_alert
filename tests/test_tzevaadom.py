"""Tests for tzevaadom file."""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import WSMessage, WSMsgType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS = {CONF_AREAS: ["גבעת שמואל"], CONF_ALERT_ACTIVE_DURATION: 10}


@contextmanager
def mock_ws(messages: list[WSMessage]) -> Generator[AsyncMock]:
    """Mock WebSocket connection for testing."""
    with patch("aiohttp.ClientSession.ws_connect") as connect:
        ws = AsyncMock()
        ws.receive = AsyncMock(side_effect=messages)
        connect.return_value.__aenter__.return_value = ws
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
        await cleanup_test(hass, config_entry)
    ws.close.assert_called_once()


async def test_message(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test tzevaadom message."""
    with mock_ws(
        [WSMessage(type=WSMsgType.TEXT, data=json.dumps({"test": "test"}), extra=None)]
    ):
        config_entry = await setup_test(hass)
        await cleanup_test(hass, config_entry)
    assert "WS message: {'test': 'test'}" in caplog.text


@pytest.mark.parametrize(
    ("message_type", "log_message"),
    [
        (WSMsgType.BINARY, "WS system message (BINARY), ignoring."),
        (WSMsgType.PING, "WS system message (PING), ignoring."),
        (WSMsgType.PONG, "WS system message (PONG), ignoring."),
        (WSMsgType.ERROR, "Unexpected WS message (ERROR): None"),
    ],
    ids=("binary", "ping", "pong", "error"),
)
async def test_other_messages(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    message_type: WSMsgType,
    log_message: str,
) -> None:
    """Test tzevaadom non-text message types."""
    with mock_ws([WSMessage(type=message_type, data=None, extra=None)]):
        config_entry = await setup_test(hass)
        await cleanup_test(hass, config_entry)
    assert log_message in caplog.text


async def test_reconnect(hass: HomeAssistant) -> None:
    """Test WebSocket reconnect."""
    ws_closed = asyncio.Event()
    ws = AsyncMock()
    ws.close = AsyncMock(side_effect=lambda: ws_closed.set())

    with (
        patch("aiohttp.ClientSession.ws_connect") as mock_connect,
        patch("secrets.SystemRandom.uniform", return_value=0),
    ):
        mock_connect.side_effect = [AsyncMock(__aenter__=AsyncMock(return_value=ws))]
        config_entry = await setup_test(hass)
        await ws_closed.wait()
        await cleanup_test(hass, config_entry)

    ws.close.assert_called_once()
