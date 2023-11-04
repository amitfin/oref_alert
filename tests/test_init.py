"""The tests for the init file."""
from __future__ import annotations

from datetime import timedelta

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    Platform,
    STATE_OFF,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from freezegun.api import FrozenDateTimeFactory
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_SERVICE,
    REMOVE_SENSOR_SERVICE,
    SYNTHETIC_ALERT_SERVICE,
    ATTR_COUNTRY_ALERTS,
    CONF_ALERT_MAX_AGE,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DOMAIN,
    TITLE,
    OREF_ALERT_UNIQUE_ID,
)

DEFAULT_OPTIONS = {CONF_AREAS: [], CONF_ALERT_MAX_AGE: 10}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


async def test_setup(hass: HomeAssistant) -> None:
    """Test basic setup flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.states.get(ENTITY_ID)


async def test_config_update(hass: HomeAssistant) -> None:
    """Test config update flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[CONF_ALERT_MAX_AGE] == 10
    hass.config_entries.async_update_entry(
        config_entry, options={**DEFAULT_OPTIONS, **{CONF_ALERT_MAX_AGE: 5}}
    )
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).attributes[CONF_ALERT_MAX_AGE] == 5
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_add_remove_sensor_service(hass: HomeAssistant) -> None:
    """Test add_sensor and remove_sensor custom services."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN, ADD_SENSOR_SERVICE, {CONF_NAME: "test", CONF_AREAS: []}, blocking=True
    )
    await hass.async_block_till_done()
    entity_id = f"{ENTITY_ID}_test"
    assert hass.states.get(entity_id) is not None
    entity_reg = entity_registry.async_get(hass)
    entity_config_entry = hass.config_entries.async_get_entry(
        entity_reg.async_get(entity_id).config_entry_id
    )
    assert f"{TITLE} test" in entity_config_entry.options[CONF_SENSORS]

    await hass.services.async_call(
        DOMAIN,
        REMOVE_SENSOR_SERVICE,
        {CONF_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is None
    assert entity_reg.async_get(entity_id) is None


async def test_synthetic_alert_service(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test synthetic_alert custom service."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_SERVICE,
        {CONF_AREA: "קריית שמונה", CONF_DURATION: 20},
        blocking=True,
    )
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert len(state.attributes[ATTR_COUNTRY_ALERTS]) == 1
    assert state.attributes[ATTR_COUNTRY_ALERTS][0]["data"] == "קריית שמונה"
