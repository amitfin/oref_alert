"""The tests for the init file."""
from __future__ import annotations

from homeassistant.const import CONF_NAME, CONF_STATE, Platform, STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oref_alert.const import (
    ADD_SENSOR_SERVICE,
    CONF_ALERT_MAX_AGE,
    CONF_AREAS,
    DOMAIN,
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


async def test_add_sensor_service(hass: HomeAssistant) -> None:
    """Test add_sensor custom service."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN, ADD_SENSOR_SERVICE, {CONF_NAME: "test", CONF_AREAS: []}, blocking=True
    )
    await hass.async_block_till_done()
    entity_id = f"{ENTITY_ID}_test"
    assert hass.states.get(entity_id)
    entity_reg = entity_registry.async_get(hass)
    template_config_entry = hass.config_entries.async_get_entry(
        entity_reg.async_get(entity_id).config_entry_id
    )
    assert template_config_entry.options["template_type"] == Platform.BINARY_SENSOR
    assert template_config_entry.options[CONF_STATE] == (
        r"{{[]|select('in',(state_attr('binary_sensor.oref_alert','country_active_alerts')|"
        r"map(attribute='data')|list))|list|length>0}}"
    )
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()
