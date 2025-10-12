"""Tests for push file."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.client_exceptions import (
    ClientError,
)
from homeassistant.const import STATE_OFF, STATE_ON, Platform
from paho.mqtt.client import MQTTMessage
from paho.mqtt.reasoncodes import ReasonCode
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
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
    LOGGER,
    OREF_ALERT_UNIQUE_ID,
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

from .utils import PUSHY_DEFAULT_CREDENTIALS as DEFAULT_CREDENTIALS
from .utils import load_json_fixture, mock_pushy_urls

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
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


@pytest.fixture(autouse=True)
def mqtt_mock() -> Generator[MqttMockPahoClient]:
    """Mock MQTT client."""
    with patch("custom_components.oref_alert.pushy.MQTTClient") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def _auto_aioclient_mock(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock aiohttp for relevant URLs."""
    mock_pushy_urls(aioclient_mock)


async def setup_test(
    hass: HomeAssistant,
    data: dict | None = None,
    options: dict | None = None,
) -> ConfigEntry:
    """Set up steps for a test case."""
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
    config = await setup_test(hass)
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


async def test_registration_persistency(hass: HomeAssistant) -> None:
    """Test registration persistency."""
    config = await setup_test(hass)
    assert config.data["pushy_credentials"] == DEFAULT_CREDENTIALS
    await cleanup_test(hass, config)


async def test_registration_invalid_content(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test registration invalid content."""
    mock_pushy_urls(aioclient_mock, valid_credentials=False)
    config = await setup_test(hass)
    assert "pushy_credentials" not in config.data
    await cleanup_test(hass, config)
    assert "Pushy registration reply is invalid: {}" in caplog.text


async def test_registration_exception(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test registration throwing exception."""
    mock_pushy_urls(
        aioclient_mock,
        lambda: aioclient_mock.post(f"{API_ENDPOINT}/register", exc=Exception()),
    )
    config = await setup_test(hass)
    await cleanup_test(hass, config)
    assert f"'{API_ENDPOINT}/register' failed" in caplog.text


@pytest.mark.parametrize(
    "debug",
    [
        False,
        True,
    ],
    ids=("no debug", "debug"),
)
async def test_subscribe_unsubscribe(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    debug: bool,  # noqa: FBT001
) -> None:
    """Test subscribe/unsubscribe calls."""
    if debug:
        LOGGER.setLevel(logging.DEBUG)

    config = await setup_test(
        hass, options={CONF_SENSORS: {"Oref Alert Test": ["פתח תקווה"]}}
    )
    await cleanup_test(hass, config)

    segments = [
        str(AREA_INFO["קריית אונו"]["segment"]),
        str(AREA_INFO["פתח תקווה"]["segment"]),
    ]
    if debug:
        segments.extend(TEST_SEGMENTS)

    assert SEGMENT_TO_AREA[int(segments[0])] == "קריית אונו"
    assert SEGMENT_TO_AREA[int(segments[1])] == "פתח תקווה"

    for uri in ("subscribe", "unsubscribe"):
        for method, url, data, _headers in aioclient_mock.mock_calls:
            if method == "POST" and url == URL(f"{API_ENDPOINT}/devices/{uri}"):
                assert data["topics"] == (segments if uri == "subscribe" else ["*"])
                break
        else:
            msg = f"{uri} call was not found"
            raise AssertionError(msg)

    assert config.data["pushy_topics"] == segments


async def test_selective_unsubscribe(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test selective unsubscribe."""
    config = await setup_test(hass, options={CONF_AREAS: ["פתח תקווה"]})
    hass.config_entries.async_update_entry(
        config,
        options={**config.options, CONF_AREAS: []},
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    await cleanup_test(hass, config)

    for method, url, data, _headers in aioclient_mock.mock_calls:
        if (
            method == "POST"
            and url == URL(f"{API_ENDPOINT}/devices/unsubscribe")
            and data.get("topics") == [str(AREA_INFO["פתח תקווה"]["segment"])]
        ):
            break
    else:
        msg = "Unsubscribe call was not found"
        raise AssertionError(msg)


@pytest.mark.parametrize(
    "exception",
    [
        True,
        False,
    ],
    ids=("exception", "invalid"),
)
async def test_validation_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    exception: bool,  # noqa: FBT001
) -> None:
    """Test validation failure."""

    async def validate(method: str, url: URL, data: dict) -> AiohttpClientMockResponse:
        response = AiohttpClientMockResponse(
            method, url, json={"success": exception or data["auth"] == "password"}
        )
        if exception and data["auth"] != "password":
            response.exc = ClientError
        return response

    mock_pushy_urls(
        aioclient_mock,
        lambda: aioclient_mock.post(
            f"{API_ENDPOINT}/devices/auth", side_effect=validate
        ),
    )
    config = await setup_test(
        hass,
        data={"pushy_credentials": {**DEFAULT_CREDENTIALS, "auth": "bad"}},
    )
    await cleanup_test(hass, config)
    assert config.data["pushy_credentials"] == DEFAULT_CREDENTIALS


async def test_subscribe_failure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test subscribe failure."""
    mock_pushy_urls(
        aioclient_mock,
        lambda: aioclient_mock.post(
            f"{API_ENDPOINT}/devices/subscribe", json={"success": False}
        ),
    )
    config = await setup_test(hass, data={"pushy_credentials": DEFAULT_CREDENTIALS})
    assert "pushy_topics" not in config.data
    await cleanup_test(hass, config)
    assert (
        "homeassistant.exceptions.IntegrationError: "
        "https://pushy.ioref.app/devices/subscribe reply payload is invalid: "
        "{'success': False}"
    ) in caplog.text


async def test_unsubscribe_failure(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Test unsubscribe failure."""
    mock_pushy_urls(
        aioclient_mock,
        lambda: aioclient_mock.post(
            f"{API_ENDPOINT}/devices/unsubscribe", exc=ClientError
        ),
    )
    config = await setup_test(hass, data={"pushy_credentials": DEFAULT_CREDENTIALS})
    await cleanup_test(hass, config)


async def test_mqtt_parameters(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,  # noqa: ARG001
    mqtt_mock: MqttMockPahoClient,
) -> None:
    """Test MQTT parameters."""
    config = await setup_test(
        hass,
        data={"pushy_credentials": DEFAULT_CREDENTIALS},
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
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test on_connect callback."""
    config = await setup_test(
        hass,
        data={"pushy_credentials": DEFAULT_CREDENTIALS},
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
    mqtt_mock: MqttMockPahoClient,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test single message."""
    freezer.move_to("2025-06-26T15:34:00+0300")
    async_fire_time_changed(hass)
    config = await setup_test(
        hass,
        data={"pushy_credentials": DEFAULT_CREDENTIALS},
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]
    message: MQTTMessage = MQTTMessage()
    payload = load_json_fixture("pushy_alert.json")
    message.payload = json.dumps(payload).encode("utf-8")
    listener.on_message(message)
    await config.runtime_data.coordinator.async_refresh()
    assert f"MQTT message: {payload}" in caplog.text
    assert listener.alerts.items() == load_json_fixture("pushy_alerts_as_history.json")
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_ON
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    await cleanup_test(hass, config)


async def test_message_no_throw(
    hass: HomeAssistant,
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that message processing never throws an exception."""
    config = await setup_test(
        hass,
        data={"pushy_credentials": DEFAULT_CREDENTIALS},
    )
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]
    message: MQTTMessage = MQTTMessage()
    listener.on_message(message)
    await cleanup_test(hass, config)
    assert "Failed to process MQTT message." in caplog.text


async def test_message_test(
    hass: HomeAssistant,
    mqtt_mock: MqttMockPahoClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a test message is silently ignored."""
    config = await setup_test(
        hass,
        data={"pushy_credentials": DEFAULT_CREDENTIALS},
    )
    listener: PushyNotifications = mqtt_mock.user_data_set.call_args.args[0]
    message: MQTTMessage = MQTTMessage()
    message.payload = json.dumps(
        {"alertTitle": "22345678-1e64-4db5-a367", "test": True}
    ).encode("utf-8")
    listener.on_message(message)
    await cleanup_test(hass, config)
    assert "ERROR    custom_components.oref_alert:pushy.py:" not in caplog.text
