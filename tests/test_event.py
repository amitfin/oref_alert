"""The tests for the event file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.const import ATTR_FRIENDLY_NAME, CONF_NAME, STATE_UNKNOWN
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_ACTION,
    ATTR_RECORD,
    CATEGORY_FIELD,
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DOMAIN,
    SYNTHETIC_ALERT_ACTION,
)

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import Event, HomeAssistant

AREA = "חולון"
DEFAULT_OPTIONS = {
    CONF_AREAS: [AREA],
    CONF_ALERT_ACTIVE_DURATION: 10,
}


async def async_setup(
    hass: HomeAssistant, options: dict[str, Any] | None = None
) -> str:
    """Integration setup."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, options={**DEFAULT_OPTIONS, **(options or {})}
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry.entry_id


async def async_shutdown(hass: HomeAssistant, config_id: str) -> None:
    """Shutdown by removing the integration."""
    assert await hass.config_entries.async_remove(config_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    ("event_type", "category"),
    [
        ("pre_alert", 14),
        ("alert", 1),
        ("end", 13),
    ],
    ids=("pre_alert", "alert", "end"),
)
async def test_event(
    event_type: str,
    category: int,
    hass: HomeAssistant,
) -> None:
    """Test entity state."""
    config_id = await async_setup(hass)

    state = hass.states.get("event.oref_alert")
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert set(state.attributes.get(ATTR_EVENT_TYPES) or []) == {
        "pre_alert",
        "alert",
        "end",
    }
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == "Oref Alert"
    assert state.attributes.get(ATTR_EVENT_TYPE) is None
    assert state.attributes.get(ATTR_RECORD) is None

    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: category, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("event.oref_alert")
    assert state is not None
    assert state.attributes.get(ATTR_EVENT_TYPE) == event_type
    record = state.attributes.get(ATTR_RECORD)
    assert record is not None
    assert record.get(CATEGORY_FIELD) == category

    await async_shutdown(hass, config_id)


async def test_dedup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test identical event dedup logic."""
    events: list[str] = []

    async def event_listener(event: Event) -> None:
        if event.data.get("entity_id") == "event.oref_alert" and (
            new_state := event.data.get("new_state")
        ):
            events.append(new_state.attributes.get(ATTR_EVENT_TYPE))

    hass.bus.async_listen("state_changed", event_listener)

    config_id = await async_setup(hass)

    assert events == [None]

    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: 1, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events == [None, "alert"]

    freezer.tick(9 * 60)
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: 1, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events == [None, "alert"]

    freezer.tick(2 * 60)
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: 1, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events == [None, "alert", "alert"]

    freezer.tick()
    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: 13, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events == [None, "alert", "alert", "end"]

    await async_shutdown(hass, config_id)


async def test_additional(
    hass: HomeAssistant,
) -> None:
    """Test additional sensor."""
    config_id = await async_setup(hass)

    area = "טבריה"
    await hass.services.async_call(
        DOMAIN,
        ADD_SENSOR_ACTION,
        {CONF_NAME: "Test", CONF_AREAS: [area]},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("event.oref_alert_test")
    assert state is not None
    assert state.state == STATE_UNKNOWN

    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: area, CATEGORY_FIELD: 1, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()

    state = hass.states.get("event.oref_alert_test")
    assert state is not None
    assert state.attributes.get(ATTR_EVENT_TYPE) == "alert"
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == "Oref Alert Test"

    await async_shutdown(hass, config_id)
