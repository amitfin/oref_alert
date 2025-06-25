"""Tests for push file."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.client_exceptions import (
    ClientError,
)
from paho.mqtt.client import MQTTMessage
from paho.mqtt.reasoncodes import ReasonCode
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_SENSORS,
    DOMAIN,
)
from custom_components.oref_alert.metadata.area_info import AREA_INFO
from custom_components.oref_alert.metadata.segment_to_area import SEGMENT_TO_AREA
from custom_components.oref_alert.pushy import (
    ANDROID_ID_SUFFIX,
    API_ENDPOINT,
    TEST_SEGMENTS,
    PushyNotifications,
    get_device_id,
)

if TYPE_CHECKING:
    from collections.abc import Generator

    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from pytest_homeassistant_custom_component.typing import (
        MqttMockPahoClient,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["קריית אונו"], CONF_ALERT_ACTIVE_DURATION: 10}


@pytest.fixture(autouse=True)
def mqtt_mock() -> Generator[MqttMockPahoClient]:
    """Mock MQTT client."""
    with patch("custom_components.oref_alert.pushy.MQTTClient") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


def mock_api_calls(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock relevant URLs of APIs."""
    if aioclient_mock:
        for uri in ("register", "devices/auth", "subscribe", "unsubscribe"):
            aioclient_mock.post(f"{API_ENDPOINT}/{uri}")


async def setup_test(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker | None = None,
    data: dict | None = None,
    options: dict | None = None,
) -> ConfigEntry:
    """Set up steps for a test case."""
    if aioclient_mock:
        mock_api_calls(aioclient_mock)
    config_entry = MockConfigEntry(
        domain=DOMAIN, data=(data or {}), options={**DEFAULT_OPTIONS, **(options or {})}
    )
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry


async def cleanup_test(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Clean up steps for a test case."""
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_device_id(hass: HomeAssistant) -> None:
    """Test device ID."""
    id1 = await get_device_id(hass)
    assert len(id1) == 16
    id2 = await get_device_id(hass)
    assert id1 == id2


async def test_registration_params(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test registration parameters."""
    config = await setup_test(hass, aioclient_mock)
    await cleanup_test(hass, config)
    for method, url, data, _headers in aioclient_mock.mock_calls:
        if method == "POST" and url == URL(f"{API_ENDPOINT}/register"):
            assert data["androidId"].endswith(ANDROID_ID_SUFFIX)
            assert len(data["androidId"]) == len(ANDROID_ID_SUFFIX) + 16
            assert data["platform"] == "android"
            break
    else:
        msg = "Registration call was not found"
        raise AssertionError(msg)


async def test_registration_persistency(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test registration persistency."""
    aioclient_mock.post(f"{API_ENDPOINT}/register", text='{"token": "a", "auth": "b"}')
    config = await setup_test(hass, aioclient_mock)
    assert config.data["pushy_credentials"] == {"token": "a", "auth": "b"}
    await cleanup_test(hass, config)


async def test_subscribe_unsubscribe(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test subscribe/unsubscribe calls."""
    aioclient_mock.post(f"{API_ENDPOINT}/register", text="{}")
    config = await setup_test(
        hass, aioclient_mock, options={CONF_SENSORS: {"Oref Alert Test": ["פתח תקווה"]}}
    )
    await cleanup_test(hass, config)

    segments = [
        str(AREA_INFO["קריית אונו"]["segment"]),
        str(AREA_INFO["פתח תקווה"]["segment"]),
        *TEST_SEGMENTS,
    ]
    assert SEGMENT_TO_AREA[int(segments[0])] == "קריית אונו"
    assert SEGMENT_TO_AREA[int(segments[1])] == "פתח תקווה"

    for uri in ("subscribe", "unsubscribe"):
        for method, url, data, _headers in aioclient_mock.mock_calls:
            if method == "POST" and url == URL(f"{API_ENDPOINT}/{uri}"):
                assert data["topics"] == segments
                break
        else:
            msg = f"{uri} call was not found"
            raise AssertionError(msg)


async def test_validation_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test validation failure."""

    async def validate(method: str, url: URL, data: dict) -> AiohttpClientMockResponse:
        response = AiohttpClientMockResponse(method, url)
        if data["auth"] != "good":
            response.exc = ClientError
        return response

    aioclient_mock.post(f"{API_ENDPOINT}/devices/auth", side_effect=validate)
    aioclient_mock.post(f"{API_ENDPOINT}/register", text='{"auth": "good"}')
    config = await setup_test(
        hass, aioclient_mock, data={"pushy_credentials": {"auth": "bad"}}
    )
    await cleanup_test(hass, config)
    assert config.data["pushy_credentials"] == {"auth": "good"}


async def test_subscribe_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test subscribe failure."""
    aioclient_mock.post(f"{API_ENDPOINT}/subscribe", exc=ClientError)
    config = await setup_test(hass, aioclient_mock, data={"pushy_credentials": {}})
    await cleanup_test(hass, config)
    for method, url, _data, _headers in aioclient_mock.mock_calls:
        assert method != "POST" or url != URL(f"{API_ENDPOINT}/unsubscribe")


async def test_unsubscribe_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test unsubscribe failure."""
    aioclient_mock.post(f"{API_ENDPOINT}/unsubscribe", exc=ClientError)
    config = await setup_test(hass, aioclient_mock, data={"pushy_credentials": {}})
    await cleanup_test(hass, config)


async def test_mqtt_parameters(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,  # noqa: ARG001
    mqtt_mock: MqttMockPahoClient,
) -> None:
    """Test MQTT parameters."""
    config = await setup_test(
        hass,
        aioclient_mock,
        data={"pushy_credentials": {"token": "user", "auth": "password"}},
    )
    mqtt_mock.username_pw_set.assert_called_with("user", "password")
    mqtt_mock.connect_async.assert_called_with(
        f"mqtt-{int(time.time())}.ioref.io", 443, 300
    )
    mqtt_mock.disconnect.assert_not_called()
    await cleanup_test(hass, config)
    mqtt_mock.disconnect.assert_called()


async def test_on_connect(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test on_connect callback."""
    config = await setup_test(
        hass,
        aioclient_mock,
        data={"pushy_credentials": {"token": "user", "auth": "password"}},
    )
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]

    mqtt_mock.subscribe.assert_not_called()
    listener.on_connect(ReasonCode(2, identifier=0))
    mqtt_mock.subscribe.assert_called_with("user", 1)
    listener.on_connect(ReasonCode(2, identifier=136))
    mqtt_mock.subscribe.assert_called_once()
    assert "MQTT connection failed: Server unavailable." in caplog.text

    await cleanup_test(hass, config)


async def test_simple_message(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test MQTT parameters."""
    config = await setup_test(
        hass,
        aioclient_mock,
        data={"pushy_credentials": {"token": "user", "auth": "password"}},
    )
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]
    message: MQTTMessage = MQTTMessage()
    message.payload = b'{"test": "test"}'
    listener.on_message(message)
    await cleanup_test(hass, config)
    assert "MQTT message: {'test': 'test'}" in caplog.text


async def test_message_no_throw(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that message processing never throws an exception."""
    config = await setup_test(
        hass,
        aioclient_mock,
        data={"pushy_credentials": {"token": "user", "auth": "password"}},
    )
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]
    message: MQTTMessage = MQTTMessage()
    listener.on_message(message)
    await cleanup_test(hass, config)
    assert "Failed to process MQTT message." in caplog.text
