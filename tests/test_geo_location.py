"""The tests for the geo_location file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import (
    ATTR_DATE,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_FRIENDLY_NAME,
    CONF_SOURCE,
    CONF_UNIT_OF_MEASUREMENT,
    Platform,
    UnitOfLength,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template, result_as_boolean
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ATTR_HOME_DISTANCE,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    CONF_POLL_INTERVAL,
    DOMAIN,
    LOCATION_ID_SUFFIX,
    OREF_ALERT_UNIQUE_ID,
)

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["בארי"], CONF_ALERT_ACTIVE_DURATION: 10}
ENTITY_ID = f"{Platform.GEO_LOCATION}.{OREF_ALERT_UNIQUE_ID}_{LOCATION_ID_SUFFIX}"


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


async def test_entity(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    config_id = await async_setup(hass)
    assert not any(
        entry.domain == Platform.GEO_LOCATION
        for entry in er.async_entries_for_config_entry(er.async_get(hass), config_id)
    )
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == "80.6"
    assert state.name == "בארי"
    assert state.attributes[CONF_SOURCE] == DOMAIN
    assert state.attributes[ATTR_LATITUDE] == 31.4245
    assert state.attributes[ATTR_LONGITUDE] == 34.4926
    assert state.attributes[CONF_UNIT_OF_MEASUREMENT] == UnitOfLength.KILOMETERS
    assert state.attributes[CONF_FRIENDLY_NAME] == "בארי"
    assert state.attributes[ATTR_HOME_DISTANCE] == 80.6
    assert state.attributes[ATTR_DATE] == dt_util.parse_datetime(
        "2023-10-07 06:30:00+03:00"
    )
    assert state.attributes["category"] == 1
    assert state.attributes["title"] == "ירי רקטות וטילים"
    assert len(state.attributes) == 9
    await async_shutdown(hass, config_id)


async def test_add_remove(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test adding and removing entities."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    config_id = await async_setup(hass, {CONF_POLL_INTERVAL: 1})
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 0
    mock_urls(aioclient_mock, None, "multi_alerts_history.json")
    freezer.tick(2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert {
        state.entity_id for state in hass.states.async_all(Platform.GEO_LOCATION)
    } == {ENTITY_ID, f"{ENTITY_ID}_2"}
    assert not any(
        entry.domain == Platform.GEO_LOCATION
        for entry in er.async_entries_for_config_entry(er.async_get(hass), config_id)
    )
    mock_urls(aioclient_mock, None, None)
    freezer.tick(2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 0
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    freezer.tick(2)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert {
        state.entity_id for state in hass.states.async_all(Platform.GEO_LOCATION)
    } == {ENTITY_ID}
    await async_shutdown(hass, config_id)


async def test_clean_start(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test cleaning old entities."""
    mock_urls(aioclient_mock, "single_alert_real_time.json", None)
    config_id = await async_setup(hass)
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 1
    mock_urls(aioclient_mock, None, None)
    assert await hass.config_entries.async_set_disabled_by(
        config_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await hass.config_entries.async_set_disabled_by(config_id, None)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 0
    await async_shutdown(hass, config_id)


async def test_attributes_update(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test entity state."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["category"] == 1
    mock_urls(aioclient_mock, None, "single_alert_history_update.json")
    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.attributes["category"] == 2
    await async_shutdown(hass, config_id)


async def test_distance_types(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test type of state and distance attribute."""
    freezer.move_to("2023-10-07 06:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    config_id = await async_setup(hass)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert result_as_boolean(
        Template(f"{{{{ states.{ENTITY_ID}.state is string }}}}", hass).async_render(
            parse_result=False
        )
    )
    assert result_as_boolean(
        Template(
            f"{{{{ states.{ENTITY_ID}.attributes.{ATTR_HOME_DISTANCE} is float }}}}",
            hass,
        ).async_render(parse_result=False)
    )
    await async_shutdown(hass, config_id)
