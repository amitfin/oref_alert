"""The tests for the update_events file."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.oref_alert.const import (
    CONF_ALERT_ACTIVE_DURATION,
    CONF_AREAS,
    DOMAIN,
)

from .utils import mock_urls

if TYPE_CHECKING:
    from freezegun.api import FrozenDateTimeFactory
    from homeassistant.core import Event, HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

DEFAULT_OPTIONS = {CONF_AREAS: ["פתח תקווה"], CONF_ALERT_ACTIVE_DURATION: 10}


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


async def test_event(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test bus event."""
    hass.config.latitude = 32.072
    hass.config.longitude = 34.879
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_update_history.json")

    events: list[Event] = []

    async def event_listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(f"{DOMAIN}_update_event", event_listener)

    config_id = await async_setup(hass)

    assert len(events) == 1
    assert events[0].data == {
        "area": "פתח תקווה",
        "home_distance": 1.6,
        "latitude": 32.084,
        "longitude": 34.8878,
        "category": 14,
        "title": "ניתן לצאת מהמרחב המוגן",
        "icon": "mdi:flash-alert",
        "emoji": "⚡",
    }

    await async_shutdown(hass, config_id)


async def test_event_fired_once(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that update event is fired only once."""
    freezer.move_to("2025-04-26 03:30:00+03:00")
    mock_urls(aioclient_mock, None, "single_update_history.json")

    events: list[Event] = []

    async def event_listener(event: Event) -> None:
        events.append(event)

    hass.bus.async_listen(f"{DOMAIN}_update_event", event_listener)

    config_id = await async_setup(hass)

    assert len(events) == 1

    freezer.tick(20)
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(events) == 1

    await async_shutdown(hass, config_id)
