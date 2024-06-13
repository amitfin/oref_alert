"""The tests for the sensor file."""
from __future__ import annotations

import datetime
from typing import Any

from freezegun.api import FrozenDateTimeFactory

from homeassistant.const import CONF_NAME, Platform, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.oref_alert.const import (
    ADD_SENSOR_SERVICE,
    ATTR_ALERT,
    ATTR_AREA,
    ATTR_TIME_TO_SHELTER,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
    END_TIME_ID_SUFFIX,
    TIME_TO_SHELTER_ID_SUFFIX,
)

from .utils import load_json_fixture, mock_urls

DEFAULT_OPTIONS = {CONF_AREAS: ["בארי"], CONF_ALERT_ACTIVE_DURATION: 10}
TIME_TO_SHELTER_ENTITY_ID = (
    f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_{TIME_TO_SHELTER_ID_SUFFIX}"
)
END_TIME_ENTITY_ID = f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_{END_TIME_ID_SUFFIX}"


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


async def test_time_to_shelter_state(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )

    config_id = await async_setup(hass)

    time_to_shelter = 15
    assert hass.states.get(TIME_TO_SHELTER_ENTITY_ID).state == str(time_to_shelter)
    assert (
        hass.states.get(TIME_TO_SHELTER_ENTITY_ID).attributes[ATTR_ALERT]
        == load_json_fixture("single_alert_history.json")[0]
    )

    for _ in range(100):
        freezer.tick(datetime.timedelta(seconds=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        time_to_shelter -= 1
        assert hass.states.get(TIME_TO_SHELTER_ENTITY_ID).state == (
            str(time_to_shelter) if time_to_shelter > -60 else STATE_UNKNOWN
        )

    await async_shutdown(hass, config_id)


async def test_time_to_shelter_attributes_no_alert(
    hass: HomeAssistant,
) -> None:
    """Test attributes when there is no alert."""
    config_id = await async_setup(hass)
    assert hass.states.get(TIME_TO_SHELTER_ENTITY_ID).attributes[ATTR_AREA] == "בארי"
    assert (
        hass.states.get(TIME_TO_SHELTER_ENTITY_ID).attributes[ATTR_TIME_TO_SHELTER]
        == 15
    )
    assert hass.states.get(TIME_TO_SHELTER_ENTITY_ID).attributes[ATTR_ALERT] is None
    await async_shutdown(hass, config_id)


async def test_alert_end_time_state(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(
        aioclient_mock, "multi_alerts_real_time.json", "multi_alerts_history.json"
    )

    config_id = await async_setup(hass)

    assert (
        hass.states.get(END_TIME_ENTITY_ID).attributes[ATTR_ALERT]
        == load_json_fixture("single_alert_history.json")[0]
    )
    alert_end_time = 600
    for _ in range(11):
        assert hass.states.get(END_TIME_ENTITY_ID).state == str(alert_end_time)
        freezer.tick(datetime.timedelta(seconds=60))
        async_fire_time_changed(hass)
        await hass.async_block_till_done(wait_background_tasks=True)
        alert_end_time -= 60

    assert hass.states.get(END_TIME_ENTITY_ID).state == STATE_UNKNOWN
    await async_shutdown(hass, config_id)


async def test_alert_end_time_attributes_no_alert(
    hass: HomeAssistant,
) -> None:
    """Test attributes when there is no alert."""
    config_id = await async_setup(hass)
    assert hass.states.get(END_TIME_ENTITY_ID).attributes[ATTR_AREA] == "בארי"
    assert hass.states.get(END_TIME_ENTITY_ID).attributes[CONF_ALERT_ACTIVE_DURATION] == 10
    assert hass.states.get(END_TIME_ENTITY_ID).attributes[ATTR_ALERT] is None
    await async_shutdown(hass, config_id)


async def test_no_entity_for_multi_areas(
    hass: HomeAssistant,
) -> None:
    """Test no entity is created for config with multi areas."""
    config_id = await async_setup(hass, {CONF_AREAS: ["תל אביב - כל האזורים"]})
    assert not hass.states.async_entity_ids(Platform.SENSOR)
    await async_shutdown(hass, config_id)


async def test_additional_sensor(
    hass: HomeAssistant,
) -> None:
    """Test additional sensor."""
    config_id = await async_setup(hass, {CONF_AREAS: ["תל אביב - כל האזורים"]})
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_SERVICE,
        {CONF_NAME: "test", CONF_AREAS: ["רעננה"]},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    sensors = hass.states.async_entity_ids(Platform.SENSOR)
    assert len(sensors) == 2
    for entity_id in (
        f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_test_{TIME_TO_SHELTER_ID_SUFFIX}",
        f"{Platform.SENSOR}.{OREF_ALERT_UNIQUE_ID}_test_{END_TIME_ID_SUFFIX}",
    ):
        assert entity_id in sensors
        assert hass.states.get(entity_id).attributes[ATTR_AREA] == "רעננה"
    await async_shutdown(hass, config_id)
