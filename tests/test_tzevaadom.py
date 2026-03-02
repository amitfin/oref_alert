"""Tests for tzevaadom file."""

from __future__ import annotations

import asyncio
import json
from asyncio import Event
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import WSMessage, WSMsgType
from homeassistant.const import STATE_OK, Platform
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ATTR_RECORD,
    CONF_AREAS,
    DOMAIN,
    IST,
    OREF_ALERT_UNIQUE_ID,
    RecordAndMetadata,
)
from custom_components.oref_alert.records_schema import RecordType
from custom_components.oref_alert.tzevaadom import TzevaAdomNotifications
from tests.utils import load_json_fixture

if TYPE_CHECKING:
    from collections.abc import Generator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS = {CONF_AREAS: ["גבעת שמואל"]}
ENTITY_ID = f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}"


@contextmanager
def mock_ws(messages: list[WSMessage]) -> Generator[AsyncMock]:
    """Mock WebSocket connection for testing."""
    messages_processed = Event()
    close_message = WSMessage(type=WSMsgType.CLOSED, data=None, extra=None)
    blocked_receive: asyncio.Future[WSMessage] = (
        asyncio.get_event_loop().create_future()
    )
    ws = AsyncMock()
    queue: deque[WSMessage] = deque(messages)

    async def receive() -> WSMessage:
        if queue:
            return queue.popleft()
        messages_processed.set()
        return await blocked_receive

    ws.receive = AsyncMock(side_effect=receive)
    ws.close = AsyncMock(side_effect=lambda: blocked_receive.set_result(close_message))
    ws.messages_processed = messages_processed.wait

    with patch("aiohttp.ClientSession.ws_connect") as connect:
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
        await cleanup_test(hass, config_entry)
    ws.close.assert_called_once()


@pytest.mark.allowed_logs(["Unknown area 'dummy'"])
@pytest.mark.parametrize(
    ("file", "overrides", "expected_state", "expected_record"),
    [
        (
            "single_alert_tzevaadom.json",
            {},
            RecordType.ALERT,
            {
                "alertDate": "2025-06-30 15:00:00",
                "title": "חדירת כלי טיס עוין",  # noqa: RUF001
                "data": "גבעת שמואל",
                "category": 2,
                "channel": "tzevaadom",
            },
        ),
        ("single_alert_tzevaadom.json", {"isDrill": True}, STATE_OK, None),
        ("single_alert_tzevaadom.json", {"cities": ["dummy"]}, STATE_OK, None),
        (
            "single_update_tzevaadom.json",
            {},
            RecordType.PRE_ALERT,
            {
                "alertDate": "2026-03-01 16:45:13",
                "title": "בדקות הקרובות צפויות להתקבל התרעות באזורך",
                "data": "גבעת שמואל",
                "category": 14,
                "channel": "tzevaadom",
            },
        ),
        (
            "single_update_end_tzevaadom.json",
            {},
            STATE_OK,
            {
                "alertDate": "2026-03-01 15:45:12",
                "title": "הארוע הסתיים",
                "data": "גבעת שמואל",
                "category": 13,
                "channel": "tzevaadom",
            },
        ),
        ("single_update_tzevaadom.json", {"citiesIds": None}, STATE_OK, None),
    ],
    ids=("plain", "drill", "invalid area", "pre alert", "end", "no cities"),
)
async def test_message(  # noqa: PLR0913
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    file: str,
    overrides: dict,
    expected_state: str,
    expected_record: dict,
) -> None:
    """Test tzevaadom message."""
    freezer.move_to("2025-06-30T15:00:00+0300")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    message = load_json_fixture(file)
    message["data"].update(overrides)
    data = json.dumps(message).encode("utf-8")
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)]) as ws:
        config_entry = await setup_test(hass)
        await ws.messages_processed()
        state = hass.states.get(ENTITY_ID)
        assert state is not None
        assert state.state == expected_state
        assert state.attributes[ATTR_RECORD] == expected_record
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
        await ws.messages_processed()
        await cleanup_test(hass, config_entry)
    assert (f"Unknown area '{area}' in Tzeva Adom alert, skipping." in caplog.text) == (
        not valid
    )


@pytest.mark.allowed_logs(
    ["Error processing WS message", "Tzevaadom unknown message type: test"]
)
@pytest.mark.parametrize(
    ("message_type", "log_message", "data"),
    [
        (WSMsgType.BINARY, "WS system message 'BINARY' => ignoring", None),
        (WSMsgType.PING, "WS system message 'PING' => ignoring", None),
        (WSMsgType.PONG, "WS system message 'PONG' => ignoring", None),
        (WSMsgType.TEXT, "Error processing WS message", None),
        (WSMsgType.TEXT, "Tzevaadom unknown message type: test", '{"type": "test"}'),
    ],
    ids=(
        "binary",
        "ping",
        "pong",
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
        await ws.messages_processed()
        await cleanup_test(hass, config_entry)
    assert log_message in caplog.text


async def test_duplicate(hass: HomeAssistant) -> None:
    """Test 2 messages with the same ID."""
    alert = load_json_fixture("single_alert_tzevaadom.json")
    data = json.dumps(alert).encode("utf-8")
    config = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config.runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_refresh=AsyncMock()),
        classifier=SimpleNamespace(
            add_metadata=lambda record: RecordAndMetadata(
                raw=record,
                raw_dict=asdict(record),
                record_type=RecordType.ALERT,
                time=datetime.strptime(record.alertDate, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=IST
                ),
                expire=None,
            )
        ),
    )
    tzevaadom = TzevaAdomNotifications(hass, config)
    with mock_ws([WSMessage(type=WSMsgType.TEXT, data=data, extra=None)] * 3) as ws:
        await tzevaadom.start()
        await ws.messages_processed()
        assert len(tzevaadom.alerts.items()) == 1
        await tzevaadom.stop()
