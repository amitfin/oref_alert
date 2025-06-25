"""Pushy notification channel."""

from __future__ import annotations

import hashlib
import json
import ssl
from itertools import chain
from typing import TYPE_CHECKING, Any, Final

import homeassistant.util.dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.instance_id import async_get
from paho.mqtt.client import Client as MQTTClient
from paho.mqtt.client import MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion

from custom_components.oref_alert.metadata.area_info import AREA_INFO

from .const import CONF_AREAS, CONF_SENSORS, LOGGER

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

API_ENDPOINT: Final = "https://pushy.ioref.app"
MQTT_HOST: Final = "mqtt-{timestamp}.ioref.io"
MQTT_PORT: Final = 443
MQTT_KEEPALIVE: Final = 300
REQUEST_RETRIES = 3
PUSHY_CREDENTIALS_KEY: Final = "pushy_credentials"
TOKEN_KEY: Final = "token"  # noqa: S105
AUTH_KEY: Final = "auth"
ANDROID_ID_KEY: Final = "androidId"
REGISTRATION_PARAMETERS: Final = {
    ANDROID_ID_KEY: None,  # To be filled
    "app": None,
    "appId": "66c20ac875260a035a3af7b2",
    "platform": "android",
    "sdk": 10117,
}
ANDROID_ID_SUFFIX: Final = "-Google-Android-SDK-built-for-x86_64"
TOPICS_KEY: Final = "topics"
TEST_SEGMENTS: Final = [
    "5003000",
    "5003001",
    "5003002",
    "5003003",
    "5003004",
    "5003006",
]

_device_id: str = ""


async def get_device_id(hass: HomeAssistant) -> str:
    """Return a stable ID of 16 characters."""
    global _device_id  # noqa: PLW0603
    if _device_id:
        return _device_id
    ha_id = await async_get(hass)
    _device_id = hashlib.blake2b(ha_id.encode("utf-8"), digest_size=8).hexdigest()
    return _device_id


class PushyNotifications:
    """Register for notifications coming from Pushy."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize areas checker."""
        self._hass = hass
        self._config_entry = config_entry
        self._http_client = async_get_clientsession(hass)
        self._credentials: dict = {}
        self._topics: list = []
        self._mqtt: MQTTClient | None = None

    async def _api_call(self, uri: str, content: Any, reply: bool = False) -> Any:  # noqa: FBT001, FBT002
        """Make HTTP request to the API server."""
        exc_info = Exception()
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.post(
                    f"{API_ENDPOINT}/{uri}", json=content
                ) as response:
                    return (await response.json()) if reply else None
            except Exception as ex:  # noqa: BLE001
                exc_info = ex
        raise exc_info

    async def _register(self) -> None:
        """Perform a new registration and save it in the config."""
        device_id = await get_device_id(self._hass)
        try:
            credentials = await self._api_call(
                "register",
                {
                    **REGISTRATION_PARAMETERS,
                    ANDROID_ID_KEY: f"{device_id}{ANDROID_ID_SUFFIX}",
                },
                reply=True,
            )
        except:  # noqa: E722
            LOGGER.exception(f"'{API_ENDPOINT}/register' failed")
            return
        # Save the credentials data which causes the integration to reload.
        LOGGER.debug("Pushy registration is done.")
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            data={
                **(self._config_entry.data or {}),
                PUSHY_CREDENTIALS_KEY: credentials,
            },
        )
        return

    async def _validate(self, credentials: dict) -> bool:
        """Validate that the configuration is working properly."""
        device_id = await get_device_id(self._hass)
        try:
            await self._api_call(
                "devices/auth",
                {
                    **REGISTRATION_PARAMETERS,
                    ANDROID_ID_KEY: f"{device_id}{ANDROID_ID_SUFFIX}",
                    **credentials,
                },
            )
        except:  # noqa: E722
            # Delete the credentials data which causes the integration to reload.
            # Note: there is no loop here. The registration might fail and that's it.
            self._hass.config_entries.async_update_entry(
                self._config_entry,
                data={
                    key: value
                    for key, value in (self._config_entry.data or {}).items()
                    if key != PUSHY_CREDENTIALS_KEY
                },
            )
            return False
        LOGGER.debug("Pushy credentials were validated.")
        return True

    async def _subscribe(self) -> None:
        """Subscribe to the relevant topics."""
        self._topics = [
            str(AREA_INFO[area]["segment"])
            for area in (
                self._config_entry.options[CONF_AREAS]
                + list(
                    chain.from_iterable(
                        self._config_entry.options.get(CONF_SENSORS, {}).values()
                    )
                )
            )
            if area in AREA_INFO
        ] + TEST_SEGMENTS
        if self._topics:
            try:
                await self._api_call(
                    "subscribe", {**self._credentials, TOPICS_KEY: self._topics}
                )
            except:  # noqa: E722
                LOGGER.exception(f"'{API_ENDPOINT}/subscribe' failed")
                self._topics = []
            LOGGER.debug("Pushy subscribe is done.")

    async def _unsubscribe(self) -> None:
        """Unsubscribe the relevant topics."""
        try:
            await self._api_call(
                "unsubscribe", {**self._credentials, TOPICS_KEY: self._topics}
            )
        except:  # noqa: E722
            LOGGER.exception(f"'{API_ENDPOINT}/unsubscribe' failed")

    def _listen(self) -> None:
        """Listen for MQTT messages."""
        self._mqtt = MQTTClient(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self._credentials.get(TOKEN_KEY),
            clean_session=False,
        )
        self._mqtt.user_data_set(self)
        self._mqtt.enable_logger()
        self._mqtt.username_pw_set(
            self._credentials.get(TOKEN_KEY), self._credentials.get(AUTH_KEY)
        )
        self._mqtt.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        self._mqtt.on_message = lambda _client, _userdata, message: self.on_message(
            message
        )
        self._mqtt.connect_async(
            MQTT_HOST.replace("{timestamp}", str(int(dt_util.now().timestamp()))),
            MQTT_PORT,
            MQTT_KEEPALIVE,
        )
        self._mqtt.loop_start()

    def on_message(self, message: MQTTMessage) -> None:
        """MQTT message processing."""
        try:
            content = json.loads(message.payload.decode("utf-8"))
            LOGGER.debug("MQTT message: %s", content)
        except:  # noqa: E722
            LOGGER.exception("Failed to process MQTT message.")

    async def start(self) -> None:
        """Register for notifications."""
        if (
            credentials := (self._config_entry.data or {}).get(PUSHY_CREDENTIALS_KEY)
        ) is None:
            await self._register()
            return
        if not (await self._validate(credentials)):
            return
        self._credentials = credentials
        await self._subscribe()
        await self._hass.async_add_executor_job(self._listen)

    async def stop(self) -> None:
        """Unregister."""
        if not self._topics:
            return
        await self._unsubscribe()
        if self._mqtt:
            await self._hass.async_add_executor_job(self._mqtt.disconnect)
            await self._hass.async_add_executor_job(self._mqtt.loop_stop)
