"""The tests for the binary_sensor file."""
from __future__ import annotations

import datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import CONF_NAME, Platform, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.const import (
    ADD_SENSOR_SERVICE,
    ATTR_COUNTRY_ALERTS,
    ATTR_COUNTRY_ACTIVE_ALERTS,
    ATTR_SELECTED_AREAS_ALERTS,
    ATTR_SELECTED_AREAS_ACTIVE_ALERTS,
    CONF_ALERT_MAX_AGE,
    CONF_AREAS,
    CONF_OFF_ICON,
    CONF_ON_ICON,
    CONF_POLL_INTERVAL,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
    ALL_AREAS_ID_SUFFIX,
)

from .utils import load_json_fixture, mock_urls

DEFAULT_OPTIONS = {CONF_AREAS: ["בארי"], CONF_ALERT_MAX_AGE: 10}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


async def async_setup(
    hass: HomeAssistant, options: dict[str, Any] | None = None
) -> str:
    """Integration setup."""
    options = options or {}
    config_entry = MockConfigEntry(
        domain=DOMAIN, options={**DEFAULT_OPTIONS, **options}
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry.entry_id


async def async_shutdown(hass: HomeAssistant, config_id: str) -> None:
    """Shutdown by removing the integration."""
    assert await hass.config_entries.async_remove(config_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_state(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")

    config_id = await async_setup(hass)
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    freezer.move_to("2023-10-07 06:39:50+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    freezer.move_to("2023-10-07 06:40:01+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await async_shutdown(hass, config_id)


@pytest.mark.parametrize(
    ("areas",),
    ((["תל אביב - כל האזורים"],), (["מחוז דן"],)),
    ids=("City all areas", "District"),
)
async def test_real_time_alert_area_expansion(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, areas: list[str]
) -> None:
    """Test real time alert and city expansion."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(hass, {CONF_AREAS: areas})
    assert hass.states.get(ENTITY_ID).state == STATE_ON
    await async_shutdown(hass, config_id)


async def test_state_attributes(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test state attributes."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )
    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    active_area_alert = load_json_fixture("single_alert_history.json")
    assert state.attributes[CONF_ALERT_MAX_AGE] == 10
    assert state.attributes[ATTR_SELECTED_AREAS_ACTIVE_ALERTS] == active_area_alert
    assert state.attributes[ATTR_SELECTED_AREAS_ALERTS] == active_area_alert
    combined_alerts = load_json_fixture("combined_alerts.json")
    assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS] == combined_alerts
    assert state.attributes[ATTR_COUNTRY_ALERTS] == combined_alerts
    await async_shutdown(hass, config_id)


async def test_interval(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test setting the interval."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["תל אביב - כל האזורים"],
        },
    )

    # Test the "update" path which is more involved than initial configuration.
    config_entry = hass.config_entries.async_get_entry(config_id)
    hass.config_entries.async_update_entry(
        config_entry,
        options={**config_entry.options, **{CONF_POLL_INTERVAL: 125}},
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    assert hass.states.get(ENTITY_ID).state == STATE_ON
    mock_urls(aioclient_mock, None, None)

    freezer.tick(datetime.timedelta(seconds=120))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    freezer.tick(datetime.timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    await async_shutdown(hass, config_id)


async def test_icons(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test state attributes."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(
        hass,
        {
            CONF_AREAS: ["תל אביב - כל האזורים"],
            CONF_ON_ICON: "mdi:emoticon-sad",
            CONF_OFF_ICON: "mdi:emoticon-happy",
        },
    )
    assert hass.states.get(ENTITY_ID).attributes["icon"] == "mdi:emoticon-sad"
    mock_urls(aioclient_mock, None, None)
    freezer.tick(datetime.timedelta(seconds=600))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(ENTITY_ID).attributes["icon"] == "mdi:emoticon-happy"
    await async_shutdown(hass, config_id)


async def test_unrecognized_area(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test unrecognized area."""
    mock_urls(aioclient_mock, "unrecognized_alert.json", None)
    config_id = await async_setup(hass)
    await async_shutdown(hass, config_id)
    assert "Alert has an unrecognized area: שכם" in caplog.text
    assert "Alert has an unrecognized area: סעד" not in caplog.text


async def test_additional_sensor(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test state of an additional sensor."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(hass)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_SERVICE,
        {CONF_NAME: "test", CONF_AREAS: ["תל אביב - כל האזורים"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(f"{ENTITY_ID}_test").state == STATE_ON
    await async_shutdown(hass, config_id)


async def test_all_areas_sensor(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test all-areas sensor."""
    freezer.move_to("2023-10-10 11:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_random_area_history.json")
    config_id = await async_setup(hass)
    state = hass.states.get(f"{ENTITY_ID}_{ALL_AREAS_ID_SUFFIX}")
    assert state.state == STATE_ON
    expected_alerts = load_json_fixture("single_alert_random_area_history.json")
    assert state.attributes[ATTR_COUNTRY_ACTIVE_ALERTS] == expected_alerts
    assert state.attributes[ATTR_COUNTRY_ALERTS] == expected_alerts
    await async_shutdown(hass, config_id)
