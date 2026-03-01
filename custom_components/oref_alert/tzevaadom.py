"""Implement websocket channel for Tzeva Adom alerts."""

from __future__ import annotations

import asyncio
import contextlib
import enum
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final

import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .categories import (
    END_ALERT_CATEGORY,
    PRE_ALERT_CATEGORY,
    tzevaadom_threat_id_to_history_category,
)
from .const import (
    CATEGORY_FIELD,
    DATE_FIELD,
    IST,
    LOGGER,
    TITLE_FIELD,
    Record,
    RecordAndMetadata,
    RecordSource,
)
from .metadata import TZEVAADOM_SPELLING_FIX
from .metadata.areas import AREAS
from .metadata.tzevaadom_id_to_area import (
    TZEVAADOM_ID_TO_AREA,
)
from .ttl_deque import TTLDeque

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OrefAlertConfigEntry

WS_URL: Final = "wss://ws.tzevaadom.co.il/socket?platform=WEB"
ORIGIN_HEADER: Final = "https://www.tzevaadom.co.il"
WS_HEARTBEAT: Final = 45

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

PRE_ALERT_TITLE = "בדקות הקרובות צפויות להתקבל התרעות באזורך"
END_TITLE = "הארוע הסתיים"


class MessageType(enum.StrEnum):
    """Message types for Tzeva Adom WebSocket messages."""

    ALERT = "ALERT"
    SYSTEM_MESSAGE = "SYSTEM_MESSAGE"


class SystemMessageType(enum.IntEnum):
    """Message types for Tzeva Adom WebSocket messages."""

    PRE_ALERT = 0
    END = 1


class TzevaAdomNotifications:
    """Register for notifications coming from Tzeva Adom."""

    def __init__(self, hass: HomeAssistant, config_entry: OrefAlertConfigEntry) -> None:
        """Initialize TzevaAdomNotifications."""
        self._hass = hass
        self._config_entry = config_entry
        self.alerts: TTLDeque[RecordAndMetadata] = TTLDeque()
        self._ids: TTLDeque[str] = TTLDeque()
        self._http_client = async_get_clientsession(hass)
        self._ws: ClientWebSocketResponse | None = None
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

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
        while True:
            try:
                async with self._http_client.ws_connect(
                    WS_URL,
                    origin=ORIGIN_HEADER,
                    heartbeat=WS_HEARTBEAT,
                ) as self._ws:
                    while True:
                        message = await self._ws.receive()
                        match message.type:
                            case aiohttp.WSMsgType.TEXT:
                                await self._on_message(message.json())
                            case (
                                aiohttp.WSMsgType.CLOSING
                                | aiohttp.WSMsgType.CLOSE
                                | aiohttp.WSMsgType.CLOSED
                                | aiohttp.WSMsgType.ERROR
                            ):
                                LOGGER.debug(
                                    "WS system message '%s' => closing",
                                    WSMsgType(message.type).name,
                                )
                                break
                            case _:
                                LOGGER.debug(
                                    "WS system message '%s' => ignoring",
                                    WSMsgType(message.type).name,
                                )

            except:  # noqa: E722
                LOGGER.exception("Error in WS listener")
            if self._stop.is_set():
                break
            await self._close()
            await self._delay()

    async def _delay(self) -> None:
        """Delay for a short period before reconnecting."""
        with contextlib.suppress(Exception):
            await asyncio.wait_for(
                self._stop.wait(), timeout=secrets.SystemRandom().uniform(5, 8)
            )

    def _parse_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
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
                TITLE_FIELD: THREAT_TITLES[int(message["data"]["threat"])],
                CATEGORY_FIELD: category,
                "areas": message["data"]["cities"],
                "id": f"{MessageType.ALERT}_{message['data']['notificationId']}",
            }

        elif message["type"] == MessageType.SYSTEM_MESSAGE:
            areas = [
                TZEVAADOM_ID_TO_AREA[city_id]
                for city_id in message["data"].get("citiesIds") or []
                if city_id in TZEVAADOM_ID_TO_AREA
            ]

            # Filter out empty areas and ensure the message is "pre_alert" or "end".
            if (
                not areas
                or (instruction := message["data"].get("instructionType")) is None
                or instruction
                not in (SystemMessageType.PRE_ALERT, SystemMessageType.END)
            ):
                return None

            fields = {
                # We use the official title for pre-alerts.
                TITLE_FIELD: PRE_ALERT_TITLE
                if instruction == SystemMessageType.PRE_ALERT
                else END_TITLE,
                CATEGORY_FIELD: PRE_ALERT_CATEGORY
                if instruction == SystemMessageType.PRE_ALERT
                else END_ALERT_CATEGORY,
                "areas": areas,
                "id": (
                    f"{MessageType.SYSTEM_MESSAGE}_{message['data']['notificationId']}"
                ),
            }

        else:
            LOGGER.warning("Tzevaadom unknown message type: %s", message["type"])
            return None

        fields[DATE_FIELD] = datetime.fromtimestamp(
            int(message["data"]["time"]), tz=IST
        ).strftime("%Y-%m-%d %H:%M:%S")

        return fields

    async def _on_message(self, message: dict[str, Any]) -> None:
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
                name = TZEVAADOM_SPELLING_FIX.get(area, area)
                if name not in AREAS:
                    LOGGER.warning(
                        "Unknown area '%s' in Tzeva Adom alert, skipping.", name
                    )
                    continue
                self.alerts.add(
                    self._config_entry.runtime_data.classifier.add_metadata(
                        Record(
                            alertDate=fields[DATE_FIELD],
                            title=fields[TITLE_FIELD],
                            data=name,
                            category=fields[CATEGORY_FIELD],
                            channel=RecordSource.TZEVAADOM,
                        )
                    )
                )
                new_alert = True

            if new_alert:
                await self._config_entry.runtime_data.coordinator.async_refresh()

        except:  # noqa: E722
            LOGGER.exception("Error processing WS message")
