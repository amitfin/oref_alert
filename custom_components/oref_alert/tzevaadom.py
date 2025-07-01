"""Implement websocket channel for Tzeva Adom alerts."""

from __future__ import annotations

import asyncio
import contextlib
import enum
import secrets
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Final

import aiohttp
from aiohttp import ClientWebSocketResponse, ClientWSTimeout, WSMsgType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.oref_alert.categories import (
    tzevaadom_threat_id_to_history_category,
)
from custom_components.oref_alert.metadata.areas import AREAS
from custom_components.oref_alert.metadata.tzevaadom_id_to_area import (
    TZEVAADOM_ID_TO_AREA,
)
from custom_components.oref_alert.ttl_deque import TTLDeque

from .const import (
    CONF_ALERT_ACTIVE_DURATION,
    DATA_COORDINATOR,
    IST,
    LOGGER,
    AlertField,
    AlertSource,
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

THREAT_TITLES = {
    0: "ירי רקטות וטילים",
    1: "אירוע חומרים מסוכנים",
    2: "חדירת מחבלים",
    3: "רעידת אדמה",
    4: "חשש לצונאמי",
    5: "חדירת כלי טיס עוין",  # noqa: RUF001
    6: "חשש לאירוע רדיולוגי",
    7: "חשש לאירוע כימי",
    8: "התרעות פיקוד העורף",
}


class MessageType(str, enum.Enum):
    """Message types for Tzeva Adom WebSocket messages."""

    ALERT = "ALERT"
    SYSTEM_MESSAGE = "SYSTEM_MESSAGE"


class TzevaAdomNotifications:
    """Register for notifications coming from Tzeva Adom."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize TzevaAdomNotifications."""
        self._hass = hass
        self._config_entry = config_entry
        self.alerts: TTLDeque = TTLDeque(
            config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )
        self._ids: TTLDeque = TTLDeque(config_entry.options[CONF_ALERT_ACTIVE_DURATION])
        self._http_client = async_get_clientsession(hass)
        self._ws: ClientWebSocketResponse | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the WebSocket listener."""
        self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Stop the WebSocket listener."""
        self._stop.set()
        await self._close()
        if self._task:
            await self._task

    async def _close(self) -> None:
        """Close WS."""
        if self._ws:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

    async def _listen(self) -> None:
        """Listen for WebSocket messages."""
        while not self._stop.is_set():
            try:
                async with self._http_client.ws_connect(
                    WS_URL,
                    origin=ORIGIN_HEADER,
                    timeout=ClientWSTimeout(
                        ws_receive=WS_IDLE_TIMEOUT,  # type: ignore  # noqa: PGH003
                        ws_close=WS_CLOSE_TIMEOUT,  # type: ignore  # noqa: PGH003
                    ),
                ) as self._ws:
                    while True:
                        message = await self._ws.receive()
                        if message.type == aiohttp.WSMsgType.TEXT:
                            await self._on_message(message.json())
                        elif message.type in WS_SYSTEM_MESSAGES:
                            LOGGER.debug(
                                "WS system message (%s), ignoring.",
                                WSMsgType(message.type).name,
                            )
                        else:
                            if message.type != aiohttp.WSMsgType.CLOSING:
                                LOGGER.debug(
                                    "Unexpected WS message (%s): %s",
                                    WSMsgType(message.type).name
                                    if isinstance(message.type, int)
                                    else "None",
                                    message.data,
                                )
                                await self._delay()
                            break

            except:  # noqa: E722
                LOGGER.exception("Error in WS listener")
                await self._delay()
            await self._close()

    async def _delay(self) -> None:
        """Delay for a short period before reconnecting."""
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                self._stop.wait(), timeout=secrets.SystemRandom().uniform(5, 15)
            )

    def _parse_message(self, message: dict) -> dict | None:
        """Parse the message and return parsed/converted fields."""
        if message["type"] == MessageType.ALERT:
            if (
                message["data"]["isDrill"]
                or (
                    category := tzevaadom_threat_id_to_history_category(
                        int(message["data"]["threat"])
                    )
                )
                is None
            ):
                return None
            fields = {
                AlertField.TITLE: THREAT_TITLES[int(message["data"]["threat"])],
                AlertField.CATEGORY: category,
                "areas": message["data"]["cities"],
                "id": f"{MessageType.ALERT}_{message['data']['notificationId']}",
            }

        elif message["type"] == MessageType.SYSTEM_MESSAGE:
            if (
                cities_ids := message["data"].get("citiesIds")
                # SYSTEM_MESSAGE is working for now only for testing purposes.
            ) is None or "pytest" not in sys.modules:
                return None
            fields = {
                AlertField.TITLE: message["data"]["titleHe"],
                AlertField.CATEGORY: 14,  # 14 is pre-alert and 13 is post-alert.
                "areas": [TZEVAADOM_ID_TO_AREA[city_id] for city_id in cities_ids],
                "id": f"{MessageType.SYSTEM_MESSAGE}_{message['data']['id']}",
            }

        else:
            LOGGER.warning("Tzevaadom unknown message type: %s", message["type"])
            return None

        fields[AlertField.DATE] = datetime.fromtimestamp(
            message["data"]["time"], tz=IST
        ).strftime("%Y-%m-%d %H:%M:%S")

        return fields

    async def _on_message(self, message: dict) -> None:
        """Handle incoming WebSocket messages."""
        try:
            LOGGER.debug("WS message: %s", message)

            if (fields := self._parse_message(message)) is None:
                return

            if fields["id"] in self._ids.items():
                return
            self._ids.add(fields["id"])

            new_alert = False
            for area in fields["areas"]:
                if area not in AREAS:
                    LOGGER.warning(
                        "Unknown area '%s' in Tzeva Adom alert, skipping.", area
                    )
                    continue
                self.alerts.add(
                    {
                        AlertField.DATE: fields[AlertField.DATE],
                        AlertField.TITLE: fields[AlertField.TITLE],
                        AlertField.AREA: area,
                        AlertField.CATEGORY: fields[AlertField.CATEGORY],
                        AlertField.CHANNEL: AlertSource.TZEVAADOM,
                    }
                )
                new_alert = True

            if new_alert and (
                coordinator := self._config_entry.runtime_data.get(DATA_COORDINATOR)
            ):
                await coordinator.async_refresh()

        except:  # noqa: E722
            LOGGER.exception("Error processing WS message")
