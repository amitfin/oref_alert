"""The tests for the init file."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import (
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_OFF,
    Platform,
)
from homeassistant.helpers import entity_registry
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_SERVICE,
    ATTR_COUNTRY_ALERTS,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_ALERT_MAX_AGE_DEPRECATED,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    CONF_SENSORS,
    DOMAIN,
    OREF_ALERT_UNIQUE_ID,
    REMOVE_SENSOR_SERVICE,
    SYNTHETIC_ALERT_SERVICE,
    TITLE,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import HomeAssistant

DEFAULT_OPTIONS = {CONF_AREAS: [], CONF_ALERT_ACTIVE_DURATION: 10}
ENTITY_ID = f"{Platform.BINARY_SENSOR}.{OREF_ALERT_UNIQUE_ID}"


async def test_setup(hass: HomeAssistant) -> None:
    """Test basic setup flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not hass.states.get(ENTITY_ID)


async def test_config_update(hass: HomeAssistant) -> None:
    """Test config update flow."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    attributes = state.attributes
    assert attributes is not None
    assert attributes[CONF_ALERT_ACTIVE_DURATION] == 10
    hass.config_entries.async_update_entry(
        config_entry, options={**DEFAULT_OPTIONS, CONF_ALERT_ACTIVE_DURATION: 5}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    attributes = state.attributes
    assert attributes is not None
    assert attributes[CONF_ALERT_ACTIVE_DURATION] == 5
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_add_remove_sensor_service(hass: HomeAssistant) -> None:
    """Test add_sensor and remove_sensor custom services."""
    config_entry = MockConfigEntry(domain=DOMAIN, options=DEFAULT_OPTIONS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        DOMAIN, ADD_SENSOR_SERVICE, {CONF_NAME: "test", CONF_AREAS: []}, blocking=True
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    entity_id = f"{ENTITY_ID}_test"
    assert hass.states.get(entity_id) is not None
    entity_reg = entity_registry.async_get(hass)
    entity = entity_reg.async_get(entity_id)
    assert entity is not None
    config_id = entity.config_entry_id
    assert config_id is not None
    entity_config_entry = hass.config_entries.async_get_entry(config_id)
    assert entity_config_entry is not None
    assert f"{TITLE} test" in entity_config_entry.options[CONF_SENSORS]

    await hass.services.async_call(
        DOMAIN,
        REMOVE_SENSOR_SERVICE,
        {CONF_ENTITY_ID: entity_id},
        blocking=True,
    )
    await hass.async_block_till_done(wait_background_tasks=True)
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
    await hass.async_block_till_done(wait_background_tasks=True)
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_SERVICE,
        {CONF_AREA: "קריית שמונה", CONF_DURATION: 20},
        blocking=True,
    )
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert len(state.attributes[ATTR_COUNTRY_ALERTS]) == 1
    assert state.attributes[ATTR_COUNTRY_ALERTS][0]["data"] == "קריית שמונה"


async def test_max_age_deprecation(hass: HomeAssistant) -> None:
    """Test an old config with max_age option."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, options={CONF_AREAS: [], CONF_ALERT_MAX_AGE_DEPRECATED: 15}
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    state = hass.states.get(ENTITY_ID)
    assert state is not None
    assert state.state == STATE_OFF
    assert state.attributes[CONF_ALERT_ACTIVE_DURATION] == 15
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_unknown_area(hass: HomeAssistant) -> None:
    """Test repair ticket of an unknown area."""
    repairs = async_capture_events(hass, ir.EVENT_REPAIRS_ISSUE_REGISTRY_UPDATED)
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        options={
            CONF_ALERT_ACTIVE_DURATION: 10,
            CONF_AREAS: ["unknown1"],
            CONF_SENSORS: {"x": ["unknown2"]},
        },
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(repairs) == 2
    for i in range(2):
        assert repairs[i].data["action"] == "create"
        assert repairs[i].data["domain"] == DOMAIN
        assert repairs[i].data["issue_id"] == f"{DOMAIN}_unknown{i + 1}"
