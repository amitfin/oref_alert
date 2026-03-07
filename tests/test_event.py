"""The tests for the event file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.components.event import ATTR_EVENT_TYPE, ATTR_EVENT_TYPES
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    CONF_ENTITY_ID,
    CONF_NAME,
    STATE_UNKNOWN,
)
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.oref_alert.const import (
    ADD_SENSOR_ACTION,
    ATTR_RECORD,
    CATEGORY_FIELD,
    CONF_AREA,
    CONF_AREAS,
    CONF_DURATION,
    DOMAIN,
    REMOVE_SENSOR_ACTION,
    SYNTHETIC_ALERT_ACTION,
)
from custom_components.oref_alert.records_schema import RecordType

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import Event, HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

AREA = "תל אביב - מרכז העיר"
DEFAULT_OPTIONS = {
    CONF_AREAS: [AREA],
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
    assert record.category == category

    await async_shutdown(hass, config_id)


async def test_dedup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test identical event dedup logic."""
    events: list[str] = []

    async def event_listener(event: Event) -> None:
        if event.data.get("entity_id") == "event.oref_alert" and (
            new_state := event.data.get("new_state")
        ):
            events.append(new_state.attributes.get(ATTR_EVENT_TYPE))

    hass.bus.async_listen("state_changed", event_listener)

    mock_urls(aioclient_mock, "single_alert_real_time.json", None)

    config_id = await async_setup(hass)

    assert events == [None, RecordType.ALERT]

    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert events == [None, RecordType.ALERT]

    freezer.tick(10 * 60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert events == [None, RecordType.ALERT, RecordType.ALERT]

    await async_shutdown(hass, config_id)


async def test_synthetic_no_dedup(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test synthetic doesn't have a dedup logic."""
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
    assert events == [None, RecordType.ALERT]

    freezer.tick(10)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert events == [None, RecordType.ALERT]

    await hass.services.async_call(
        DOMAIN,
        SYNTHETIC_ALERT_ACTION,
        {CONF_AREA: AREA, CATEGORY_FIELD: 1, CONF_DURATION: 100},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert events == [None, RecordType.ALERT, RecordType.ALERT]

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

    await hass.services.async_call(
        DOMAIN,
        REMOVE_SENSOR_ACTION,
        {CONF_ENTITY_ID: "binary_sensor.oref_alert_test"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("event.oref_alert_test") is None

    await async_shutdown(hass, config_id)


async def test_restore_record_dict(hass: HomeAssistant) -> None:
    """Test restoring event record from dict state does not fail."""
    mock_restore_cache(
        hass,
        [
            State(
                "event.oref_alert",
                STATE_UNKNOWN,
                {
                    ATTR_RECORD: {
                        "data": AREA,
                        "category": 1,
                        "channel": "website-history",
                        "alertDate": "2025-01-01 11:59:30",
                        "title": "",
                    }
                },
            )
        ],
    )
    config_id = await async_setup(hass)
    state = hass.states.get("event.oref_alert")
    assert state is not None
    await async_shutdown(hass, config_id)
