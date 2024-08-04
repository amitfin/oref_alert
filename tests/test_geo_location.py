"""The tests for the geo_location file."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.const import (
    ATTR_DATE,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_SOURCE,
    Platform,
)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
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
    state = hass.states.get(f"{ENTITY_ID}_be_eri")
    assert state is not None
    assert state.state == "80.7"
    assert state.name == "בארי"
    assert state.attributes[CONF_SOURCE] == DOMAIN
    assert state.attributes[ATTR_LATITUDE] == 31.4245
    assert state.attributes[ATTR_LONGITUDE] == 34.4926
    assert state.attributes[ATTR_DATE] == dt_util.parse_datetime(
        "2023-10-07 06:30:00+03:00"
    )
    await async_shutdown(hass, config_id)


async def test_add_remove(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test adding and removing entities."""
    freezer.move_to("2023-10-07 06:29:00+03:00")
    config_id = await async_setup(hass, {CONF_POLL_INTERVAL: 1})
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 0
    entity_registry = er.async_get(hass)
    base_count = len(er.async_entries_for_config_entry(entity_registry, config_id))
    mock_urls(aioclient_mock, None, "single_alert_history.json")
    freezer.move_to("2023-10-07 06:30:01+03:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 1
    assert (
        len(er.async_entries_for_config_entry(entity_registry, config_id))
        == base_count + 1
    )
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(hass.states.async_all(Platform.GEO_LOCATION)) == 0
    assert (
        len(er.async_entries_for_config_entry(entity_registry, config_id)) == base_count
    )
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
