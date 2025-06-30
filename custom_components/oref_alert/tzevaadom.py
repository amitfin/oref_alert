"""Implement websocket channel for Tzeva Adom alerts."""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from typing import TYPE_CHECKING, Final

import aiohttp
from aiohttp import ClientWebSocketResponse, ClientWSTimeout, WSMsgType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.oref_alert.ttl_deque import TTLDeque

from .const import (
    CONF_ALERT_ACTIVE_DURATION,
    LOGGER,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

WS_URL: Final = "wss://ws.tzevaadom.co.il/socket?platform=WEB"
ORIGIN_HEADER: Final = "https://www.tzevaadom.co.il"
WS_IDLE_TIMEOUT: Final = 10 * 60
WS_CLOSE_TIMEOUT: Final = 3.0
WS_SYSTEM_MESSAGES: Final = [
    aiohttp.WSMsgType.BINARY,
    aiohttp.WSMsgType.PING,
    aiohttp.WSMsgType.PONG,
]


class TzevaAdomNotifications:
    """Register for notifications coming from Tzeva Adom."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize TzevaAdomNotifications."""
        self._hass = hass
        self._config_entry = config_entry
        self.alerts: TTLDeque = TTLDeque(
            config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )
        self._http_client = async_get_clientsession(hass)
        self._stop = asyncio.Event()
        self._ws: ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the WebSocket listener."""
        self._stop.clear()
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._stop.set()
        if self._ws:
            await self._ws.close()
        if self._task:
            await self._task

    async def _listen(self) -> None:
        """Listen for WebSocket messages."""
        while not self._stop.is_set():
            try:
                if self._ws:
                    await self._ws.close()
                    self._ws = None
                async with self._http_client.ws_connect(
                    WS_URL,
                    origin=ORIGIN_HEADER,
                    timeout=ClientWSTimeout(
                        ws_receive=WS_IDLE_TIMEOUT,  # type: ignore  # noqa: PGH003
                        ws_close=WS_CLOSE_TIMEOUT,  # type: ignore  # noqa: PGH003
                    ),
                ) as ws:
                    self._ws = ws
                    while True:
                        message = await ws.receive()
                        if message.type == aiohttp.WSMsgType.TEXT:
                            await self.on_message(message.json())
                        elif message.type in WS_SYSTEM_MESSAGES:
                            LOGGER.debug(
                                "WS system message (%s), ignoring.",
                                WSMsgType(message.type).name,
                            )
                        else:
                            if message.type != aiohttp.WSMsgType.CLOSING:
                                LOGGER.debug(
                                    "Unexpected WS message: type: %d payload: %s",
                                    message.type,
                                    message.data,
                                )
                                await self._delay()
                            break

            except:  # noqa: E722
                LOGGER.exception("Error in WS listener")
                await self._delay()

    async def _delay(self) -> None:
        """Delay for a short period before reconnecting."""
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                self._stop.wait(), timeout=secrets.SystemRandom().uniform(5, 15)
            )

    async def on_message(self, message: dict) -> None:
        """Handle incoming WebSocket messages."""
        LOGGER.debug("WS message: %s", message)
