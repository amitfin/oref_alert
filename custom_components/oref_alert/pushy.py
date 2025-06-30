"""Pushy notification channel."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
from itertools import chain
from typing import TYPE_CHECKING, Any, Final

import homeassistant.util.dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.instance_id import async_get
from paho.mqtt.client import Client as MQTTClient
from paho.mqtt.client import MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion

from custom_components.oref_alert.categories import pushy_thread_id_to_history_category
from custom_components.oref_alert.metadata.area_info import AREA_INFO
from custom_components.oref_alert.metadata.segment_to_area import SEGMENT_TO_AREA
from custom_components.oref_alert.ttl_deque import TTLDeque

from .const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DATA_COORDINATOR,
    LOGGER,
    AlertField,
    AlertSource,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from paho.mqtt.reasoncodes import ReasonCode

API_ENDPOINT: Final = "https://pushy.ioref.app"
MQTT_HOST: Final = "mqtt-{timestamp}.ioref.io"
MQTT_PORT: Final = 443
MQTT_KEEPALIVE: Final = 300
MQTT_QOS: Final = 1
REQUEST_RETRIES = 3
PUSHY_CREDENTIALS_KEY: Final = "pushy_credentials"
TOKEN_KEY: Final = "token"  # noqa: S105
AUTH_KEY: Final = "auth"
PUSHY_TOPICS_KEY: Final = "pushy_topics"
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
        """Initialize PushyNotifications."""
        self._hass = hass
        self._config_entry = config_entry
        self._http_client = async_get_clientsession(hass)
        self._credentials: dict = {}
        self._mqtt: MQTTClient | None = None
        self.alerts: TTLDeque = TTLDeque(
            config_entry.options[CONF_ALERT_ACTIVE_DURATION]
        )

    async def _api_call(self, uri: str, content: Any, check: bool = True) -> Any:  # noqa: FBT001, FBT002
        """Make HTTP request to the API server."""
        exc_info = Exception()
        for _ in range(REQUEST_RETRIES):
            try:
                async with self._http_client.post(
                    f"{API_ENDPOINT}/{uri}", json=content
                ) as response:
                    content = await response.json()
                    if check and not content.get("success"):
                        message = (
                            f"{API_ENDPOINT}/{uri} reply payload is invalid: {content}"
                        )
                        raise ValueError(message)  # noqa: TRY301
                    return content
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
                check=False,
            )
        except:  # noqa: E722
            LOGGER.exception(f"'{API_ENDPOINT}/register' failed")
            return
        if TOKEN_KEY not in credentials or AUTH_KEY not in credentials:
            LOGGER.error("Pushy registration reply is invalid: %s", credentials)
            return
        LOGGER.debug("Pushy registration is done: %s", credentials)
        # Save the credentials data which causes the integration to reload.
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
        LOGGER.debug("Pushy credentials are validate.")
        return True

    async def _subscribe(self) -> bool:
        """Subscribe to the relevant topics."""
        topics = [
            str(AREA_INFO[area]["segment"])
            for area in (
                self._config_entry.options[CONF_AREAS]
                + list(
                    chain.from_iterable(
                        self._config_entry.options.get(CONF_SENSORS, {}).values()
                    )
                )
            )
            if area in AREA_INFO and AREA_INFO[area]["segment"]
        ]
        if LOGGER.isEnabledFor(logging.DEBUG):
            topics.extend(TEST_SEGMENTS)

        if (
            previous_topics := (self._config_entry.data or {}).get(PUSHY_TOPICS_KEY)
        ) is None:
            await self._unsubscribe(["*"])
            previous_topics = []

        if removed := [topic for topic in previous_topics if topic not in topics]:
            await self._unsubscribe(removed)

        if added := [topic for topic in topics if topic not in previous_topics]:
            try:
                await self._api_call(
                    "devices/subscribe", {**self._credentials, TOPICS_KEY: added}
                )
            except:  # noqa: E722
                LOGGER.exception(f"'{API_ENDPOINT}/subscribe' failed")
                return True
            LOGGER.debug("Pushy subscribe is done: %s", added)

        if added or removed:
            self._hass.config_entries.async_update_entry(
                self._config_entry,
                data={
                    **(self._config_entry.data or {}),
                    PUSHY_TOPICS_KEY: topics,
                },
            )
            return True

        return False

    async def _unsubscribe(self, topics: list[str]) -> None:
        """Unsubscribe the relevant topics."""
        try:
            await self._api_call(
                "devices/unsubscribe", {**self._credentials, TOPICS_KEY: topics}
            )
        except:  # noqa: E722
            LOGGER.exception(f"'{API_ENDPOINT}/unsubscribe' failed")
            return
        LOGGER.debug("Pushy unsubscribe is done: %s", topics)

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
        self._mqtt.on_connect = lambda _c, _u, _f, reason_code, _p: self.on_connect(
            reason_code
        )
        self._mqtt.connect_async(
            MQTT_HOST.replace("{timestamp}", str(int(dt_util.now().timestamp()))),
            MQTT_PORT,
            MQTT_KEEPALIVE,
        )
        self._mqtt.loop_start()

    def on_connect(self, reason_code: ReasonCode) -> None:
        """Subscribe on successful connect."""
        if not reason_code.is_failure and self._mqtt:
            self._mqtt.subscribe(self._credentials.get(TOKEN_KEY, ""), MQTT_QOS)
            LOGGER.debug("MQTT subscribe is done.")
        else:
            LOGGER.warning(f"MQTT connection failed: {reason_code.getName()}.")

    def on_message(self, message: MQTTMessage) -> None:
        """MQTT message processing."""
        try:
            content = json.loads(message.payload.decode("utf-8"))
            LOGGER.debug("MQTT message: %s", content)
            new_alert = False
            alert_date = dt_util.parse_datetime(
                content["time"], raise_on_error=True
            ).strftime("%Y-%m-%d %H:%M:%S")
            if (
                category := pushy_thread_id_to_history_category(
                    int(content["threatId"])
                )
            ) is not None:
                for area in [
                    SEGMENT_TO_AREA[int(segment)]
                    for segment in content["citiesIds"].split(",")
                    if int(segment) in SEGMENT_TO_AREA
                ]:
                    self.alerts.add(
                        {
                            AlertField.DATE: alert_date,
                            AlertField.TITLE: content[AlertField.TITLE],
                            AlertField.AREA: area,
                            AlertField.CATEGORY: category,
                            AlertField.CHANNEL: AlertSource.MOBILE,
                        }
                    )
                    new_alert = True
            if new_alert and (
                coordinator := self._config_entry.runtime_data.get(DATA_COORDINATOR)
            ):
                asyncio.run_coroutine_threadsafe(
                    coordinator.async_refresh(), self._hass.loop
                )
        except:  # noqa: E722
            LOGGER.exception("Failed to process MQTT message.")

    async def start(self) -> None:
        """Register for notifications."""
        if (
            credentials := (self._config_entry.data or {}).get(PUSHY_CREDENTIALS_KEY)
        ) is None:
            await self._register()
            return  # The config entry data was changed so the integration will reload
        if not (await self._validate(credentials)):
            return
        self._credentials = credentials
        if await self._subscribe():
            return  # The config entry data was changed so the integration will reload
        await self._hass.async_add_executor_job(self._listen)

    async def stop(self) -> None:
        """Unregister."""
        if self._mqtt:
            await self._hass.async_add_executor_job(self._mqtt.disconnect)
            await self._hass.async_add_executor_job(self._mqtt.loop_stop)
